"""Round state machine tests (PLAN.md §5).

Async round logic is exercised with a fake clock (no-op sleep) and a seeded RNG
so a full 60s round resolves instantly and deterministically. Each async body is
driven with ``asyncio.run`` — no pytest-asyncio dependency.
"""

from __future__ import annotations

import asyncio
import random
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from server import rules
from server.arena import Arena, Phase, _weighted_index
from server.config import Config
from server.events import RecordingSink
from server.models import RoundResult
from server.store import MemoryStore

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GAME_CONFIG = PROJECT_ROOT / "config" / "game.toml"

STATS = {"STR": 15, "DEX": 14, "CON": 13, "INT": 12, "WIS": 11, "CHA": 10}


def _fixed_now() -> datetime:
    return datetime(2026, 7, 1, 12, 0, 0, tzinfo=UTC)


async def _nosleep(_seconds: float) -> None:
    return None


def build_arena(
    store: MemoryStore, seed: int = 1, *, open_on_launch: bool = True
) -> tuple[Arena, RecordingSink, Config]:
    cfg = Config.load(GAME_CONFIG)
    # Pin arena events off: these tests assert exact ticker counts / XP values.
    # Event behavior has its own suite (test_arena_events.py). chance <= 0 short-
    # circuits before any rng draw, so seeded streams here are unaffected.
    cfg.round = replace(cfg.round, event_chance=0.0)
    # Boot open by default: the closed-boot gate has its own tests below;
    # run_once() bypasses the gate, but run()-driven tests need the arena open.
    cfg.arena = replace(cfg.arena, open_on_launch=open_on_launch)
    sink = RecordingSink()
    arena = Arena(
        cfg, store, sink, rng=random.Random(seed), sleep=_nosleep, now=_fixed_now
    )
    return arena, sink, cfg


def make_char(store: MemoryStore, login: str, name: str, class_name: str, level: int = 1):
    uid = store.add_user(login)
    return store.create_character(
        user_id=uid,
        name=name,
        class_name=class_name,
        race="human",
        stats=dict(STATS),
        sprite_set=f"{class_name}_01",
        level=level,
    )


# ---------------------------------------------------------------------------
# A full round
# ---------------------------------------------------------------------------
def test_empty_queue_fills_with_npcs_and_completes():
    store = MemoryStore()
    arena, sink, cfg = build_arena(store)
    n = cfg.round.fighters_per_round

    outcome = asyncio.run(arena.run_once())

    assert not outcome.voided
    assert len(outcome.entries) == n  # NPCs fill every slot
    assert all(e.is_npc for e in outcome.entries)  # nobody queued -> all NPC fill
    assert all(e.character_id is None for e in outcome.entries)
    assert store.characters == {}  # NPCs are never persisted as characters

    starts = sink.of_type("round_start")
    assert len(starts) == 1 and len(starts[0]["fighters"]) == n
    assert sink.of_type("attack"), "combat should emit attack events"

    ends = sink.of_type("round_end")
    assert len(ends) == 1
    standings = ends[0]["standings"]
    assert [s["placement"] for s in standings] == list(range(1, n + 1))
    assert sorted(e.placement for e in outcome.entries) == list(range(1, n + 1))


def test_round_emits_winner_ticker():
    store = MemoryStore()
    arena, sink, _ = build_arena(store, seed=5)
    ch = make_char(store, "brian", "Thorak", "barbarian")
    asyncio.run(arena.enqueue(ch.id, ch.user_id))
    asyncio.run(arena.run_once())

    tickers = sink.of_type("ticker")
    assert len(tickers) == 1
    assert tickers[0]["kind"] == "winner"
    assert "wins with" in tickers[0]["text"]


def test_round_start_fighters_carry_platform_for_badge():
    store = MemoryStore()
    arena, sink, _ = build_arena(store, seed=5)
    ch = make_char(store, "brian", "Thorak", "barbarian")  # add_user defaults platform=twitch
    asyncio.run(arena.enqueue(ch.id, ch.user_id))
    asyncio.run(arena.run_once())

    fighters = sink.of_type("round_start")[0]["fighters"]
    assert all("platform" in f for f in fighters)
    mine = next(f for f in fighters if f["name"] == "Thorak")
    assert mine["platform"] == "twitch"
    # Every fighter carries a personality field for the round-start flavor; NPC
    # fill always has one assigned (PLAN.md §7).
    assert all("personality" in f for f in fighters)
    assert all(f["personality"] for f in fighters if f["is_npc"])


def test_countdowns_cover_every_phase():
    store = MemoryStore()
    arena, sink, cfg = build_arena(store)
    asyncio.run(arena.run_once())
    phases = {c["phase"] for c in sink.of_type("countdown")}
    # Combat included: the overlay needs a live fight timer (not a frozen title).
    assert {"intermission", "roster_lock", "combat", "results"} <= phases
    # longest intermission countdown value equals the configured duration
    inter = [c["seconds_left"] for c in sink.of_type("countdown") if c["phase"] == "intermission"]
    assert max(inter) == cfg.timings.intermission_seconds


# ---------------------------------------------------------------------------
# Real characters, matchmaking, aggregates
# ---------------------------------------------------------------------------
def test_real_character_fights_and_updates_aggregates():
    store = MemoryStore()
    arena, sink, cfg = build_arena(store, seed=5)
    ch = make_char(store, "brian", "Thorak", "barbarian")

    assert asyncio.run(arena.enqueue(ch.id, ch.user_id)) == 1
    outcome = asyncio.run(arena.run_once())

    mine = [e for e in outcome.entries if e.character_id == ch.id]
    assert len(mine) == 1 and not mine[0].is_npc

    updated = store.characters[ch.id]
    assert updated.battles_fought == 1
    assert updated.wins + updated.losses == 1
    assert (updated.wins == 1) == (mine[0].placement == 1)
    assert updated.lifetime_damage == mine[0].total_damage
    assert updated.lifetime_hits == mine[0].hits
    assert updated.xp == rules.xp_for_placement(mine[0].placement, cfg.xp)


def test_per_battle_leveling_grants_one_level_and_retires_placement_xp():
    # R3 (PLAN.md §13.1): with [xp].mode = "per_battle" every completed battle is
    # +1 level (capped at levels_max), placement XP is retired, and the primary
    # stat still grows one per level.
    store = MemoryStore()
    arena, _, cfg = build_arena(store, seed=5)
    cfg.xp = replace(cfg.xp, mode="per_battle", levels_max=20)
    ch = make_char(store, "brian", "Thorak", "barbarian", level=1)
    primary = cfg.classes[ch.class_name].primary
    base_primary = ch.stats[primary]

    asyncio.run(arena.enqueue(ch.id, ch.user_id))
    asyncio.run(arena.run_once())
    updated = store.characters[ch.id]
    assert updated.level == 2  # exactly one level, regardless of placement
    assert updated.xp == 0  # no placement XP awarded
    assert updated.battles_fought == 1
    assert updated.stats[primary] == base_primary + cfg.xp.per_level_primary_bonus

    asyncio.run(arena.enqueue(ch.id, ch.user_id))
    asyncio.run(arena.run_once())
    assert store.characters[ch.id].level == 3  # +1 again next battle


def test_per_battle_leveling_caps_at_levels_max():
    store = MemoryStore()
    arena, _, cfg = build_arena(store, seed=5)
    cfg.xp = replace(cfg.xp, mode="per_battle", levels_max=20)
    ch = make_char(store, "amy", "Cap", "fighter", level=20)
    asyncio.run(arena.enqueue(ch.id, ch.user_id))
    asyncio.run(arena.run_once())
    assert store.characters[ch.id].level == 20  # already maxed, stays put


def test_one_character_per_user_per_round_with_overflow_priority():
    store = MemoryStore()
    arena, _, _ = build_arena(store)
    uid = store.add_user("bob")
    c1 = store.create_character(
        user_id=uid, name="First", class_name="rogue", race="human",
        stats=dict(STATS), sprite_set="rogue_01",
    )
    c2 = store.create_character(
        user_id=uid, name="Second", class_name="monk", race="human",
        stats=dict(STATS), sprite_set="monk_01",
    )
    asyncio.run(arena.enqueue(c1.id, uid))
    asyncio.run(arena.enqueue(c2.id, uid))

    out1 = asyncio.run(arena.run_once())
    bobs = [e for e in out1.entries if e.character_id in (c1.id, c2.id)]
    assert len(bobs) == 1 and bobs[0].character_id == c1.id  # FIFO, one per user
    assert arena.queue_size == 1  # c2 held over

    out2 = asyncio.run(arena.run_once())
    assert any(e.character_id == c2.id for e in out2.entries)  # priority next round
    assert arena.queue_size == 0


def test_enqueue_is_idempotent_per_character():
    store = MemoryStore()
    arena, _, _ = build_arena(store)
    ch = make_char(store, "dave", "Rex", "ranger")
    assert asyncio.run(arena.enqueue(ch.id, ch.user_id)) == 1
    assert asyncio.run(arena.enqueue(ch.id, ch.user_id)) == 1
    assert arena.queue_size == 1


# ---------------------------------------------------------------------------
# R2 weighted-lottery queue (PLAN.md §13.1)
# ---------------------------------------------------------------------------
class _FakeRandom:
    """Deterministic stand-in exposing just what _weighted_index needs."""

    def __init__(self, value: float = 0.0):
        self.value = value

    def random(self) -> float:
        return self.value

    def randrange(self, n: int) -> int:
        return 0


def test_weighted_index_picks_by_cumulative_weight():
    # r = random()*total lands in the chosen bucket's cumulative span.
    assert _weighted_index([1.0, 0.0, 0.0], _FakeRandom(0.9)) == 0
    assert _weighted_index([0.0, 0.0, 1.0], _FakeRandom(0.9)) == 2
    assert _weighted_index([1.0, 1.0], _FakeRandom(0.4)) == 0  # r=0.8 -> bucket 0 (<=1)
    assert _weighted_index([1.0, 1.0], _FakeRandom(0.6)) == 1  # r=1.2 -> bucket 1
    # All-zero weights fall back to a uniform pick (no div-by-zero).
    assert _weighted_index([0.0, 0.0], _FakeRandom(0.9)) == 0


def _lottery_arena(store, *, slots: int, seed: int = 1):
    arena, sink, cfg = build_arena(store, seed=seed)
    cfg.queue = replace(cfg.queue, selection="weighted_lottery", miss_weight=1.0)
    cfg.round = replace(cfg.round, fighters_per_round=slots)
    return arena, sink, cfg


def test_weighted_lottery_seats_priority_token_first():
    store = MemoryStore()
    arena, _, _ = _lottery_arena(store, slots=1)
    normal = make_char(store, "u1", "Normal", "rogue")
    vip = make_char(store, "u2", "Vip", "monk")
    asyncio.run(arena.enqueue(normal.id, normal.user_id))
    asyncio.run(arena.enqueue(vip.id, vip.user_id, priority=True))

    out = asyncio.run(arena.run_once())
    ids = {e.character_id for e in out.entries}
    assert vip.id in ids and normal.id not in ids  # priority guaranteed the seat
    assert arena.queue_size == 1  # normal held over


def test_weighted_lottery_accumulates_misses_on_skipped():
    store = MemoryStore()
    arena, _, _ = _lottery_arena(store, slots=2)
    chars = [make_char(store, f"u{i}", f"C{i}", "fighter") for i in range(5)]
    for c in chars:
        asyncio.run(arena.enqueue(c.id, c.user_id))

    asyncio.run(arena.run_once())
    assert arena.queue_size == 3  # 2 seated of 5, 3 held over
    # Misses bucket per round kind/tier (R4); these are all races -> "race" bucket.
    assert all(item.misses.get("race") == 1 for item in arena._queue)  # each skip = +1

    asyncio.run(arena.run_once())
    assert arena.queue_size == 1  # 2 more seated
    assert all(item.misses.get("race") == 2 for item in arena._queue)


def test_weighted_lottery_one_character_per_user():
    store = MemoryStore()
    arena, _, _ = _lottery_arena(store, slots=8)
    uid = store.add_user("solo")
    a = store.create_character(user_id=uid, name="Aa", class_name="rogue", race="human",
                               stats=dict(STATS), sprite_set="rogue_01")
    b = store.create_character(user_id=uid, name="Bb", class_name="monk", race="human",
                               stats=dict(STATS), sprite_set="monk_01")
    asyncio.run(arena.enqueue(a.id, uid))
    asyncio.run(arena.enqueue(b.id, uid))

    out = asyncio.run(arena.run_once())
    mine = [e for e in out.entries if e.character_id in (a.id, b.id)]
    assert len(mine) == 1  # only one of the user's characters seated
    assert arena.queue_size == 1


def test_weighted_lottery_favors_high_miss_characters():
    # Statistical: a character carrying many misses should win the single seat far
    # more often than a fresh rival. Weight 1 vs 1+30 -> ~31x more likely.
    wins_high = 0
    trials = 60
    for seed in range(trials):
        store = MemoryStore()
        arena, _, _ = _lottery_arena(store, slots=1, seed=seed)
        fresh = make_char(store, "fresh", "Fresh", "rogue")
        veteran = make_char(store, "vet", "Vet", "monk")
        asyncio.run(arena.enqueue(fresh.id, fresh.user_id))
        asyncio.run(arena.enqueue(veteran.id, veteran.user_id))
        # Hand the veteran a long miss streak in the race bucket.
        for item in arena._queue:
            if item.character_id == veteran.id:
                item.misses = {"race": 30}
        out = asyncio.run(arena.run_once())
        if any(e.character_id == veteran.id for e in out.entries):
            wins_high += 1
    assert wins_high > trials * 0.8  # ~97% expected; generous margin for noise


def _lottery_monster_arena(store, *, slots: int, every_n: int, seed: int = 1):
    """Weighted lottery + monster rounds (moore engine). The tier-1 monster is made
    unkillable so the ladder stays pinned at tier 1 and the miss bucket is stable."""
    from server.config import MonsterConfig

    arena, sink, cfg = build_arena(store, seed=seed)
    cfg.combat = replace(cfg.combat, engine="moore")
    cfg.queue = replace(cfg.queue, selection="weighted_lottery", miss_weight=1.0)
    cfg.round = replace(cfg.round, fighters_per_round=slots)
    tiers = dict(cfg.monsters.tiers)
    tiers[1] = replace(tiers[1], hp_pct_of_team=1e9)  # unkillable -> ladder stays at 1
    cfg.monsters = MonsterConfig(
        every_n=every_n, target_selection="random", max_tier=5, tiers=tiers
    )
    return arena, sink, cfg


def test_weighted_lottery_buckets_misses_by_monster_tier():
    # A fighter skipped on a Tier-1 monster round accrues its miss in the "tier1"
    # bucket, not the shared "race" bucket (R4 per-tier priority).
    store = MemoryStore()
    arena, _, _ = _lottery_monster_arena(store, slots=1, every_n=1)
    chars = [make_char(store, f"u{i}", f"C{i}", "fighter") for i in range(3)]
    for c in chars:
        asyncio.run(arena.enqueue(c.id, c.user_id))

    asyncio.run(arena.run_once())  # tier-1 monster round
    assert arena._queue  # some held over
    for item in arena._queue:
        assert item.misses.get("tier1") == 1
        assert "race" not in item.misses  # a race skip would land elsewhere


def test_weighted_lottery_race_and_tier_buckets_are_independent():
    # every_n=2 -> round 1 is a race, round 2 is a Tier-1 monster. A fighter skipped
    # in both carries a separate miss in each bucket, proving they don't cross-count.
    store = MemoryStore()
    arena, _, _ = _lottery_monster_arena(store, slots=1, every_n=2)
    chars = [make_char(store, f"u{i}", f"C{i}", "fighter") for i in range(3)]
    for c in chars:
        asyncio.run(arena.enqueue(c.id, c.user_id))

    asyncio.run(arena.run_once())  # race round
    asyncio.run(arena.run_once())  # tier-1 monster round
    survivors = list(arena._queue)
    assert survivors  # at least one fighter skipped both rounds
    twice_skipped = survivors[0]
    assert twice_skipped.misses.get("race") == 1
    assert twice_skipped.misses.get("tier1") == 1


def test_fighter_view_and_round_start_gate_gear_on_the_shop():
    from server import events
    from server.models import Entry

    # Unit: fighter_view mirrors the entry's equipment for the overlay paper-doll.
    e = Entry(
        slot=0, character_id=1, is_npc=False, dummy_sprite="d", name="X",
        class_name="rogue", sprite_set="rogue_01", owner="brian",
        equipment={"weapon": "flame_sword", "armor": "plate"},
    )
    assert events.fighter_view(e)["gear"] == {"weapon": "flame_sword", "armor": "plate"}

    # Integration: gear only reaches the wire when the shop is live.
    store = MemoryStore()
    arena, sink, cfg = build_arena(store)
    ch = make_char(store, "brian", "Geared", "rogue")
    store.characters[ch.id].equipment = {"weapon": "flame_sword"}

    asyncio.run(arena.enqueue(ch.id, ch.user_id))
    asyncio.run(arena.run_once())  # shop off (default)
    off_view = _fighter_named(sink, "Geared")
    assert off_view is not None and off_view["gear"] == {}

    cfg.shop = replace(cfg.shop, enabled=True)
    asyncio.run(arena.enqueue(ch.id, ch.user_id))
    asyncio.run(arena.run_once())  # shop on
    on_view = _fighter_named(sink, "Geared")
    assert on_view is not None and on_view["gear"] == {"weapon": "flame_sword"}


def _fighter_named(sink, name):
    """The most recent round_start's fighter view with ``name`` (real characters
    have unique names; NPC fill is prefixed "[NPC]"), or None."""
    starts = sink.of_type("round_start")
    if not starts:
        return None
    for f in starts[-1]["fighters"]:
        if f.get("name") == name:
            return f
    return None


# ---------------------------------------------------------------------------
# Retirement & lifespan (hard rule #7)
# ---------------------------------------------------------------------------
def test_retirement_at_lifespan_boundary():
    store = MemoryStore()
    arena, _, cfg = build_arena(store)
    ch = make_char(store, "amy", "Veteran", "fighter")
    store.characters[ch.id].battles_fought = cfg.round.lifespan_battles - 1  # 19

    asyncio.run(arena.enqueue(ch.id, ch.user_id))
    asyncio.run(arena.run_once())

    updated = store.characters[ch.id]
    assert updated.battles_fought == cfg.round.lifespan_battles
    assert updated.is_retired is True
    assert updated.retired_at is not None

    # A retired character can no longer be selected.
    asyncio.run(arena.enqueue(ch.id, ch.user_id))
    out = asyncio.run(arena.run_once())
    assert all(e.character_id != ch.id for e in out.entries)


def test_recover_voids_unfinished_round():
    store = MemoryStore()
    build_arena(store)
    rid = asyncio.run(store.create_round("arena", None))  # started, never ended
    voided = asyncio.run(store.recover())
    assert rid in voided
    assert store.rounds[rid]["is_voided"] is True


class _FlakyStore(MemoryStore):
    """Fails the first real (non-void) finalize to simulate a mid-round crash."""

    def __init__(self) -> None:
        super().__init__()
        self._fail_next = True

    async def finalize_round(self, result: RoundResult) -> None:
        if not result.voided and self._fail_next:
            self._fail_next = False
            raise RuntimeError("simulated crash during results")
        await super().finalize_round(result)


def test_round_crash_voids_and_consumes_no_lifespan():
    store = _FlakyStore()
    arena, _, _ = build_arena(store, seed=3)
    ch = make_char(store, "cid", "Zed", "wizard")
    asyncio.run(arena.enqueue(ch.id, ch.user_id))

    outcome = asyncio.run(arena.run_once())

    assert outcome.voided is True
    assert store.rounds[outcome.round_id]["is_voided"] is True
    assert store.characters[ch.id].battles_fought == 0  # lifespan not consumed


# ---------------------------------------------------------------------------
# Pause / resume (mod control, PLAN.md §10)
# ---------------------------------------------------------------------------
def test_pause_halts_loop_until_resume():
    async def body():
        store = MemoryStore()
        arena, sink, _ = build_arena(store)
        arena.pause()
        task = asyncio.create_task(arena.run(max_rounds=1))
        await asyncio.sleep(0.02)  # let the loop reach the paused wait
        assert not task.done()  # paused before starting a round
        arena.resume()
        await asyncio.wait_for(task, timeout=2)
        assert len(sink.of_type("round_end")) == 1

    asyncio.run(body())


# ---------------------------------------------------------------------------
# Open / close gate (mod !start / !close): the arena boots closed unless
# [arena].open_on_launch is set, and !close idles it after the current round.
# ---------------------------------------------------------------------------
def _close_on(sink: RecordingSink, arena: Arena, event_type: str) -> None:
    """Patch the sink so the arena closes when the given event type is emitted
    (models a mod typing !close mid-round)."""
    orig_emit = sink.emit

    async def emit_and_close(event: dict) -> None:
        await orig_emit(event)
        if event.get("type") == event_type:
            arena.close()

    sink.emit = emit_and_close  # type: ignore[method-assign]


async def _wait_for_phase(arena: Arena, phase: Phase, tries: int = 2000) -> None:
    for _ in range(tries):
        if arena.phase == phase:
            return
        await asyncio.sleep(0)
    raise AssertionError(f"arena never reached {phase} (stuck at {arena.phase})")


def test_closed_boot_emits_idle_and_runs_no_rounds():
    async def body():
        store = MemoryStore()
        arena, sink, _ = build_arena(store, open_on_launch=False)
        assert not arena.is_open
        assert arena.phase == Phase.IDLE  # pre-run snapshot already reads idle
        task = asyncio.create_task(arena.run(max_rounds=1))
        await asyncio.sleep(0.02)  # let the loop reach the idle wait
        assert not task.done()
        assert sink.of_type("round_start") == []
        assert any(e["phase"] == "idle" for e in sink.of_type("countdown"))
        assert arena.phase == Phase.IDLE
        arena.stop()
        await asyncio.wait_for(task, timeout=2)

    asyncio.run(body())


def test_start_opens_the_arena_and_a_round_runs():
    async def body():
        store = MemoryStore()
        arena, sink, _ = build_arena(store, open_on_launch=False)
        task = asyncio.create_task(arena.run(max_rounds=1))
        await asyncio.sleep(0.02)
        assert not task.done()
        arena.open()  # mod !start
        await asyncio.wait_for(task, timeout=2)
        assert len(sink.of_type("round_end")) == 1

    asyncio.run(body())


def test_close_takes_effect_after_the_current_round():
    async def body():
        store = MemoryStore()
        arena, sink, _ = build_arena(store)
        _close_on(sink, arena, "round_start")  # mod closes mid-round
        task = asyncio.create_task(arena.run())
        await _wait_for_phase(arena, Phase.IDLE)
        # The in-flight round completed (never interrupted), then no new round.
        assert len(sink.of_type("round_start")) == 1
        assert len(sink.of_type("round_end")) == 1
        arena.stop()
        await asyncio.wait_for(task, timeout=2)

    asyncio.run(body())


def test_queue_survives_close_and_seats_on_reopen():
    async def body():
        store = MemoryStore()
        arena, sink, _ = build_arena(store, open_on_launch=False)
        ch = make_char(store, "brian", "Thorak", "barbarian")
        await arena.enqueue(ch.id, ch.user_id)
        task = asyncio.create_task(arena.run(max_rounds=1))
        await asyncio.sleep(0.02)
        assert arena.is_queued(ch.id)  # queue preserved while closed
        arena.open()
        await asyncio.wait_for(task, timeout=2)
        names = [f["name"] for f in sink.of_type("round_start")[0]["fighters"]]
        assert "Thorak" in names

    asyncio.run(body())


def test_snapshot_while_idle_has_no_stale_round():
    async def body():
        store = MemoryStore()
        arena, sink, _ = build_arena(store)
        _close_on(sink, arena, "round_end")  # close right as the round completes
        task = asyncio.create_task(arena.run())
        await _wait_for_phase(arena, Phase.IDLE)
        snap = arena.snapshot()
        assert snap["phase"] == "idle"
        assert snap["round"] is None  # regression: _current cleared on close
        assert snap["fighters"] == []
        arena.stop()
        await asyncio.wait_for(task, timeout=2)

    asyncio.run(body())


def test_stop_unblocks_a_closed_arena():
    async def body():
        store = MemoryStore()
        arena, sink, _ = build_arena(store, open_on_launch=False)
        task = asyncio.create_task(arena.run())
        await asyncio.sleep(0.02)
        arena.stop()  # must not hang on the closed gate
        await asyncio.wait_for(task, timeout=2)
        assert sink.of_type("round_start") == []

    asyncio.run(body())


# ---------------------------------------------------------------------------
# Round kind on the wire (overlay layout cue)
# ---------------------------------------------------------------------------
def test_round_start_carries_kind_race():
    store = MemoryStore()
    arena, sink, _ = build_arena(store)
    asyncio.run(arena.run_once())
    start = sink.of_type("round_start")[0]
    assert start["kind"] == "race"
    assert start["tier"] is None


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------
def test_same_seed_reproduces_round():
    def run_seeded():
        store = MemoryStore()
        arena, sink, _ = build_arena(store, seed=99)
        asyncio.run(arena.run_once())
        return [(e["slot"], e["roll"], e["damage"]) for e in sink.of_type("attack")]

    assert run_seeded() == run_seeded()


# ---------------------------------------------------------------------------
# MooreDnD engine (R1) — the arena runs a full round under the new combat math
# ---------------------------------------------------------------------------
def _moore_arena(store: MemoryStore, seed: int = 5) -> tuple[Arena, RecordingSink, Config]:
    cfg = Config.load(GAME_CONFIG)
    cfg.combat = replace(cfg.combat, engine="moore")
    cfg.round = replace(cfg.round, event_chance=0.0)
    sink = RecordingSink()
    arena = Arena(cfg, store, sink, rng=random.Random(seed), sleep=_nosleep, now=_fixed_now)
    return arena, sink, cfg


def test_moore_engine_runs_a_full_round():
    store = MemoryStore()
    arena, sink, cfg = _moore_arena(store)
    n = cfg.round.fighters_per_round
    ch = make_char(store, "brian", "Thorak", "barbarian")
    asyncio.run(arena.enqueue(ch.id, ch.user_id))
    outcome = asyncio.run(arena.run_once())

    assert not outcome.voided and len(outcome.entries) == n
    attacks = sink.of_type("attack")
    assert attacks, "moore combat must emit attacks"
    # Every fighter (real + NPC fill) swings and lands hits under the new math.
    hit_dmgs = [a["damage"] for a in attacks if not a["miss"]]
    assert hit_dmgs and all(d > 0 for d in hit_dmgs)
    # Barbarian STR 15 -> AP ~ 15*25*coeff ~ 370 +/- 150 variance; hits sit on the
    # 0-1000 core-stat scale (a plain round, NOT the classic x10 display scale).
    assert max(hit_dmgs) < 1500
    ends = sink.of_type("round_end")
    assert len(ends) == 1 and len(ends[0]["standings"]) == n
    # Real character's aggregates were persisted from the moore round.
    updated = store.characters[ch.id]
    assert updated.battles_fought == 1 and updated.lifetime_damage > 0


def test_moore_round_is_deterministic_per_seed():
    def run():
        store = MemoryStore()
        arena, sink, _ = _moore_arena(store, seed=17)
        asyncio.run(arena.run_once())
        return [(e["slot"], e["roll"], e["damage"]) for e in sink.of_type("attack")]

    assert run() == run()


def test_moore_hits_use_to_hit_vs_dummy_ac():
    # With the low dummy AC, misses should be rare (near-auto, R1 §3), unlike a
    # world where every low roll whiffs.
    store = MemoryStore()
    arena, sink, _ = _moore_arena(store, seed=3)
    asyncio.run(arena.run_once())
    attacks = sink.of_type("attack")
    miss_rate = sum(a["miss"] for a in attacks) / len(attacks)
    assert miss_rate < 0.15  # near-automatic vs the dummy


# ---------------------------------------------------------------------------
# R4 monster battles (docs/R4_R6_plan.md)
# ---------------------------------------------------------------------------
def _monster_arena(store, *, tier1_hp_pct: float, seed: int = 5):
    """Moore engine + monsters enabled every round; tier-1 HP overridden so the
    outcome is deterministic (tiny -> victory, huge -> defeat)."""
    from server.config import MonsterConfig

    cfg = Config.load(GAME_CONFIG)
    cfg.combat = replace(cfg.combat, engine="moore")
    cfg.round = replace(cfg.round, event_chance=0.0)
    tiers = dict(cfg.monsters.tiers)
    tiers[1] = replace(tiers[1], hp_pct_of_team=tier1_hp_pct)
    cfg.monsters = MonsterConfig(every_n=1, target_selection="random", max_tier=5, tiers=tiers)
    sink = RecordingSink()
    arena = Arena(cfg, store, sink, rng=random.Random(seed), sleep=_nosleep, now=_fixed_now)
    return arena, sink, cfg


def test_monster_round_victory_awards_mvp_and_climbs_ladder():
    store = MemoryStore()
    arena, sink, _ = _monster_arena(store, tier1_hp_pct=0.001)  # trivially killable
    ch = make_char(store, "brian", "Thorak", "barbarian")
    asyncio.run(arena.enqueue(ch.id, ch.user_id))
    asyncio.run(arena.run_once())

    assert sink.of_type("monster_spawn"), "monster round should announce a spawn"
    results = sink.of_type("team_result")
    assert len(results) == 1 and results[0]["victory"] is True

    updated = store.characters[ch.id]
    assert updated.battles_fought == 1  # monster rounds count toward lifespan
    # The lone real fighter out-damages NPCs -> MVP -> takes the win.
    assert updated.wins == 1 and updated.losses == 0
    assert asyncio.run(store.get_game_state("monster_ladder_tier")) == "2"  # climbed


def test_monster_round_start_carries_kind_tier_and_snapshot_monster():
    store = MemoryStore()
    arena, sink, _ = _monster_arena(store, tier1_hp_pct=0.001)
    asyncio.run(arena.run_once())

    start = sink.of_type("round_start")[0]
    assert start["kind"] == "monster"
    assert start["tier"] == 1
    # A late joiner's sync (snapshot) carries the monster layout too.
    snap = arena.snapshot()
    assert snap["round"]["kind"] == "monster"
    assert snap["round"]["tier"] == 1
    assert snap["round"]["monster"]["label"]
    assert snap["round"]["monster"]["hp"] > 0


def test_monster_round_defeat_is_a_loss_and_resets_ladder():
    store = MemoryStore()
    # Seed the ladder high so a defeat visibly resets it to 1.
    asyncio.run(store.set_game_state("monster_ladder_tier", "4"))
    arena, sink, _ = _monster_arena(store, tier1_hp_pct=1e9)  # unkillable
    ch = make_char(store, "amy", "Vala", "wizard")
    asyncio.run(arena.enqueue(ch.id, ch.user_id))
    asyncio.run(arena.run_once())

    results = sink.of_type("team_result")
    assert len(results) == 1 and results[0]["victory"] is False
    updated = store.characters[ch.id]
    assert updated.wins == 0 and updated.losses == 1  # nobody wins on defeat
    assert asyncio.run(store.get_game_state("monster_ladder_tier")) == "1"  # reset


def test_monster_round_wins_losses_invariant_holds():
    # Every real fighter takes exactly one of win/loss (preserves wins+losses ==
    # battles_fought), even with several players in the round.
    store = MemoryStore()
    arena, _, _ = _monster_arena(store, tier1_hp_pct=0.001)
    chars = [make_char(store, f"p{i}", f"H{i}", "fighter") for i in range(4)]
    for c in chars:
        asyncio.run(arena.enqueue(c.id, c.user_id))
    asyncio.run(arena.run_once())

    winners = sum(store.characters[c.id].wins for c in chars)
    losers = sum(store.characters[c.id].losses for c in chars)
    assert winners == 1  # exactly one MVP
    assert winners + losers == len(chars)  # everyone got one outcome


def test_monster_round_is_deterministic_per_seed():
    def run():
        store = MemoryStore()
        arena, sink, _ = _monster_arena(store, tier1_hp_pct=0.5, seed=11)
        make = make_char(store, "brian", "Thorak", "barbarian")
        asyncio.run(arena.enqueue(make.id, make.user_id))
        asyncio.run(arena.run_once())
        return sink.of_type("team_result")[0]["victory"], [
            (a["slot"], a["roll"], a["damage"]) for a in sink.of_type("attack")
        ]

    assert run() == run()
