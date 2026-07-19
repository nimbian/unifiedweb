"""R6 co-training blend rules (docs/R4_R6_plan.md): the stat blend regresses toward
the creation mean with a bounded edge and converges across generations (no
snowball). Cost + expectations too. Command flow lives in test_commands."""

from __future__ import annotations

import random
from pathlib import Path

from server import rules
from server.config import Config

GAME_CONFIG = Path(__file__).resolve().parents[1] / "config" / "game.toml"
CFG = Config.load(GAME_CONFIG)
BARB = CFG.classes["barbarian"]
EXP = rules.sorted_stat_expectations(CFG.stats, samples=20000)


def _maxed():
    return {s: 18 for s in ["STR", "DEX", "CON", "INT", "WIS", "CHA"]}


def _leveled_parent(rng, cls, level=20):
    block = rules.roll_sorted_stat_block(rng, CFG.stats, cls)
    block[cls.primary] = rules.primary_at_level(block[cls.primary], level, CFG.xp)
    return block


def test_expectations_are_descending_and_reasonable():
    assert sorted(EXP, reverse=True) == EXP
    assert 15 < EXP[0] < 18 and 8 < EXP[-1] < 12


def test_training_cost_rises_with_mentor_uses():
    assert rules.training_cost(500, 0) == 500
    assert rules.training_cost(500, 1) == 1000
    assert rules.training_cost(500, 3) == 2000


def test_blend_assigns_highest_to_primary():
    rng = random.Random(1)
    child = rules.blend_training_stats(_maxed(), _maxed(), BARB, EXP, CFG.training, rng)
    assert child[BARB.primary] == max(child.values())  # sorted into class priority


def test_blend_bounds_the_primary_edge():
    # Even with both parents maxed + leveled, the child's primary stays within the
    # per-rank cap of the sorted-4d6 rank mean -> a small, bounded DPS edge.
    rng = random.Random(2)
    ceiling = min(18, round(EXP[0]) + CFG.training.max_bonus_points)
    for _ in range(200):
        child = rules.blend_training_stats(_maxed(), _maxed(), BARB, EXP, CFG.training, rng)
        assert child[BARB.primary] <= ceiling


def test_blend_regresses_weak_parents_up_toward_the_mean():
    # Two below-average parents produce a child pulled back UP toward the mean
    # (regression cuts both ways, so lineages don't drift to extremes).
    rng = random.Random(3)
    weak = {s: 6 for s in ["STR", "DEX", "CON", "INT", "WIS", "CHA"]}
    prim = sum(
        rules.blend_training_stats(weak, weak, BARB, EXP, CFG.training, rng)[BARB.primary]
        for _ in range(300)
    ) / 300
    assert prim > 9  # well above the parents' 6, regressed toward the ~16 mean


def test_multi_generation_lineage_does_not_snowball():
    # Repeatedly training children from the previous generation's children (each
    # re-leveled to 20 so it can mentor) must converge, not compound.
    rng = random.Random(4)
    gen = [_leveled_parent(rng, BARB) for _ in range(150)]
    means = []
    for _ in range(6):
        children = []
        for _ in range(150):
            a, b = rng.choice(gen), rng.choice(gen)
            child = rules.blend_training_stats(a, b, BARB, EXP, CFG.training, rng)
            child[BARB.primary] = rules.primary_at_level(child[BARB.primary], 20, CFG.xp)
            children.append(child)
        means.append(sum(c[BARB.primary] for c in children) / len(children))
        gen = children
    # Later generations don't exceed the first by more than rounding noise.
    assert max(means) - means[0] <= 1.0
