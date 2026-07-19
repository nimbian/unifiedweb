"""Chat betting tests (PLAN.md §6.6): pari-mutuel math, gold wallet + bets,
the ROSTER_LOCK betting window, settlement, and per-round accrual."""

from __future__ import annotations

import asyncio
import random
from datetime import UTC, datetime
from pathlib import Path

import pytest

from server import rules
from server.adapters import InboundMessage, MessageRouter
from server.arena import Arena
from server.commands import GameCommands
from server.config import Config
from server.economy import Presence
from server.events import RecordingSink
from server.store import BET_EXISTS, BET_INSUFFICIENT, BET_OK, MemoryStore

GAME_CONFIG = Path(__file__).resolve().parents[1] / "config" / "game.toml"


def _run(coro):
    return asyncio.run(coro)


async def _nosleep(_seconds: float) -> None:
    return None


# ---------------------------------------------------------------------------
# Pari-mutuel math (pure)
# ---------------------------------------------------------------------------
def test_parimutuel_winners_split_pool_in_proportion():
    bets = [(1, 0, 100), (2, 1, 100), (3, 0, 200)]  # slot 0 wins
    payouts = rules.settle_parimutuel(bets, winning_slot=0, rake=0.0)
    # pool 400, winning pool 300: user1 100*400/300≈133, user3 200*400/300≈267
    assert payouts == {1: 133, 3: 267}
    assert sum(payouts.values()) == pytest.approx(400, abs=1)  # whole pool paid out


def test_parimutuel_refunds_when_nobody_backed_the_winner():
    payouts = rules.settle_parimutuel([(1, 2, 50), (2, 3, 50)], winning_slot=0)
    assert payouts == {1: 50, 2: 50}  # stakes refunded, gold not destroyed


def test_parimutuel_rake_is_taken_off_the_top():
    payouts = rules.settle_parimutuel([(1, 0, 100), (2, 1, 100)], winning_slot=0, rake=0.10)
    assert payouts == {1: 180}  # distributable 180, sole winner takes it


def test_parimutuel_no_bets():
    assert rules.settle_parimutuel([], winning_slot=0) == {}


# ---------------------------------------------------------------------------
# Gold wallet + place_bet
# ---------------------------------------------------------------------------
def test_place_bet_deducts_gold_and_blocks_a_second_bet():
    store = MemoryStore(starting_gold=100)
    uid = store.add_user("brian")
    rid = _run(store.create_round("arena", None))
    assert _run(store.place_bet(rid, uid, 0, 40)) == BET_OK
    assert _run(store.get_gold(uid)) == 60
    assert _run(store.place_bet(rid, uid, 1, 10)) == BET_EXISTS
    assert _run(store.get_gold(uid)) == 60  # second bet didn't deduct


def test_place_bet_rejects_insufficient_gold():
    store = MemoryStore(starting_gold=30)
    uid = store.add_user("brian")
    rid = _run(store.create_round("arena", None))
    assert _run(store.place_bet(rid, uid, 0, 100)) == BET_INSUFFICIENT
    assert _run(store.get_gold(uid)) == 30


def test_settle_bets_pays_winners_and_conserves_gold():
    store = MemoryStore(starting_gold=100)
    a, b = store.add_user("a"), store.add_user("b")
    rid = _run(store.create_round("arena", None))
    _run(store.place_bet(rid, a, 0, 50))  # backs the winner
    _run(store.place_bet(rid, b, 1, 50))  # backs a loser
    bets = _run(store.bets_for_round(rid))
    payouts = rules.settle_parimutuel([(x.user_id, x.slot, x.amount) for x in bets], winning_slot=0)
    _run(store.settle_bets(rid, payouts))
    assert _run(store.get_gold(a)) == 150  # staked 50, won the 100 pool
    assert _run(store.get_gold(b)) == 50
    assert _run(store.get_gold(a)) + _run(store.get_gold(b)) == 200  # zero-rake: conserved


# ---------------------------------------------------------------------------
# Betting window + settlement through the arena/commands
# ---------------------------------------------------------------------------
def _harness():
    cfg = Config.load(GAME_CONFIG)
    store = MemoryStore(starting_gold=cfg.economy.starting_gold)
    clock = [10_000.0]
    now = lambda: datetime.fromtimestamp(clock[0], tz=UTC)  # noqa: E731
    arena = Arena(cfg, store, RecordingSink(), rng=random.Random(3), sleep=_nosleep, now=now)
    cmds = GameCommands(cfg, store, arena, now=now)
    router = MessageRouter(cmds, RecordingSink())
    return cfg, store, arena, router, clock


def _bet(router, clock, text, uid="u1", login="brian"):
    clock[0] += 4.0  # clear the global cooldown between commands
    msg = InboundMessage(
        platform="twitch", platform_user_id=uid, display_name=login.title(),
        text=text, timestamp=datetime.fromtimestamp(clock[0], tz=UTC), login=login,
    )
    return _run(router.dispatch(msg))


def test_bet_is_rejected_while_betting_is_closed():
    _, _, arena, router, clock = _harness()
    assert not arena.betting_open  # INTERMISSION at construction
    assert "betting is closed" in _bet(router, clock, "!bet 0 20")[0]


def test_bet_during_roster_lock_then_settles_on_round_end():
    cfg, store, arena, router, clock = _harness()
    ctx = _run(arena._roster_lock())  # lock a lineup; phase is now ROSTER_LOCK
    assert arena.betting_open

    reply = _bet(router, clock, "!bet 0 40")
    assert "bet 40 gold" in reply[0]
    bettor = next(u for u in store.users if store.users[u]["login"] == "brian")
    assert _run(store.get_gold(bettor)) == cfg.economy.starting_gold - 40  # staked

    _run(arena._combat(ctx))
    _run(arena._results(ctx))  # settles bets
    settled = [b for b in store.bets if b["round_id"] == ctx.round_id]
    assert settled and settled[0]["payout"] is not None  # bet was settled
    # A lone bettor is the whole pool, so their gold is conserved either way.
    assert _run(store.get_gold(bettor)) == cfg.economy.starting_gold


def test_bet_on_unknown_fighter_is_rejected():
    _, _, arena, router, clock = _harness()
    _run(arena._roster_lock())
    assert "no fighter" in _bet(router, clock, "!bet 99 10")[0]


# ---------------------------------------------------------------------------
# Per-round gold accrual (presence)
# ---------------------------------------------------------------------------
def test_accrual_pays_present_chatters_and_drains_presence():
    cfg = Config.load(GAME_CONFIG)
    store = MemoryStore(starting_gold=100)
    presence = Presence()
    presence.seen("twitch", "u1", "alice", "Alice")
    presence.seen("twitch", "u2", "bob", "Bob")
    presence.seen("twitch", "u1", "alice", "Alice")  # duplicate -> still one payout
    arena = Arena(cfg, store, RecordingSink(), sleep=_nosleep, presence=presence)

    _run(arena._accrue_gold())

    assert presence.active_count == 0  # drained
    golds = sorted(u["gold"] for u in store.users.values())
    assert golds == [100 + cfg.economy.gold_per_round] * 2  # both got the stipend once
