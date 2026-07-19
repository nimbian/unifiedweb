"""Unit tests for the pure game-rules module (PLAN.md §4).

These must pass before the rules feed into the simulator or the round loop.
"""

from __future__ import annotations

import random

import pytest

from server import rules
from server.config import (
    ROLL_TABLE_LEN,
    ClassDef,
    DamageConfig,
    StatConfig,
    XpConfig,
)

# --- Canonical fixtures independent of the tuned coefficients on disk --------

STAT_CFG = StatConfig(dice=4, sides=6, keep=3, reroll_below=2)

CANON_TABLE = (
    0.5, 0.7, 0.7, 0.8, 0.8, 0.9, 0.9, 1.0, 1.0, 1.0,
    1.1, 1.1, 1.3, 1.3, 1.6, 1.6, 1.8, 1.8,
)
DMG_CFG = DamageConfig(
    roll_multipliers=CANON_TABLE, crit_primary_mult=2.0, crit_final_mult=2.0, display_scale=10.0
)

# coeff=1.0 makes the arithmetic in the damage tests transparent.
UNIT_CLASS = ClassDef(name="test", primary="STR", secondary="CON", attack_interval=3.0, coeff=1.0)

XP_CFG = XpConfig(
    levels_max=10,
    base_per_round=100,
    placement_bonus=(150, 100, 60, 30, 30),
    curve_coeff=100,
    per_level_primary_bonus=1,
)


# ---------------------------------------------------------------------------
# 4.1 Stat generation
# ---------------------------------------------------------------------------
def test_roll_die_never_below_reroll_threshold():
    rng = random.Random(1)
    seen = {rules.roll_die(rng, STAT_CFG) for _ in range(5000)}
    assert seen == {2, 3, 4, 5, 6}  # 1s always rerolled; full 2..6 range appears


def test_roll_stat_range_is_6_to_18():
    rng = random.Random(2)
    lo, hi = 99, 0
    for _ in range(20000):
        v = rules.roll_stat(rng, STAT_CFG)
        lo, hi = min(lo, v), max(hi, v)
        assert 6 <= v <= 18
    assert lo == 6 and hi == 18  # both extremes are reachable


def test_roll_stat_drops_lowest_die():
    # Feed dice directly: 4 dice [2,6,5,4] -> drop the 2, keep 6+5+4 = 15.
    class FakeRandom:
        def __init__(self, values):
            self._values = list(values)

        def randint(self, a, b):
            return self._values.pop(0)

    fake = FakeRandom([2, 6, 5, 4])
    assert rules.roll_stat(fake, STAT_CFG) == 15


def test_roll_stat_block_has_all_six_stats():
    rng = random.Random(3)
    block = rules.roll_stat_block(rng, STAT_CFG)
    assert set(block) == {"STR", "DEX", "CON", "INT", "WIS", "CHA"}
    assert all(6 <= v <= 18 for v in block.values())


def test_stat_generation_is_deterministic_per_seed():
    assert rules.roll_stat_block(random.Random(42), STAT_CFG) == rules.roll_stat_block(
        random.Random(42), STAT_CFG
    )


# ---------------------------------------------------------------------------
# 4.4 Attack roll / damage formula
# ---------------------------------------------------------------------------
def test_natural_one_is_a_miss():
    res = rules.resolve_attack(1, 16, 10, UNIT_CLASS, DMG_CFG)
    assert res.is_miss and not res.is_crit
    assert res.damage == 0


def test_natural_twenty_is_a_crit():
    # raw = coeff * ((PS*2.0 + SS) * 2.0) = 1.0 * ((16*2 + 10) * 2) = 84.0; x10 display = 840
    res = rules.resolve_attack(20, 16, 10, UNIT_CLASS, DMG_CFG)
    assert res.is_crit and not res.is_miss
    assert res.damage == pytest.approx(84.0)
    assert rules.display_damage(res.damage, DMG_CFG) == 840


@pytest.mark.parametrize(
    "roll,raw,display",
    [
        (2, 18.0, 180),   # 16*0.5 + 10
        (10, 26.0, 260),  # 16*1.0 + 10
        (11, 26.0, 260),  # mult 1.0 as well
        (19, 38.8, 388),  # 16*1.8 + 10 = 38.8 (no per-hit rounding bias)
    ],
)
def test_normal_roll_damage(roll, raw, display):
    res = rules.resolve_attack(roll, 16, 10, UNIT_CLASS, DMG_CFG)
    assert not res.is_crit and not res.is_miss
    assert res.damage == pytest.approx(raw)  # RAW float, not rounded
    assert rules.display_damage(res.damage, DMG_CFG) == display


def test_display_damage_scales_and_rounds():
    assert rules.display_damage(0.0, DMG_CFG) == 0
    assert rules.display_damage(26.0, DMG_CFG) == 260
    assert rules.display_damage(38.8, DMG_CFG) == 388


def test_secondary_stat_is_flat_not_multiplied_by_roll():
    # Same primary/roll, secondary differs by 3 -> damage differs by exactly 3,
    # at both a low and a high multiplier (SS is never scaled by the roll).
    for roll in (2, 10, 19):
        low = rules.resolve_attack(roll, 10, 5, UNIT_CLASS, DMG_CFG).damage
        high = rules.resolve_attack(roll, 10, 8, UNIT_CLASS, DMG_CFG).damage
        assert high - low == 3


def test_coefficient_scales_damage():
    heavy = ClassDef(name="h", primary="STR", secondary="CON", attack_interval=4.0, coeff=2.0)
    base = rules.resolve_attack(10, 16, 10, UNIT_CLASS, DMG_CFG).damage
    scaled = rules.resolve_attack(10, 16, 10, heavy, DMG_CFG).damage
    assert scaled == 2 * base


def test_attack_multiplier_table_boundaries():
    assert rules.attack_multiplier(2, DMG_CFG) == 0.5
    assert rules.attack_multiplier(19, DMG_CFG) == 1.8
    assert rules.attack_multiplier(10, DMG_CFG) == 1.0
    assert len(DMG_CFG.roll_multipliers) == ROLL_TABLE_LEN


@pytest.mark.parametrize("bad_roll", [1, 20, 0, 21])
def test_attack_multiplier_rejects_special_and_out_of_range(bad_roll):
    with pytest.raises(ValueError):
        rules.attack_multiplier(bad_roll, DMG_CFG)


@pytest.mark.parametrize("bad_roll", [0, 21, -1])
def test_resolve_attack_rejects_out_of_range_d20(bad_roll):
    with pytest.raises(ValueError):
        rules.resolve_attack(bad_roll, 10, 10, UNIT_CLASS, DMG_CFG)


def test_roll_attack_uses_injected_rng():
    # Force a nat 1 then a nat 20 via a stubbed rng.
    class StubRng:
        def __init__(self, seq):
            self._seq = list(seq)

        def randint(self, a, b):
            return self._seq.pop(0)

    stub = StubRng([1, 20])
    assert rules.roll_attack(stub, 16, 10, UNIT_CLASS, DMG_CFG).is_miss
    assert rules.roll_attack(stub, 16, 10, UNIT_CLASS, DMG_CFG).is_crit


@pytest.mark.parametrize(
    "interval,expected",
    [(4.0, 15), (3.0, 20), (2.0, 30), (1.5, 40), (3.5, 17), (2.5, 24), (5.0, 12)],
)
def test_attacks_in_window(interval, expected):
    assert rules.attacks_in_window(interval, 60) == expected


def test_simulate_fighter_matches_resolve_attack():
    """The fast aggregate must equal summing the canonical resolve_attack over
    the identical roll sequence — otherwise the sim would balance a different
    game than the one that ships."""

    class ReplayRng:
        def __init__(self, seq):
            self._seq = list(seq)
            self._i = 0

        def randint(self, a, b):
            v = self._seq[self._i]
            self._i += 1
            return v

    # A sequence hitting every d20 face, including 1 (miss) and 20 (crit).
    seq = [((i * 7) % 20) + 1 for i in range(200)]
    ps, ss = 17, 11

    exp_total = exp_hits = exp_crits = exp_misses = exp_high = 0
    for roll in seq:
        r = rules.resolve_attack(roll, ps, ss, UNIT_CLASS, DMG_CFG)
        if r.is_miss:
            exp_misses += 1
            continue
        exp_hits += 1
        exp_crits += int(r.is_crit)
        exp_total += r.damage
        exp_high = max(exp_high, r.damage)

    got = rules.simulate_fighter(ReplayRng(seq), ps, ss, UNIT_CLASS, DMG_CFG, len(seq))
    assert got.total_damage == pytest.approx(exp_total)
    assert got.hits == exp_hits
    assert got.crits == exp_crits
    assert got.misses == exp_misses
    assert got.highest_hit == pytest.approx(exp_high)


# ---------------------------------------------------------------------------
# 4.5 XP / leveling / placement / retirement
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "level,cumulative",
    [(1, 0), (2, 100), (3, 300), (4, 600), (5, 1000), (10, 4500)],
)
def test_cumulative_xp_curve(level, cumulative):
    assert rules.cumulative_xp_for_level(level, XP_CFG) == cumulative


@pytest.mark.parametrize(
    "xp,level",
    [(0, 1), (99, 1), (100, 2), (299, 2), (300, 3), (4499, 9), (4500, 10), (10_000_000, 10)],
)
def test_level_for_xp(xp, level):
    assert rules.level_for_xp(xp, XP_CFG) == level


def test_level_is_capped_at_max():
    assert rules.level_for_xp(999_999_999, XP_CFG) == XP_CFG.levels_max


def test_primary_grows_one_per_level():
    assert rules.primary_at_level(15, 1, XP_CFG) == 15
    assert rules.primary_at_level(15, 5, XP_CFG) == 19
    assert rules.primary_at_level(15, 10, XP_CFG) == 24


@pytest.mark.parametrize(
    "placement,xp",
    [(1, 250), (2, 200), (3, 160), (4, 130), (5, 130), (6, 100), (10, 100)],
)
def test_xp_for_placement(placement, xp):
    assert rules.xp_for_placement(placement, XP_CFG) == xp


def test_win_is_first_place_only():
    assert rules.is_win(1)
    assert not rules.is_win(2)
    assert not rules.is_win(10)


def test_level_after_battle_grants_one_level_capped():
    # R3: +1 level per completed battle, regardless of placement, capped at max.
    assert rules.level_after_battle(1, XP_CFG) == 2
    assert rules.level_after_battle(9, XP_CFG) == 10
    assert rules.level_after_battle(10, XP_CFG) == 10  # capped at levels_max
    to20 = XpConfig(levels_max=20, base_per_round=0, placement_bonus=(),
                    curve_coeff=100, per_level_primary_bonus=1, mode="per_battle")
    assert rules.level_after_battle(19, to20) == 20
    assert rules.level_after_battle(20, to20) == 20


def test_retirement_at_lifespan():
    assert not rules.should_retire(19, 20)
    assert rules.should_retire(20, 20)
    assert rules.should_retire(21, 20)


def test_invalid_placement_and_level_raise():
    with pytest.raises(ValueError):
        rules.xp_for_placement(0, XP_CFG)
    with pytest.raises(ValueError):
        rules.cumulative_xp_for_level(0, XP_CFG)
