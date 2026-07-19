"""Seasons + Hall of Fame tests (PLAN.md §8). Season leaderboards reset each
calendar month; the Hall of Fame persists all-time records (hard rule #11: do
NOT equalize which classes hold what)."""

from __future__ import annotations

import asyncio
import random
from datetime import UTC, datetime
from pathlib import Path

from server.adapters import InboundMessage, MessageRouter
from server.arena import Arena
from server.commands import GameCommands
from server.config import Config
from server.events import RecordingSink
from server.models import HoFCandidate
from server.store import MemoryStore

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GAME_CONFIG = PROJECT_ROOT / "config" / "game.toml"
STATS = {"STR": 15, "DEX": 14, "CON": 13, "INT": 12, "WIS": 11, "CHA": 10}


async def _nosleep(_seconds: float) -> None:
    return None


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Season rollover
# ---------------------------------------------------------------------------
def test_current_season_is_stable_within_a_month_and_rolls_over():
    store = MemoryStore()
    jan_a = _run(store.ensure_current_season(datetime(2026, 1, 5, tzinfo=UTC)))
    jan_b = _run(store.ensure_current_season(datetime(2026, 1, 28, tzinfo=UTC)))
    feb = _run(store.ensure_current_season(datetime(2026, 2, 1, tzinfo=UTC)))
    dec = _run(store.ensure_current_season(datetime(2026, 12, 31, tzinfo=UTC)))
    jan_next_year = _run(store.ensure_current_season(datetime(2027, 1, 1, tzinfo=UTC)))

    assert jan_a == jan_b  # same month -> same season
    assert feb != jan_a  # new month -> new season
    assert len({jan_a, feb, dec, jan_next_year}) == 4
    assert store.seasons[dec]["ends_at"] == datetime(2027, 1, 1, tzinfo=UTC)  # year wrap


# ---------------------------------------------------------------------------
# Season leaderboards aggregate a season's rounds
# ---------------------------------------------------------------------------
def _arena(store: MemoryStore, now: datetime, seed: int = 5):
    cfg = Config.load(GAME_CONFIG)
    return Arena(
        cfg, store, RecordingSink(), rng=random.Random(seed), sleep=_nosleep, now=lambda: now
    )


def test_season_leaderboard_and_hall_of_fame_populate_from_a_round():
    store = MemoryStore()
    now = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)
    uid = store.add_user("brian")
    ch = store.create_character(
        user_id=uid, name="Thorak", class_name="barbarian", race="human",
        stats=dict(STATS), sprite_set="barb_01",
    )
    arena = _arena(store, now)
    _run(arena.enqueue(ch.id, ch.user_id))
    _run(arena.run_once())

    season_id = _run(store.ensure_current_season(now))
    board = _run(store.season_leaderboard(season_id, "damage", 3))
    assert any(r.name == "Thorak" and r.value > 0 for r in board)

    hof = _run(store.hall_of_fame())
    keys = {r.record_key for r in hof}
    assert {"highest_hit", "highest_round", "most_damage"} <= keys
    assert all(r.character_name == "Thorak" for r in hof)  # only real fighter this round


def test_season_leaderboards_are_scoped_to_their_season():
    store = MemoryStore()
    uid = store.add_user("brian")
    ch = store.create_character(
        user_id=uid, name="Thorak", class_name="barbarian", race="human",
        stats=dict(STATS), sprite_set="barb_01",
    )
    # A round in March, then a round in April: each season sees only its own round.
    for month in (3, 4):
        arena = _arena(store, datetime(2026, month, 10, tzinfo=UTC))
        _run(arena.enqueue(ch.id, ch.user_id))
        _run(arena.run_once())

    march = _run(store.ensure_current_season(datetime(2026, 3, 1, tzinfo=UTC)))
    april = _run(store.ensure_current_season(datetime(2026, 4, 1, tzinfo=UTC)))
    assert march != april
    march_board = _run(store.season_leaderboard(march, "damage", 3))
    april_board = _run(store.season_leaderboard(april, "damage", 3))
    # Thorak appears in each, but the totals are per-season (one round each), so
    # neither board's value is the sum of both rounds.
    assert march_board and april_board
    combined = _run(store.top_by_damage(3))  # lifetime spans both rounds
    assert combined[0].lifetime_damage > march_board[0].value


# ---------------------------------------------------------------------------
# Hall of Fame keeps only records that are beaten
# ---------------------------------------------------------------------------
def test_hall_of_fame_only_updates_on_a_new_record():
    store = MemoryStore()
    uid = store.add_user("amy")
    a = store.create_character(
        user_id=uid, name="Ada", class_name="wizard", race="human",
        stats=dict(STATS), sprite_set="wizard_01",
    )
    b = store.create_character(
        user_id=uid, name="Bo", class_name="monk", race="human",
        stats=dict(STATS), sprite_set="monk_01",
    )
    _run(store.update_hall_of_fame([HoFCandidate("highest_hit", a.id, 500.0)]))
    _run(store.update_hall_of_fame([HoFCandidate("highest_hit", b.id, 300.0)]))  # lower -> ignored
    hof = {r.record_key: r for r in _run(store.hall_of_fame())}
    assert hof["highest_hit"].character_name == "Ada" and hof["highest_hit"].value == 500.0

    _run(store.update_hall_of_fame([HoFCandidate("highest_hit", b.id, 800.0)]))  # higher wins
    hof = {r.record_key: r for r in _run(store.hall_of_fame())}
    assert hof["highest_hit"].character_name == "Bo" and hof["highest_hit"].value == 800.0


# ---------------------------------------------------------------------------
# !hof command rotates through the records
# ---------------------------------------------------------------------------
def test_hof_command_rotates_one_record_per_call():
    store = MemoryStore()
    uid = store.add_user("brian")
    ch = store.create_character(
        user_id=uid, name="Thorak", class_name="barbarian", race="human",
        stats=dict(STATS), sprite_set="barb_01",
    )
    _run(store.update_hall_of_fame([
        HoFCandidate("highest_hit", ch.id, 840.0),
        HoFCandidate("most_wins", ch.id, 7),
    ]))
    cfg = Config.load(GAME_CONFIG)
    arena = Arena(cfg, store, RecordingSink(), sleep=_nosleep)
    clock = [10_000.0]  # advanced past the 3s global cooldown between calls
    cmds = GameCommands(cfg, store, arena, now=lambda: datetime.fromtimestamp(clock[0], tz=UTC))
    router = MessageRouter(cmds, RecordingSink())

    def hof():
        clock[0] += 4.0
        msg = InboundMessage(
            platform="twitch", platform_user_id="u1", display_name="Brian",
            text="!hof", timestamp=datetime.fromtimestamp(clock[0], tz=UTC), login="brian",
        )
        return _run(router.dispatch(msg))[0]

    first, second, third = hof(), hof(), hof()
    assert "Biggest Hit" in first and "840" in first and "Thorak" in first
    assert "Most Wins" in second and " 7 " in f" {second} "
    assert third == first  # wraps around (two records)


def test_hof_command_when_empty():
    store = MemoryStore()
    cfg = Config.load(GAME_CONFIG)
    arena = Arena(cfg, store, RecordingSink(), sleep=_nosleep)
    router = MessageRouter(GameCommands(cfg, store, arena), RecordingSink())
    msg = InboundMessage(
        platform="twitch", platform_user_id="u1", display_name="Brian",
        text="!hof", timestamp=datetime(2026, 3, 1, tzinfo=UTC), login="brian",
    )
    assert "No Hall of Fame records yet" in _run(router.dispatch(msg))[0]
