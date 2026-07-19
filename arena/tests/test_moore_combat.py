"""MooreDnD combat-model tests (R1, docs/R1_combat_math.md).

Pure primitives only — ability→core-stat derivation, sorted-4d6 assignment, and
the per-swing to-hit-vs-AC resolution. The engine flag stays "classic" in the
shipped config, so these exercise the additive `moore` code directly. Round/sim/
arena wiring and the moore tuner are later increments."""

from __future__ import annotations

import random
from pathlib import Path

import pytest

from server import rules
from server.config import NEUTRAL_RACE, STAT_NAMES, AbilityDef, Config

GAME_CONFIG = Path(__file__).resolve().parents[1] / "config" / "game.toml"
CFG = Config.load(GAME_CONFIG)
COMBAT = CFG.combat
BARB = CFG.classes["barbarian"]
WIZ = CFG.classes["wizard"]


class ScriptRandom:
    """RNG returning scripted values so a swing is fully determined."""

    def __init__(self, randints=None, uniforms=None, randoms=None):
        self._randints = list(randints or [])
        self._uniforms = list(uniforms or [])
        self._randoms = list(randoms or [])

    def randint(self, a: int, b: int) -> int:
        return self._randints.pop(0)

    def uniform(self, a: float, b: float) -> float:
        return self._uniforms.pop(0) if self._uniforms else 0.0

    def random(self) -> float:
        return self._randoms.pop(0) if self._randoms else 1.0


# ---------------------------------------------------------------------------
# D&D modifier
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "score,mod",
    [(7, -2), (8, -1), (9, -1), (10, 0), (11, 0), (12, 1), (14, 2), (16, 3), (18, 4), (20, 5)],
)
def test_dnd_modifier_matches_the_canonical_table(score, mod):
    assert rules.dnd_modifier(score) == mod


# ---------------------------------------------------------------------------
# Core-stat derivation
# ---------------------------------------------------------------------------
def test_attack_power_scales_by_ability_and_class_coeff():
    abilities = {s: 10 for s in STAT_NAMES}
    abilities["STR"] = 16  # barbarian primary
    core = rules.derive_core_stats(abilities, BARB, COMBAT)
    assert core.attack_power == pytest.approx(16 * COMBAT.ap_per_point * BARB.ap_coeff())
    assert core.attack_modifier == 3  # mod(16)
    assert core.attack_speed == round(1000 / BARB.attack_interval)


def test_attack_power_respects_the_cap():
    abilities = {s: 10 for s in STAT_NAMES}
    abilities["WIS"] = 400  # absurd primary -> would exceed the cap
    core = rules.derive_core_stats(abilities, WIZ, COMBAT)
    assert core.attack_power == COMBAT.ap_cap


def test_crit_damage_uses_the_class_crit_ability():
    # Barbarian crit ability defaults to its secondary, CON.
    assert BARB.crit_ability == "CON"
    abilities = {s: 10 for s in STAT_NAMES}
    abilities["CON"] = 12
    core = rules.derive_core_stats(abilities, BARB, COMBAT)
    # 100% + 5pp * 12 = 160% -> x1.6
    assert core.crit_damage_mult == pytest.approx(1.0 + COMBAT.crit_pp_per_point * 12 / 100)


def test_wizard_primary_stays_wis_in_derivation():
    abilities = {s: 8 for s in STAT_NAMES}
    abilities["WIS"] = 18
    abilities["INT"] = 8
    core = rules.derive_core_stats(abilities, WIZ, COMBAT)
    # AP must come from WIS (18), not INT (8) — hard rule #6.
    assert core.attack_power == pytest.approx(18 * COMBAT.ap_per_point * WIZ.ap_coeff())
    assert core.attack_modifier == rules.dnd_modifier(18)


def test_health_ac_loot_use_con_dex_cha():
    abilities = {s: 10 for s in STAT_NAMES}
    abilities["CON"], abilities["DEX"], abilities["CHA"] = 14, 16, 12
    core = rules.derive_core_stats(abilities, BARB, COMBAT)
    assert core.health == pytest.approx(COMBAT.health_base + 14 * COMBAT.health_per_con)
    assert core.armor_class == BARB.base_ac + rules.dnd_modifier(16)
    assert core.loot_bonus == pytest.approx(COMBAT.loot_base + 12 * COMBAT.loot_per_cha)


# ---------------------------------------------------------------------------
# Sorted-4d6 assignment
# ---------------------------------------------------------------------------
def test_priority_puts_primary_and_secondary_first():
    order = rules.stat_priority(BARB)
    assert order[:2] == ["STR", "CON"]  # barbarian primary, secondary
    assert sorted(order) == sorted(STAT_NAMES)  # a permutation of all six


def test_sorted_assignment_gives_highest_roll_to_primary():
    rolls = [8, 18, 12, 15, 10, 6]
    block = rules.assign_sorted_stats(rolls, BARB)
    assert block["STR"] == 18  # highest -> primary
    assert block["CON"] == 15  # next -> secondary
    assert sorted(block.values()) == sorted(rolls)
    assert set(block) == set(STAT_NAMES)


def test_sorted_assignment_rejects_wrong_length():
    with pytest.raises(ValueError):
        rules.assign_sorted_stats([1, 2, 3], BARB)


def test_roll_sorted_stat_block_is_ordered_and_server_side():
    rng = random.Random(4)
    block = rules.roll_sorted_stat_block(rng, CFG.stats, WIZ)
    order = rules.stat_priority(WIZ)
    vals = [block[s] for s in order]
    assert vals == sorted(vals, reverse=True)  # priority order is non-increasing
    assert all(6 <= v <= 18 for v in block.values())  # 4d6-drop-lowest range


# ---------------------------------------------------------------------------
# Per-swing resolution
# ---------------------------------------------------------------------------
def _core(ap=300.0, mod=2, crit_mult=1.6):
    return rules.CoreStats(
        attack_power=ap, attack_modifier=mod, attack_speed=250,
        health=400, armor_class=14, crit_damage_mult=crit_mult, loot_bonus=20,
    )


def test_natural_one_always_misses():
    res = rules.resolve_moore_attack(ScriptRandom([1]), _core(), 5, COMBAT)
    assert res.is_miss and res.damage == 0.0 and res.roll == 1


def test_natural_twenty_always_hits_and_crits():
    core = _core(ap=300.0, crit_mult=1.6)
    res = rules.resolve_moore_attack(ScriptRandom([20], [0.0]), core, 99, COMBAT)
    assert res.is_crit and not res.is_miss
    assert res.damage == pytest.approx(300.0 * 1.6)


def test_hit_requires_roll_plus_mod_to_meet_ac():
    core = _core(mod=2)
    # roll 7 + mod 2 = 9 < AC 12 -> miss
    assert rules.resolve_moore_attack(ScriptRandom([7]), core, 12, COMBAT).is_miss
    # roll 10 + mod 2 = 12 >= AC 12 -> hit
    hit = rules.resolve_moore_attack(ScriptRandom([10], [0.0]), core, 12, COMBAT)
    assert not hit.is_miss and hit.damage == pytest.approx(core.attack_power)


def test_variance_is_applied_and_floored():
    core = _core(ap=300.0)
    hi = rules.resolve_moore_attack(ScriptRandom([15], [75.0]), core, 5, COMBAT)
    lo = rules.resolve_moore_attack(ScriptRandom([15], [-75.0]), core, 5, COMBAT)
    assert hi.damage == pytest.approx(375.0)
    assert lo.damage == pytest.approx(225.0)
    # a big negative variance can't push a hit below min_hit
    tiny = _core(ap=10.0)
    floored = rules.resolve_moore_attack(ScriptRandom([15], [-1000.0]), tiny, 5, COMBAT)
    assert floored.damage == COMBAT.min_hit and not floored.is_miss


def test_force_hit_lands_even_on_a_natural_one():
    # Second Wind analog: force_hit overrides both the nat-1 auto-miss and AC.
    res = rules.resolve_moore_attack(
        ScriptRandom([1], [0.0]), _core(), 99, COMBAT, force_hit=True
    )
    assert not res.is_miss and res.damage == pytest.approx(_core().attack_power)


def test_crit_expanded_upgrades_a_landed_hit():
    core = _core(ap=200.0, crit_mult=2.0)
    res = rules.resolve_moore_attack(
        ScriptRandom([12], [0.0]), core, 5, COMBAT, crit_expanded=True
    )
    assert res.is_crit and res.damage == pytest.approx(400.0)


def test_low_dummy_ac_makes_hits_near_automatic():
    # With the shipped dummy_ac and a modest +2 mod, only very low rolls miss.
    core = _core(mod=2)
    rng = random.Random(1)
    misses = sum(
        rules.resolve_moore_attack(rng, core, COMBAT.dummy_ac, COMBAT).is_miss
        for _ in range(2000)
    )
    assert misses / 2000 < 0.12  # near-auto (R1 §3: to-hit matters vs monsters, not dummies)


# ---------------------------------------------------------------------------
# Race passives + signature abilities layered onto the moore hit (R1 §4-5)
# ---------------------------------------------------------------------------
def _st(passives=NEUTRAL_RACE):
    return rules.CombatState(lucky_left=passives.lucky_reroll_ones)


def test_moore_race_attack_neutral_is_rng_identical_to_base():
    # Neutral passives + no ability + no event must reduce to resolve_moore_attack
    # (same draws, same damage) so the tuned base loop is preserved.
    for roll in range(1, 21):
        a = rules.resolve_moore_race_attack(
            ScriptRandom([roll], [12.0]), _core(), 5, COMBAT, NEUTRAL_RACE, _st()
        )
        b = rules.resolve_moore_attack(ScriptRandom([roll], [12.0]), _core(), 5, COMBAT)
        assert a.damage == pytest.approx(b.damage)
        assert (a.is_crit, a.is_miss) == (b.is_crit, b.is_miss)


def test_moore_orc_first_swing_is_multiplied():
    orc = CFG.race_passives("orc")
    core, st, rng = _core(), _st(), ScriptRandom([10, 10], [0.0, 0.0])
    first = rules.resolve_moore_race_attack(rng, core, 5, COMBAT, orc, st)
    second = rules.resolve_moore_race_attack(rng, core, 5, COMBAT, orc, st)
    assert first.damage == pytest.approx(second.damage * orc.first_hit_mult)


def test_moore_human_damage_mult_applies_per_hit():
    human = CFG.race_passives("human")
    got = rules.resolve_moore_race_attack(
        ScriptRandom([10], [0.0]), _core(), 5, COMBAT, human, _st(human)
    )
    base = rules.resolve_moore_race_attack(
        ScriptRandom([10], [0.0]), _core(), 5, COMBAT, NEUTRAL_RACE, _st()
    )
    assert got.damage == pytest.approx(base.damage * human.damage_mult)


def test_moore_elf_crit_chance_upgrades_a_hit():
    elf = CFG.race_passives("elf")  # +3% crit-upgrade chance
    core = _core(crit_mult=2.0)
    # random() below 0.03 -> the landed hit is upgraded to a crit.
    res = rules.resolve_moore_race_attack(
        ScriptRandom([10], [0.0], randoms=[0.01]), core, 5, COMBAT, elf, _st(elf)
    )
    assert res.is_crit and res.damage == pytest.approx(core.attack_power * 2.0)


def test_moore_second_wind_forces_a_nat_one_to_land():
    res = rules.resolve_moore_race_attack(
        ScriptRandom([1], [0.0]), _core(), 99, COMBAT,
        NEUTRAL_RACE, rules.CombatState(no_miss_left=1),
    )
    assert not res.is_miss and res.damage > 0.0


def test_moore_rage_buff_window_multiplies_damage():
    core = _core()
    st = rules.CombatState(buff_mult=1.4, buff_start=0.0, buff_until=10.0)
    inside = rules.resolve_moore_race_attack(
        ScriptRandom([10], [0.0]), core, 5, COMBAT, NEUTRAL_RACE, st, swing_time=5.0
    )
    plain = rules.resolve_moore_race_attack(
        ScriptRandom([10], [0.0]), core, 5, COMBAT, NEUTRAL_RACE, _st(), swing_time=5.0
    )
    assert inside.damage == pytest.approx(plain.damage * 1.4)


def test_moore_burst_ability_is_attack_power_times_hit_mult():
    core = _core(ap=300.0)
    fireball = AbilityDef(name="Fireball", kind="burst", hits=1, hit_mult=2.5)
    total, per_hit = rules.cast_moore_ability(rules.CombatState(), fireball, 30.0, core)
    assert per_hit == pytest.approx(750.0) and total == pytest.approx(750.0)


def test_moore_arena_event_applies_in_the_race_attack():
    fire = CFG.events["fire"]
    got = rules.resolve_moore_race_attack(
        ScriptRandom([10], [0.0]), _core(), 5, COMBAT, NEUTRAL_RACE, _st(), event=fire
    )
    base = rules.resolve_moore_race_attack(
        ScriptRandom([10], [0.0]), _core(), 5, COMBAT, NEUTRAL_RACE, _st()
    )
    assert got.damage == pytest.approx(base.damage * fire.damage_mult)
