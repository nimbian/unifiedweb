"""Chat command layer tests (PLAN.md §6.2). Pure, no twitchio.

Commands carry a per-user 3s global cooldown, so the ``call`` helper advances a
controllable clock between commands (modelling players who don't spam). The
cooldown itself is exercised explicitly in the dedicated tests.
"""

from __future__ import annotations

import asyncio
import random
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from server import rules
from server.adapters import InboundMessage, MessageRouter
from server.arena import Arena
from server.commands import CREATE_COOLDOWN_S, GameCommands
from server.config import Config
from server.events import RecordingSink
from server.store import MemoryStore

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GAME_CONFIG = PROJECT_ROOT / "config" / "game.toml"

BADWORDS = {"slur"}


def _profanity(name: str) -> bool:
    return any(w in name.casefold() for w in BADWORDS)


async def _nosleep(_seconds: float) -> None:
    return None


class Clock:
    def __init__(self, t: float = 10_000.0) -> None:
        self.t = t

    def __call__(self) -> datetime:
        return datetime.fromtimestamp(self.t, tz=UTC)

    def advance(self, dt: float) -> None:
        self.t += dt


class Harness:
    def __init__(self) -> None:
        cfg = Config.load(GAME_CONFIG)
        # Boot the arena open (live play state); the !start/!close gate has its
        # own tests, which close it explicitly.
        cfg.arena = replace(cfg.arena, open_on_launch=True)
        self.store = MemoryStore()
        self.clock = Clock()
        self.arena = Arena(
            cfg, self.store, RecordingSink(), rng=random.Random(1), sleep=_nosleep, now=self.clock
        )
        self.cmds = GameCommands(
            cfg, self.store, self.arena, rng=random.Random(2),
            now=self.clock, profanity_check=_profanity,
        )
        # The router turns command outcomes into overlay tickers (primary feedback)
        # + chat mirror strings; tests assert on both channels.
        self.ticker_sink = RecordingSink()
        self.router = MessageRouter(self.cmds, self.ticker_sink)

    def call(self, u: dict, text: str, gap: float = 4.0) -> list[str]:
        self.clock.advance(gap)  # space commands out past the global cooldown
        msg = InboundMessage(text=text, timestamp=self.clock(), **u)
        return asyncio.run(self.router.dispatch(msg))

    def tickers(self) -> list[dict]:
        return self.ticker_sink.of_type("ticker")


def user(
    uid: str = "u1", login: str = "brian", mod: bool = False, platform: str = "twitch"
) -> dict:
    return {
        "platform": platform,
        "platform_user_id": uid,
        "login": login,
        "display_name": login.title(),
        "is_mod": mod,
    }


# ---------------------------------------------------------------------------
# !create
# ---------------------------------------------------------------------------
def test_create_makes_character_and_replies():
    h = Harness()
    replies = h.call(user(), "!create barbarian orc Thorak")
    assert len(replies) == 1
    assert replies[0].startswith("@brian Thorak the ")
    assert "Orc Barbarian is born!" in replies[0]  # "the <personality> Orc Barbarian"
    assert "!enter to fight" in replies[0]
    ch = next(iter(h.store.characters.values()))
    assert ch.class_name == "barbarian" and ch.race == "orc" and ch.name == "Thorak"
    from server import content

    assert ch.personality in content.PERSONALITIES  # a cosmetic trait was assigned


def test_create_a_phase2_class():
    h = Harness()
    reply = h.call(user(), "!create sorcerer tiefling Zara")[0]
    assert "Sorcerer is born!" in reply
    ch = next(iter(h.store.characters.values()))
    assert ch.class_name == "sorcerer" and ch.race == "tiefling"


def test_create_rejects_unknown_class_and_race():
    h = Harness()
    assert "unknown class" in h.call(user(), "!create wizrd human Bob")[0]
    assert "unknown race" in h.call(user(), "!create wizard klingon Bob")[0]
    assert h.store.characters == {}


def _cmds_with_engine(engine: str, seed: int = 7) -> GameCommands:
    cfg = Config.load(GAME_CONFIG)
    cfg.combat = replace(cfg.combat, engine=engine)
    store = MemoryStore()
    clock = Clock()
    arena = Arena(cfg, store, RecordingSink(), rng=random.Random(1), sleep=_nosleep, now=clock)
    return GameCommands(
        cfg, store, arena, rng=random.Random(seed), now=clock, profanity_check=_profanity
    )


def test_moore_engine_rolls_sorted_stats_by_class_priority():
    # R1/§13.2: under the moore engine !create assigns the highest rolls to the
    # class's priority stats (sorted-4d6), so primary/secondary take the top two.
    cmds = _cmds_with_engine("moore")
    cd = cmds.cfg.classes["wizard"]  # Wizard primary = WIS (hard rule #6)
    block = cmds._roll_stats("wizard")
    ranked = sorted(block.values(), reverse=True)
    assert block[cd.primary] == ranked[0]    # highest roll -> primary
    assert block[cd.secondary] == ranked[1]  # next-highest -> secondary


def test_classic_engine_keeps_the_unsorted_roll():
    # Until the engine flips, !create keeps the independent per-stat roll its
    # balance gate was tuned on — no sorting into class priority.
    cmds = _cmds_with_engine("classic")
    cmds._rng = random.Random(123)
    got = cmds._roll_stats("wizard")
    expected = rules.roll_stat_block(random.Random(123), cmds.cfg.stats)
    assert got == expected


def test_create_rejects_profanity():
    h = Harness()
    assert "isn't allowed" in h.call(user(), "!create rogue elf slur")[0]
    assert h.store.characters == {}


def test_create_enforces_roster_limit():
    h = Harness()
    for name in ("Aaa", "Bbb", "Ccc"):
        h.call(user(), f"!create fighter human {name}", gap=CREATE_COOLDOWN_S + 1)
    reply = h.call(user(), "!create fighter human Ddd", gap=CREATE_COOLDOWN_S + 1)
    assert "already have" in reply[0]
    assert len(h.store.characters) == 3


def test_create_cooldown():
    h = Harness()
    h.call(user(), "!create monk human One")
    blocked = h.call(user(), "!create monk human Two", gap=5)  # past global, within create cd
    assert "wait" in blocked[0].lower()
    ok = h.call(user(), "!create monk human Two", gap=CREATE_COOLDOWN_S + 1)
    assert "is born" in ok[0]


# ---------------------------------------------------------------------------
# !enter / !stats / !roster / !inspect
# ---------------------------------------------------------------------------
def test_enter_queues_and_reports_position():
    h = Harness()
    h.call(user(), "!create ranger human Robin")
    replies = h.call(user(), "!enter")
    assert "entered the queue (position 1)" in replies[0]
    assert h.arena.queue_size == 1


def test_enter_without_character_errors():
    h = Harness()
    assert "no living character" in h.call(user(), "!enter")[0]


def test_enter_by_name_selects_that_character():
    h = Harness()
    h.call(user(), "!create rogue elf Scout", gap=CREATE_COOLDOWN_S + 1)
    h.call(user(), "!create wizard human Merlin", gap=CREATE_COOLDOWN_S + 1)
    h.call(user(), "!enter Scout")
    assert h.arena.queue_size == 1


def test_stats_and_inspect_format():
    h = Harness()
    amy = user(login="amy")
    h.call(amy, "!create paladin human Grace")
    stats = h.call(amy, "!stats")[0]
    assert stats.startswith("Grace the ")  # "Grace the <personality> - Lv1 ..."
    assert "Lv1 Paladin (Human)" in stats
    assert "0W/0L" in stats and "battles left" in stats
    inspected = h.call(user(uid="u2", login="bob"), "!inspect Grace")[0]
    assert inspected.startswith("Grace the ") and "Lv1 Paladin (Human)" in inspected


def test_roster_lists_living_characters():
    h = Harness()
    h.call(user(), "!create barbarian orc Smash", gap=CREATE_COOLDOWN_S + 1)
    h.call(user(), "!create monk human Chi", gap=CREATE_COOLDOWN_S + 1)
    roster = h.call(user(), "!roster")[0]
    assert "1) Smash Lv1 Barb" in roster
    assert "2) Chi Lv1 Monk" in roster


# ---------------------------------------------------------------------------
# !retire two-step
# ---------------------------------------------------------------------------
def test_retire_requires_confirm():
    h = Harness()
    h.call(user(), "!create fighter human Doomed")
    cid = next(iter(h.store.characters))
    prompt = h.call(user(), "!retire Doomed")
    assert "!confirm" in prompt[0]
    assert h.store.characters[cid].is_retired is False
    done = h.call(user(), "!confirm")
    assert "retired" in done[0]
    assert h.store.characters[cid].is_retired is True


def test_confirm_without_pending():
    h = Harness()
    assert "nothing to confirm" in h.call(user(), "!confirm")[0]


# ---------------------------------------------------------------------------
# leaderboards
# ---------------------------------------------------------------------------
def test_leaderboards():
    h = Harness()
    uid = h.store.add_user("carol")
    flat = {"STR": 10, "DEX": 10, "CON": 10, "INT": 10, "WIS": 10, "CHA": 10}
    a = h.store.create_character(
        user_id=uid, name="Alpha", class_name="rogue", race="human",
        stats=flat, sprite_set="rogue_01",
    )
    b = h.store.create_character(
        user_id=uid, name="Beta", class_name="monk", race="human",
        stats=flat, sprite_set="monk_01",
    )
    h.store.characters[a.id].lifetime_damage, h.store.characters[a.id].wins = 5000, 2
    h.store.characters[b.id].lifetime_damage, h.store.characters[b.id].wins = 9000, 1
    # All-time board reads lifetime stats directly.
    alltime = h.call(user(), "!top alltime")[0]
    assert alltime.startswith("All-time damage: 1) Beta 9,000 2) Alpha 5,000")
    # Season boards aggregate round entries, of which these seeded chars have none.
    assert "No season damage" in h.call(user(), "!leaderboard")[0]
    assert "No season wins" in h.call(user(), "!top wins")[0]


# ---------------------------------------------------------------------------
# mod commands & safety
# ---------------------------------------------------------------------------
def test_pause_resume_is_mod_only():
    h = Harness()
    assert h.call(user(mod=False), "!pause") == []  # ignored for non-mods
    assert h.arena.paused is False
    h.call(user(mod=True), "!pause")
    assert h.arena.paused is True
    h.call(user(mod=True), "!resume")
    assert h.arena.paused is False


def test_start_close_is_mod_only():
    h = Harness()
    assert h.call(user(mod=False), "!close") == []  # ignored for non-mods
    assert h.arena.is_open is True
    assert h.call(user(mod=False), "!start") == []
    assert h.arena.is_open is True

    close_reply = h.call(user(mod=True), "!close")
    assert h.arena.is_open is False
    assert "queue is kept" in close_reply[0]
    assert "already closed" in h.call(user(mod=True), "!close")[0]

    start_reply = h.call(user(mod=True), "!start")
    assert h.arena.is_open is True
    assert "OPEN" in start_reply[0]
    assert "already open" in h.call(user(mod=True), "!start")[0]


def test_start_while_paused_reminds_about_resume():
    h = Harness()
    h.call(user(mod=True), "!pause")
    h.call(user(mod=True), "!close")
    reply = h.call(user(mod=True), "!start")
    assert h.arena.is_open is True
    assert "!resume" in reply[0]  # still paused — the mod needs both


def test_enter_while_closed_still_queues_with_note():
    h = Harness()
    h.call(user(), "!create barbarian orc Thorak")
    h.call(user(mod=True, uid="m1", login="mod"), "!close")
    reply = h.call(user(), "!enter")
    assert "entered the queue" in reply[0]
    assert "arena is closed" in reply[0]
    ch = next(iter(h.store.characters.values()))
    assert h.arena.is_queued(ch.id)  # queued for when a mod reopens

    # No closed-note once the arena is open again (fresh character to re-enter).
    h.call(user(mod=True, uid="m1", login="mod"), "!start")
    h.call(user(), "!create wizard human Vala", gap=CREATE_COOLDOWN_S + 1)
    open_reply = h.call(user(), "!enter Vala")
    assert "entered the queue" in open_reply[0]
    assert "arena is closed" not in open_reply[0]


def test_banplayer_blocks_commands():
    h = Harness()
    brian = user(uid="u1", login="brian")
    h.call(brian, "!roster")  # registers brian's user record
    ban = h.call(user(uid="mod9", login="mods", mod=True), "!banplayer @brian")
    assert "now banned" in ban[0]
    assert h.call(brian, "!roster") == []  # banned -> dropped


def test_renamechar_mod_only():
    h = Harness()
    h.call(user(), "!create wizard human Oldname")
    cid = next(iter(h.store.characters))
    assert h.call(user(mod=False), "!renamechar Oldname Newname") == []
    h.call(user(mod=True), "!renamechar Oldname Newname")
    assert h.store.characters[cid].name == "Newname"


def test_global_cooldown_drops_rapid_commands():
    h = Harness()
    assert h.call(user(), "!help")  # first goes through
    assert h.call(user(), "!help", gap=1) == []  # within 3s -> dropped
    assert h.call(user(), "!help", gap=4)  # allowed again


def test_unknown_and_nonprefixed_ignored():
    h = Harness()
    assert h.call(user(), "!frobnicate") == []
    assert h.call(user(), "hello chat") == []


def test_help_lists_commands():
    h = Harness()
    reply = h.call(user(), "!help")[0]
    assert "!create" in reply and "!enter" in reply


# ---------------------------------------------------------------------------
# Overlay ticker is the primary feedback channel (PLAN.md §6.1)
# ---------------------------------------------------------------------------
def test_every_outcome_emits_a_ticker():
    h = Harness()
    h.call(user(), "!create barbarian orc Thorak")
    tick = h.tickers()[-1]
    assert tick["kind"] == "create"
    assert tick["platform"] == "twitch"
    assert "Thorak the" in tick["text"] and "Barbarian is born!" in tick["text"]
    assert "(@brian)" in tick["text"]  # addressed outcomes carry the owner handle


def test_command_error_emits_error_ticker():
    h = Harness()
    reply = h.call(user(), "!create wizrd human Bob")
    assert "unknown class" in reply[0]
    tick = h.tickers()[-1]
    assert tick["kind"] == "error"
    assert "unknown class" in tick["text"]


def test_public_outcome_ticker_has_no_mention():
    h = Harness()
    h.call(user(), "!help")
    tick = h.tickers()[-1]
    assert tick["kind"] == "info"
    assert "(@" not in tick["text"]  # not addressed -> no owner handle appended


# ---------------------------------------------------------------------------
# Identity is per (platform, platform_user_id) — no cross-platform linking
# ---------------------------------------------------------------------------
def test_identity_is_per_platform():
    h = Harness()
    tw = user(uid="123", login="sam", platform="twitch")
    yt = user(uid="123", login="sam", platform="youtube")  # same id, different platform
    h.call(tw, "!create rogue elf TwinT")
    h.call(yt, "!create monk human TwinY")

    assert len(h.store.users) == 2  # two separate humans, no linking
    chars = list(h.store.characters.values())
    assert len(chars) == 2
    assert chars[0].user_id != chars[1].user_id
    # Each identity sees only its own roster.
    tw_roster = h.call(tw, "!roster")[0]
    yt_roster = h.call(yt, "!roster")[0]
    assert "TwinT" in tw_roster and "TwinY" not in tw_roster
    assert "TwinY" in yt_roster and "TwinT" not in yt_roster


def test_ban_is_scoped_to_platform():
    h = Harness()
    tw = user(uid="9", login="dup", platform="twitch")
    yt = user(uid="9", login="dup", platform="youtube")
    h.call(tw, "!roster")  # register both identities
    h.call(yt, "!roster")
    h.call(user(uid="mod", login="mods", mod=True, platform="twitch"), "!banplayer dup")
    assert h.call(tw, "!roster") == []          # twitch 'dup' is banned
    assert h.call(yt, "!roster") != []          # youtube 'dup' is untouched


# ---------------------------------------------------------------------------
# R5 shop (!shop / !buy / !gear) — docs/R4_R6_plan.md
# ---------------------------------------------------------------------------
def _enable_shop(h: Harness) -> None:
    from dataclasses import replace
    h.cmds.cfg.shop = replace(h.cmds.cfg.shop, enabled=True)  # arena shares this cfg


def test_shop_commands_are_closed_until_enabled():
    h = Harness()
    assert "isn't open" in h.call(user(), "!shop")[0]
    assert "isn't open" in h.call(user(), "!buy iron sword")[0]


def test_shop_lists_the_catalog_when_enabled():
    h = Harness()
    _enable_shop(h)
    reply = h.call(user(), "!shop")[0]
    assert "Iron Sword" in reply and "weapon" in reply.lower() and "g)" in reply


def test_buy_requires_enough_gold():
    h = Harness()
    _enable_shop(h)
    h.call(user(), "!create barbarian human Thorak")
    # default starting gold (100) can't afford the 500g Iron Sword
    reply = h.call(user(), "!buy Iron Sword")[0]
    assert "not enough gold" in reply.lower()


def test_buy_equips_and_deducts_gold_then_gear_lists_it():
    h = Harness()
    _enable_shop(h)
    h.call(user(), "!create barbarian human Thorak")
    ch = next(iter(h.store.characters.values()))
    asyncio.run(h.store.credit_gold(ch.user_id, 1000))
    before = asyncio.run(h.store.get_gold(ch.user_id))

    reply = h.call(user(), "!buy Iron Sword")[0]
    assert "equipped Iron Sword" in reply
    assert asyncio.run(h.store.get_gold(ch.user_id)) == before - 500
    assert asyncio.run(h.store.get_equipment(ch.id)) == {"weapon": "iron_sword"}

    gear = h.call(user(), "!gear")[0]
    assert "Iron Sword" in gear


def test_buying_same_slot_replaces_the_item():
    h = Harness()
    _enable_shop(h)
    h.call(user(), "!create barbarian human Thorak")
    ch = next(iter(h.store.characters.values()))
    asyncio.run(h.store.credit_gold(ch.user_id, 5000))
    h.call(user(), "!buy Iron Sword")
    h.call(user(), "!buy Steel Sword")  # same slot -> replaces
    assert asyncio.run(h.store.get_equipment(ch.id)) == {"weapon": "steel_sword"}


# ---------------------------------------------------------------------------
# R6 co-training (!train / !accept / !decline) — docs/R4_R6_plan.md
# ---------------------------------------------------------------------------
def _enable_training(h: Harness) -> None:
    from dataclasses import replace
    h.cmds.cfg.training = replace(h.cmds.cfg.training, enabled=True)


def _retire_char(h: Harness, u: dict, name: str, cls: str = "barbarian") -> object:
    h.call(u, f"!create {cls} human {name}", gap=CREATE_COOLDOWN_S + 1)  # clear create cooldown
    ch = next(c for c in h.store.characters.values() if c.name == name)
    asyncio.run(h.store.retire_character(ch.id))
    return h.store.characters[ch.id]


def test_training_closed_until_enabled():
    h = Harness()
    assert "isn't available" in h.call(user(), "!train A B barbarian human Kid")[0]


def test_train_then_accept_creates_a_trained_child_with_lineage():
    h = Harness()
    _enable_training(h)
    ua = user(uid="1", login="ann")
    ub = user(uid="2", login="bob")
    pa = _retire_char(h, ua, "Alpha")
    pb = _retire_char(h, ub, "Bravo")
    asyncio.run(h.store.credit_gold(pa.user_id, 5000))

    invite = h.call(ua, "!train Alpha Bravo barbarian human Cub")[0]
    assert "!accept" in invite and "Cub" in invite
    # Bob (the other parent's owner) accepts.
    born = h.call(ub, "!accept")[0]
    assert "Cub is born" in born and "Alpha & Bravo" in born

    child = next(c for c in h.store.characters.values() if c.name == "Cub")
    assert child.user_id == pa.user_id                 # child belongs to the initiator
    assert child.trained_by_a == pa.id and child.trained_by_b == pb.id
    assert child.generation == 2
    assert h.store.characters[pa.id].mentor_uses == 1  # both parents' uses incremented
    assert h.store.characters[pb.id].mentor_uses == 1


def test_train_requires_your_mentor_to_be_retired():
    h = Harness()
    _enable_training(h)
    ua = user(uid="1", login="ann")
    h.call(ua, "!create barbarian human Alpha")  # NOT retired
    reply = h.call(ua, "!train Alpha Whoever barbarian human Cub")[0]
    assert "no RETIRED character" in reply


def test_train_rejects_both_parents_from_same_owner():
    h = Harness()
    _enable_training(h)
    ua = user(uid="1", login="ann")
    _retire_char(h, ua, "Alpha")
    _retire_char(h, ua, "Beta")
    reply = h.call(ua, "!train Alpha Beta barbarian human Cub")[0]
    assert "another player" in reply.lower()


def test_decline_cancels_the_invitation():
    h = Harness()
    _enable_training(h)
    ua = user(uid="1", login="ann")
    ub = user(uid="2", login="bob")
    pa = _retire_char(h, ua, "Alpha")
    _retire_char(h, ub, "Bravo")
    asyncio.run(h.store.credit_gold(pa.user_id, 5000))
    h.call(ua, "!train Alpha Bravo barbarian human Cub")
    assert "declined" in h.call(ub, "!decline")[0]
    assert "no training invitation" in h.call(ub, "!accept")[0]  # nothing left to accept
    assert not any(c.name == "Cub" for c in h.store.characters.values())
