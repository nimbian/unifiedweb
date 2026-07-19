"""Signature-ability tests (PLAN.md §4.2). Pure rules, deterministic RNG.

Each of the four ability kinds is exercised in isolation. Balance (classes stay
in 9.5-10.5% with abilities on) is the simulator's job (``python -m server.sim``)."""

from __future__ import annotations

import random
from pathlib import Path

import pytest

from server import rules
from server.config import NEUTRAL_RACE, Config

GAME_CONFIG = Path(__file__).resolve().parents[1] / "config" / "game.toml"
CFG = Config.load(GAME_CONFIG)
DMG = CFG.damage


def C(name: str):
    return CFG.classes[name]


class ScriptRandom:
    def __init__(self, randints=None, randoms=None, uniforms=None):
        self._randints = list(randints or [])
        self._randoms = list(randoms or [])
        self._uniforms = list(uniforms or [])

    def randint(self, a, b):
        return self._randints.pop(0)

    def random(self):
        return self._randoms.pop(0)

    def uniform(self, a, b):
        return self._uniforms.pop(0)


# ---------------------------------------------------------------------------
# damage_buff (Barbarian Rage, Warlock Curse)
# ---------------------------------------------------------------------------
def test_damage_buff_multiplies_swings_inside_the_window():
    barb = C("barbarian")
    rage = barb.ability
    st = rules.CombatState()
    burst, _ = rules.cast_ability(st, rage, 5.0, 15, 12, barb, DMG)
    assert burst == 0.0
    assert st.buff_mult == pytest.approx(1.40)
    assert (st.buff_start, st.buff_until) == (5.0, 15.0)

    base = rules.resolve_attack(10, 15, 12, barb, DMG).damage
    inside = rules.resolve_race_attack(
        ScriptRandom([10]), 15, 12, barb, DMG, NEUTRAL_RACE, st, swing_time=8.0
    )
    assert inside.damage == pytest.approx(base * 1.40)

    st2 = rules.CombatState(buff_mult=1.40, buff_start=5.0, buff_until=15.0)
    outside = rules.resolve_race_attack(
        ScriptRandom([10]), 15, 12, barb, DMG, NEUTRAL_RACE, st2, swing_time=99.0
    )
    assert outside.damage == pytest.approx(base)


# ---------------------------------------------------------------------------
# no_miss (Fighter Second Wind)
# ---------------------------------------------------------------------------
def test_no_miss_lands_the_next_n_swings_then_expires():
    fighter = C("fighter")
    st = rules.CombatState()
    rules.cast_ability(st, fighter.ability, 5.0, 15, 12, fighter, DMG)
    assert st.no_miss_left == 3

    for _ in range(3):  # three natural 1s all land as the minimum hit
        r = rules.resolve_race_attack(ScriptRandom([1]), 15, 12, fighter, DMG, NEUTRAL_RACE, st)
        assert not r.is_miss and r.roll == 2
    fourth = rules.resolve_race_attack(ScriptRandom([1]), 15, 12, fighter, DMG, NEUTRAL_RACE, st)
    assert fourth.is_miss  # counter spent


# ---------------------------------------------------------------------------
# crit_buff (Rogue Backstab)
# ---------------------------------------------------------------------------
def test_crit_buff_applies_to_next_landed_hit_only():
    rogue = C("rogue")
    st = rules.CombatState()
    rules.cast_ability(st, rogue.ability, 5.0, 15, 12, rogue, DMG)
    assert st.crit_buff_left == 1 and st.crit_buff_mag == pytest.approx(0.50)

    # A natural 1 misses (rogue has no no-miss) and must NOT spend the charge.
    miss = rules.resolve_race_attack(ScriptRandom([1]), 15, 12, rogue, DMG, NEUTRAL_RACE, st)
    assert miss.is_miss and st.crit_buff_left == 1

    up = rules.resolve_race_attack(ScriptRandom([10], [0.4]), 15, 12, rogue, DMG, NEUTRAL_RACE, st)
    assert up.is_crit and st.crit_buff_left == 0  # 0.4 < 0.50 -> crit, charge spent
    later = rules.resolve_race_attack(
        ScriptRandom([10], [0.4]), 15, 12, rogue, DMG, NEUTRAL_RACE, st
    )
    assert not later.is_crit  # buff gone


# ---------------------------------------------------------------------------
# burst (Monk Flurry, Ranger Volley, Paladin Smite, Wizard Fireball)
# ---------------------------------------------------------------------------
def test_burst_returns_total_and_per_hit_without_touching_state():
    wiz = C("wizard")
    st = rules.CombatState()
    burst, per_hit = rules.cast_ability(st, wiz.ability, 5.0, 16, 10, wiz, DMG)  # 1 x 2.5
    avg = 16 * DMG.mean_multiplier + 10
    assert per_hit == pytest.approx(wiz.coeff * avg * 2.5)
    assert burst == pytest.approx(per_hit)  # hits == 1
    assert st.buff_until == -1.0 and st.no_miss_left == 0  # no lingering state

    monk = C("monk")
    b, ph = rules.cast_ability(rules.CombatState(), monk.ability, 5.0, 15, 12, monk, DMG)  # 5 x 0.4
    avg_m = 15 * DMG.mean_multiplier + 12
    assert ph == pytest.approx(monk.coeff * avg_m * 0.40)
    assert b == pytest.approx(ph * 5)


# ---------------------------------------------------------------------------
# Scheduling + whole-round integration
# ---------------------------------------------------------------------------
def test_schedule_cast_is_mid_round_or_none():
    assert rules.schedule_cast(random.Random(0), None, 60.0) is None
    for seed in range(20):
        t = rules.schedule_cast(random.Random(seed), C("monk").ability, 60.0)
        assert 12.0 <= t <= 48.0  # [0.2, 0.8] x 60s


def test_fireball_burst_adds_exactly_its_damage_over_no_ability():
    wiz = C("wizard")
    n = rules.attacks_in_window(wiz.attack_interval, 60)
    with_ab = rules.simulate_fighter_round(
        ScriptRandom([10] * n, uniforms=[0.5]), 16, 10, wiz, DMG,
        NEUTRAL_RACE, wiz.ability, n, wiz.attack_interval, 60,
    )
    no_ab = rules.simulate_fighter_round(
        ScriptRandom([10] * n), 16, 10, wiz, DMG, NEUTRAL_RACE, None, n, wiz.attack_interval, 60,
    )
    burst = wiz.coeff * (16 * DMG.mean_multiplier + 10) * 2.5
    assert with_ab.total_damage == pytest.approx(no_ab.total_damage + burst)
