"""EventSub reward tests (PLAN.md §6.2): idempotency + each redemption effect +
support gold, and the command-side effects (bonus slots, priority, reroll).
The twitchio EventSub edge (eventsub.py) needs live verification and isn't tested."""

from __future__ import annotations

import asyncio
import random
from datetime import UTC, datetime
from pathlib import Path

from server.arena import Arena
from server.commands import CREATE_COOLDOWN_S, GameCommands
from server.config import Config
from server.events import RecordingSink
from server.rewards import RedemptionEvent, RewardRouter, SupportEvent
from server.store import TOKEN_BONUS_SLOTS, TOKEN_PRIORITY, TOKEN_REROLL, MemoryStore

GAME_CONFIG = Path(__file__).resolve().parents[1] / "config" / "game.toml"
CFG = Config.load(GAME_CONFIG)


def _run(coro):
    return asyncio.run(coro)


async def _nosleep(_seconds: float) -> None:
    return None


def _uid(store: MemoryStore, login: str) -> int:
    return next(u for u, d in store.users.items() if d["login"] == login)


def _redeem(title: str, *, event_id: str = "e1", uid: str = "u1", login: str = "alice"):
    return RedemptionEvent(
        platform="twitch", platform_user_id=uid, display_name=login.title(),
        login=login, reward_title=title, event_id=event_id,
    )


# ---------------------------------------------------------------------------
# RewardRouter: redemptions, idempotency, support gold
# ---------------------------------------------------------------------------
def test_each_redemption_grants_its_token():
    cases = {
        "Extra Character Slot": TOKEN_BONUS_SLOTS,
        "Stat Reroll": TOKEN_REROLL,
        "Priority Queue Token": TOKEN_PRIORITY,
    }
    for i, (title, kind) in enumerate(cases.items()):
        store, sink = MemoryStore(), RecordingSink()
        rr = RewardRouter(CFG, store, sink)
        _run(rr.handle_redemption(_redeem(title, event_id=f"e{i}")))
        assert _run(store.get_tokens(_uid(store, "alice"), kind)) == 1
        assert sink.of_type("ticker")[-1]["kind"] == "reward"


def test_redelivery_of_the_same_event_is_a_noop():
    store, sink = MemoryStore(), RecordingSink()
    rr = RewardRouter(CFG, store, sink)
    _run(rr.handle_redemption(_redeem("Stat Reroll", event_id="dup")))
    _run(rr.handle_redemption(_redeem("Stat Reroll", event_id="dup")))  # Twitch resend
    assert _run(store.get_tokens(_uid(store, "alice"), TOKEN_REROLL)) == 1  # granted once


def test_unmapped_reward_is_ignored():
    store, sink = MemoryStore(), RecordingSink()
    rr = RewardRouter(CFG, store, sink)
    _run(rr.handle_redemption(_redeem("Some Other Reward")))
    assert store.users == {} and not sink.of_type("ticker")


def test_support_event_grants_gold():
    store, sink = MemoryStore(starting_gold=0), RecordingSink()
    rr = RewardRouter(CFG, store, sink)
    e = SupportEvent(
        platform="twitch", platform_user_id="u1", display_name="Alice",
        login="alice", tier_value=3, event_id="s1",
    )
    _run(rr.handle_support(e))
    assert _run(store.get_gold(_uid(store, "alice"))) == 3 * CFG.rewards.gold_per_tier
    _run(rr.handle_support(e))  # redelivery
    assert _run(store.get_gold(_uid(store, "alice"))) == 3 * CFG.rewards.gold_per_tier


# ---------------------------------------------------------------------------
# Command-side effects
# ---------------------------------------------------------------------------
def _harness():
    store = MemoryStore()
    clock = [10_000.0]
    now = lambda: datetime.fromtimestamp(clock[0], tz=UTC)  # noqa: E731
    arena = Arena(CFG, store, RecordingSink(), rng=random.Random(2), sleep=_nosleep, now=now)
    cmds = GameCommands(CFG, store, arena, rng=random.Random(3), now=now)
    return store, arena, cmds, clock


def _do(cmds, clock, text, gap=4.0, uid="u1", login="brian"):
    from server.adapters import InboundMessage

    clock[0] += gap
    m = InboundMessage(
        platform="twitch", platform_user_id=uid, display_name=login.title(),
        text=text, timestamp=datetime.fromtimestamp(clock[0], tz=UTC), login=login,
    )
    return _run(cmds.handle(m))


def test_extra_slot_token_allows_one_more_character():
    store, _arena, cmds, clock = _harness()
    uid = _run(store.register_user("twitch", "u1", "brian", "Brian"))
    _run(store.grant_tokens(uid, TOKEN_BONUS_SLOTS, 1))  # base limit 3 -> 4
    for name in ("A", "B", "C", "D"):
        out = _do(cmds, clock, f"!create fighter human {name}", gap=CREATE_COOLDOWN_S + 1)
        assert out and out[0].kind == "create"
    assert len(store.characters) == 4  # the extra slot let the 4th through
    fifth = _do(cmds, clock, "!create fighter human E", gap=CREATE_COOLDOWN_S + 1)
    assert fifth[0].kind == "error" and "already have 4" in fifth[0].text


def test_priority_token_jumps_the_queue():
    store, arena, cmds, clock = _harness()
    # user A creates + enters
    _do(cmds, clock, "!create rogue elf Scout", uid="a", login="ann")
    _do(cmds, clock, "!enter", uid="a", login="ann")
    # user B creates, gets a priority token, and enters -> jumps to the front
    _do(cmds, clock, "!create monk human Chi", uid="b", login="bob")
    bob = _run(store.register_user("twitch", "b", "bob", "Bob"))
    _run(store.grant_tokens(bob, TOKEN_PRIORITY, 1))
    out = _do(cmds, clock, "!enter", uid="b", login="bob")
    assert "priority" in out[0].text and "position 1" in out[0].text
    assert _run(store.get_tokens(bob, TOKEN_PRIORITY)) == 0  # spent


def test_reroll_consumes_a_token_and_needs_one():
    store, _arena, cmds, clock = _harness()
    _do(cmds, clock, "!create wizard human Merlin")
    uid = _uid(store, "brian")
    # no token yet
    assert "no stat-reroll tokens" in _do(cmds, clock, "!reroll")[0].text
    _run(store.grant_tokens(uid, TOKEN_REROLL, 1))
    ok = _do(cmds, clock, "!reroll")
    assert ok[0].kind == "create" and "rerolled" in ok[0].text
    assert _run(store.get_tokens(uid, TOKEN_REROLL)) == 0  # spent
