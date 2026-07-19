"""Race passive tests (PLAN.md §4.3). Pure rules, deterministic RNG.

Each passive is exercised in isolation with a scripted RNG so the mechanic — not
the balance — is verified. Balance (<= ~5% DPS impact) is the simulator's job
(``python -m server.sim --races``)."""

from __future__ import annotations

import random
from pathlib import Path

import pytest

from server import rules
from server.config import NEUTRAL_RACE, Config

GAME_CONFIG = Path(__file__).resolve().parents[1] / "config" / "game.toml"
CFG = Config.load(GAME_CONFIG)
DMG = CFG.damage
BARB = CFG.classes["barbarian"]
FLAT = {"STR": 10, "DEX": 10, "CON": 10, "INT": 10, "WIS": 10, "CHA": 10}


class ScriptRandom:
    """RNG that returns scripted values so a single swing is fully determined."""

    def __init__(self, randints: list[int] | None = None, randoms: list[float] | None = None):
        self._randints = list(randints or [])
        self._randoms = list(randoms or [])

    def randint(self, a: int, b: int) -> int:
        return self._randints.pop(0)

    def random(self) -> float:
        return self._randoms.pop(0)


def _state(passives) -> rules.CombatState:
    return rules.CombatState(lucky_left=passives.lucky_reroll_ones)


# ---------------------------------------------------------------------------
# Creation-time stat bonuses
# ---------------------------------------------------------------------------
def test_human_plus_one_all_stats():
    out = rules.apply_creation_bonus(FLAT, CFG.race_passives("human"))
    assert all(out[s] == 11 for s in out)
    assert FLAT["STR"] == 10  # input not mutated


def test_dwarf_plus_two_con_only():
    out = rules.apply_creation_bonus(FLAT, CFG.race_passives("dwarf"))
    assert out["CON"] == 12
    assert out["STR"] == 10 and out["DEX"] == 10


def test_neutral_creation_bonus_is_copy():
    out = rules.apply_creation_bonus(FLAT, NEUTRAL_RACE)
    assert out == FLAT and out is not FLAT


# ---------------------------------------------------------------------------
# Attack speed (Goblin) and the neutral-equivalence invariant
# ---------------------------------------------------------------------------
def test_goblin_attack_speed_shortens_interval():
    gob = CFG.race_passives("goblin")
    assert rules.effective_interval(2.0, gob) == pytest.approx(2.0 / 1.10)
    assert rules.effective_interval(2.0, NEUTRAL_RACE) == 2.0


def test_neutral_race_matches_resolve_attack_for_every_roll():
    # The neutral path must be numerically identical to the pre-race formula, so
    # the tuned coefficients still hold.
    for roll in range(1, 21):
        st = rules.CombatState()
        got = rules.resolve_race_attack(
            ScriptRandom([roll]), 15, 12, BARB, DMG, NEUTRAL_RACE, st
        )
        exp = rules.resolve_attack(roll, 15, 12, BARB, DMG)
        assert got.damage == pytest.approx(exp.damage)
        assert got.is_crit == exp.is_crit and got.is_miss == exp.is_miss


def test_neutral_whole_round_matches_simulate_fighter():
    a = rules.simulate_fighter_with_race(random.Random(42), 15, 12, BARB, DMG, NEUTRAL_RACE, 30)
    b = rules.simulate_fighter(random.Random(42), 15, 12, BARB, DMG, 30)
    assert a.total_damage == pytest.approx(b.total_damage)
    assert (a.hits, a.crits, a.misses) == (b.hits, b.crits, b.misses)


# ---------------------------------------------------------------------------
# Per-hit combat passives
# ---------------------------------------------------------------------------
def test_orc_first_swing_is_multiplied():
    orc = CFG.race_passives("orc")
    assert orc.first_hit_mult > 1.0
    st = _state(orc)
    rng = ScriptRandom([10, 10])
    first = rules.resolve_race_attack(rng, 15, 12, BARB, DMG, orc, st)
    second = rules.resolve_race_attack(rng, 15, 12, BARB, DMG, orc, st)
    assert first.damage == pytest.approx(second.damage * orc.first_hit_mult)


def test_goblin_reduces_per_hit_damage():
    gob = CFG.race_passives("goblin")
    g = rules.resolve_race_attack(ScriptRandom([10]), 15, 12, BARB, DMG, gob, _state(gob))
    n = rules.resolve_race_attack(ScriptRandom([10]), 15, 12, BARB, DMG, NEUTRAL_RACE,
                                  rules.CombatState())
    assert g.damage == pytest.approx(n.damage * 0.95)


def test_halfling_rerolls_only_the_first_natural_one():
    hal = CFG.race_passives("halfling")
    st = _state(hal)
    rng = ScriptRandom([1, 15, 1])  # 1->reroll to 15 (hit); next 1 stays a miss
    r1 = rules.resolve_race_attack(rng, 15, 12, BARB, DMG, hal, st)
    assert not r1.is_miss and r1.roll == 15
    r2 = rules.resolve_race_attack(rng, 15, 12, BARB, DMG, hal, st)
    assert r2.is_miss and r2.roll == 1


def test_elf_can_upgrade_a_hit_to_a_crit():
    elf = CFG.race_passives("elf")
    up = rules.resolve_race_attack(ScriptRandom([10], [0.01]), 15, 12, BARB, DMG, elf, _state(elf))
    crit_raw = (15 * DMG.crit_primary_mult + 12) * DMG.crit_final_mult
    assert up.is_crit and up.damage == pytest.approx(BARB.coeff * crit_raw)
    # No upgrade when the roll lands above the crit-chance bonus.
    keep = rules.resolve_race_attack(ScriptRandom([10], [0.5]), 15, 12, BARB, DMG, elf, _state(elf))
    assert not keep.is_crit


def test_dragonborn_adds_breath_bonus_on_every_tenth_swing():
    drag = CFG.race_passives("dragonborn")
    st = _state(drag)
    rng = ScriptRandom([10] * 10)
    results = [rules.resolve_race_attack(rng, 15, 12, BARB, DMG, drag, st) for _ in range(10)]
    base = results[0].damage
    bonus = BARB.coeff * (15 * DMG.mean_multiplier + 12) * drag.breath_bonus_mult
    assert results[8].damage == pytest.approx(base)          # 9th: no bonus
    assert results[9].damage == pytest.approx(base + bonus)  # 10th: breath bonus


# ---------------------------------------------------------------------------
# Config wiring
# ---------------------------------------------------------------------------
def test_all_ten_races_parsed_and_npc_is_neutral():
    from server import content

    assert set(CFG.races) == set(content.VALID_RACES)
    assert CFG.race_passives("npc") is NEUTRAL_RACE
    assert CFG.race_passives(None) is NEUTRAL_RACE
