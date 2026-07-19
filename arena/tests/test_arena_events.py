"""Random arena event tests (PLAN.md §4.6). Pure rules with scripted RNG for
each event mechanic, plus one arena integration round with a forced event.
Balance is the simulator's job (``python -m server.sim --events``)."""

from __future__ import annotations

import asyncio
import random
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from server import rules
from server.arena import Arena
from server.config import NEUTRAL_RACE, ArenaEvent, Config, ConfigError, _parse_events
from server.events import RecordingSink
from server.store import MemoryStore

GAME_CONFIG = Path(__file__).resolve().parents[1] / "config" / "game.toml"
CFG = Config.load(GAME_CONFIG)
DMG = CFG.damage
BARB = CFG.classes["barbarian"]
STATS = {"STR": 15, "DEX": 14, "CON": 13, "INT": 12, "WIS": 11, "CHA": 10}


class ScriptRandom:
    """RNG returning scripted values so a single swing is fully determined."""

    def __init__(self, randints: list[int] | None = None, randoms: list[float] | None = None):
        self._randints = list(randints or [])
        self._randoms = list(randoms or [])

    def randint(self, a: int, b: int) -> int:
        return self._randints.pop(0)

    def random(self) -> float:
        return self._randoms.pop(0)


def _swing(event, passives=NEUTRAL_RACE, roll=10, randoms=None):
    state = rules.CombatState(lucky_left=passives.lucky_reroll_ones)
    return rules.resolve_race_attack(
        ScriptRandom([roll], randoms), 15, 12, BARB, DMG, passives, state, 0.0, event
    )


# ---------------------------------------------------------------------------
# Config parsing
# ---------------------------------------------------------------------------
def test_all_seven_events_parse_from_config():
    assert set(CFG.events) == {
        "fire", "blood_moon", "blessing", "curse", "fog", "rain", "crowd",
    }
    assert 0.0 <= CFG.round.event_chance <= 1.0
    # Owner standard (2026-07-05): every event is a flat damage mod at one of two
    # tiers — MINOR = +/-5%, MAJOR = +/-10%.
    minor = {"blessing", "crowd", "rain"}
    major = {"fire", "curse", "fog", "blood_moon"}
    for name in minor:
        assert abs(CFG.events[name].damage_mult - 1.0) == pytest.approx(0.05)
    for name in major:
        assert abs(CFG.events[name].damage_mult - 1.0) == pytest.approx(0.10)
    # Race hooks preserved.
    assert CFG.events["fire"].tag == "fire" and CFG.events["fire"].damage_mult > 1.0
    assert CFG.events["curse"].curse and CFG.events["curse"].damage_mult < 1.0
    assert CFG.events["blessing"].tag == "blessing"
    assert CFG.events["blood_moon"].tag == "blood_moon"
    assert CFG.arena_event("fire") is CFG.events["fire"]
    assert CFG.arena_event(None) is None and CFG.arena_event("nope") is None


def test_negative_event_multiplier_rejected():
    with pytest.raises(ConfigError):
        _parse_events({"bad": {"damage_mult": -0.5}})


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------
def test_pick_event_chance_zero_draws_nothing():
    # No rng draw at chance 0 (ScriptRandom would raise on an unexpected draw),
    # so configs with events disabled keep their exact rng streams.
    assert rules.pick_arena_event(ScriptRandom(), CFG.events, 0.0) is None


def test_pick_event_chance_one_always_picks():
    rng = random.Random(7)
    for _ in range(20):
        assert rules.pick_arena_event(rng, CFG.events, 1.0) in CFG.events.values()


# ---------------------------------------------------------------------------
# Per-event mechanics (scripted swings; magnitudes come from config)
# ---------------------------------------------------------------------------
def test_fire_multiplies_damage_globally():
    fire = CFG.events["fire"]
    base = _swing(None)
    assert _swing(fire).damage == pytest.approx(base.damage * fire.damage_mult)


def test_fire_grants_tiefling_its_event_bonus():
    fire = CFG.events["fire"]
    tief = CFG.race_passives("tiefling")
    base = _swing(None)
    expected = base.damage * fire.damage_mult * (1.0 + tief.event_damage_bonus)
    assert _swing(fire, tief).damage == pytest.approx(expected)


def test_curse_reduces_damage_but_dwarf_is_immune():
    curse = CFG.events["curse"]
    base = _swing(None)
    assert _swing(curse).damage == pytest.approx(base.damage * curse.damage_mult)
    dwarf = CFG.race_passives("dwarf")
    assert _swing(curse, dwarf).damage == pytest.approx(base.damage)  # rule §4.3


def test_minor_and_major_events_are_flat_damage_mods():
    # Owner standard: minor = +/-5%, major = +/-10% flat damage.
    base = _swing(None)
    assert _swing(CFG.events["blessing"]).damage == pytest.approx(base.damage * 1.05)  # minor +
    assert _swing(CFG.events["crowd"]).damage == pytest.approx(base.damage * 1.05)     # minor +
    assert _swing(CFG.events["rain"]).damage == pytest.approx(base.damage * 0.95)      # minor -
    assert _swing(CFG.events["fog"]).damage == pytest.approx(base.damage * 0.90)       # major -
    assert _swing(CFG.events["blood_moon"]).damage == pytest.approx(base.damage * 0.90)  # major -


def test_blood_moon_bane_still_gives_tiefling_its_resist_bonus():
    bm = CFG.events["blood_moon"]
    tief = CFG.race_passives("tiefling")
    base = _swing(None)
    # -10% for all, but Tiefling's +5% event bonus partially offsets: 0.90 * 1.05.
    assert _swing(bm, tief).damage == pytest.approx(base.damage * 0.90 * 1.05)


# The crit_damage_mult / crit_chance_bonus / no_miss knobs are unused by the
# current +/-5/10 event set but still supported for future events — cover them
# with synthetic events so the resolve_race_attack branches stay tested.
def test_no_miss_capability_still_supported():
    ev = ArenaEvent(name="x", label="X", no_miss=True)
    res = _swing(ev, roll=1)
    assert not res.is_miss and res.roll == 2 and res.damage > 0.0
    assert _swing(None, roll=1).is_miss  # without it a 1 still whiffs


def test_crit_damage_mult_capability_still_supported():
    ev = ArenaEvent(name="x", label="X", crit_damage_mult=0.5)
    base = _swing(None, roll=20)
    assert _swing(ev, roll=20).damage == pytest.approx(base.damage * 0.5)


def test_crit_chance_bonus_capability_still_supported():
    ev = ArenaEvent(name="x", label="X", crit_chance_bonus=-0.03)
    elf = CFG.race_passives("elf")
    assert elf.crit_chance_bonus + ev.crit_chance_bonus == pytest.approx(0.0)
    res = _swing(ev, elf, roll=10, randoms=[])
    assert res.damage == pytest.approx(_swing(None).damage)


def test_event_none_is_identical_to_no_event_path():
    for roll in range(1, 21):
        with_none = _swing(None, roll=roll)
        plain = rules.resolve_attack(roll, 15, 12, BARB, DMG)
        assert with_none.damage == pytest.approx(plain.damage)
        assert (with_none.is_crit, with_none.is_miss) == (plain.is_crit, plain.is_miss)


def test_ability_bursts_feel_the_event_too():
    fire = CFG.events["fire"]
    tief = CFG.race_passives("tiefling")
    assert rules.apply_event_damage(100.0, fire, NEUTRAL_RACE) == pytest.approx(
        100.0 * fire.damage_mult
    )
    assert rules.apply_event_damage(100.0, fire, tief) == pytest.approx(
        100.0 * fire.damage_mult * (1.0 + tief.event_damage_bonus)
    )
    curse = CFG.events["curse"]
    assert rules.apply_event_damage(
        100.0, curse, CFG.race_passives("dwarf")
    ) == pytest.approx(100.0)
    assert rules.apply_event_damage(100.0, None, NEUTRAL_RACE) == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# Arena integration: a forced event is announced, persisted, and pays its XP
# ---------------------------------------------------------------------------
async def _nosleep(_seconds: float) -> None:
    return None


def _fixed_now() -> datetime:
    return datetime(2026, 7, 1, 12, 0, 0, tzinfo=UTC)


def test_round_with_forced_event_announces_and_persists():
    cfg = Config.load(GAME_CONFIG)
    cfg.events = {"crowd": cfg.events["crowd"]}  # force which event fires
    cfg.round = replace(cfg.round, event_chance=1.0)
    store = MemoryStore()
    sink = RecordingSink()
    arena = Arena(cfg, store, sink, rng=random.Random(3), sleep=_nosleep, now=_fixed_now)
    uid = store.add_user("brian")
    ch = store.create_character(
        user_id=uid, name="Thorak", class_name="barbarian", race="human",
        stats=dict(STATS), sprite_set="barb_01",
    )
    asyncio.run(arena.enqueue(ch.id, uid))
    outcome = asyncio.run(arena.run_once())

    start = sink.of_type("round_start")[0]
    assert start["event"] == {"name": "crowd", "label": cfg.events["crowd"].label}
    banner = sink.of_type("event")
    assert len(banner) == 1 and banner[0]["name"] == "crowd"
    assert any(t["kind"] == "event" for t in sink.of_type("ticker"))
    assert store.rounds[outcome.round_id]["event"] == "crowd"

    mine = next(e for e in outcome.entries if e.character_id == ch.id)
    expected_xp = round(
        rules.xp_for_placement(mine.placement, cfg.xp) * cfg.events["crowd"].xp_mult
    )
    assert store.characters[ch.id].xp == expected_xp == mine.xp_awarded


def test_no_event_round_start_carries_null_event():
    cfg = Config.load(GAME_CONFIG)
    cfg.round = replace(cfg.round, event_chance=0.0)
    store = MemoryStore()
    sink = RecordingSink()
    arena = Arena(cfg, store, sink, rng=random.Random(1), sleep=_nosleep, now=_fixed_now)
    outcome = asyncio.run(arena.run_once())
    assert sink.of_type("round_start")[0]["event"] is None
    assert not sink.of_type("event")
    assert store.rounds[outcome.round_id]["event"] is None


def test_events_can_be_defined_inline():
    # ArenaEvent knobs all default to no-ops so partial tables are valid.
    ev = ArenaEvent(name="x", label="X")
    assert ev.damage_mult == 1.0 and not ev.no_miss and ev.xp_mult == 1.0
