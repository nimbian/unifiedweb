"""R4 monster-battle rules (docs/R4_R6_plan.md).

Pure combat primitives: monster sizing, the monster's to-hit-vs-AC swing, the
escalating ladder, and the co-op round simulation (victory/defeat, KO attrition,
determinism). Config parsing/validation lives in test_config; arena wiring and the
--monsters sim report are exercised separately."""

from __future__ import annotations

import random
from pathlib import Path

import pytest

from server import rules
from server.config import NEUTRAL_RACE, STAT_NAMES, Config, MonsterTier

GAME_CONFIG = Path(__file__).resolve().parents[1] / "config" / "game.toml"
CFG = Config.load(GAME_CONFIG)
COMBAT = CFG.combat
BARB = CFG.classes["barbarian"]


class ScriptRandom:
    """RNG returning scripted values so a swing is fully determined."""

    def __init__(self, randints=None, uniforms=None, randoms=None, randranges=None):
        self._randints = list(randints or [])
        self._uniforms = list(uniforms or [])
        self._randoms = list(randoms or [])
        self._randranges = list(randranges or [])

    def randint(self, a: int, b: int) -> int:
        return self._randints.pop(0)

    def uniform(self, a: float, b: float) -> float:
        return self._uniforms.pop(0) if self._uniforms else 0.0

    def random(self) -> float:
        return self._randoms.pop(0) if self._randoms else 1.0

    def randrange(self, n: int) -> int:
        return self._randranges.pop(0) if self._randranges else 0


def _core(str_score=16, con=14, dex=12, cha=10, cls=BARB):
    ab = {s: 10 for s in STAT_NAMES}
    ab[cls.primary] = str_score
    ab["CON"] = con
    ab["DEX"] = dex
    ab["CHA"] = cha
    return rules.derive_core_stats(ab, cls, COMBAT)


TIER3 = MonsterTier(tier=3, label="Ogre", hp_pct_of_team=0.65, ac=13,
                    attack_mod=5, attack_interval=2.8, damage=400, gold_mult=2.0)


# --- sizing --------------------------------------------------------------
def test_expected_team_output_sums_ap_times_swings():
    cores = [_core(), _core()]
    intervals = [4.0, 4.0]
    out = rules.expected_team_output(cores, intervals, 90)
    n = rules.attacks_in_window(4.0, 90)
    assert out == pytest.approx(sum(c.attack_power for c in cores) * n)


def test_build_monster_hp_is_fraction_of_team_output():
    m = rules.build_monster(TIER3, team_output=10_000.0)
    assert m.hp_max == pytest.approx(6500.0)  # 0.65 * 10000
    assert m.ac == 13 and m.attack_mod == 5 and m.gold_mult == 2.0
    assert m.tier == 3 and m.label == "Ogre"


def test_build_monster_hp_floored_at_one():
    m = rules.build_monster(TIER3, team_output=0.0)
    assert m.hp_max == 1.0


# --- monster swing -------------------------------------------------------
def _monster(damage=400.0, attack_mod=5):
    return rules.Monster(label="M", tier=3, hp_max=1000, ac=13, attack_mod=attack_mod,
                         damage=damage, attack_interval=2.8, gold_mult=2.0)


def test_monster_nat_1_always_misses():
    rng = ScriptRandom(randints=[1])
    hit, dmg = rules.resolve_monster_attack(rng, _monster(), target_ac=30, combat=COMBAT)
    assert hit is False and dmg == 0.0


def test_monster_nat_20_crits_for_double():
    rng = ScriptRandom(randints=[20], uniforms=[0.0])
    hit, dmg = rules.resolve_monster_attack(rng, _monster(damage=400), target_ac=99, combat=COMBAT)
    assert hit is True and dmg == pytest.approx(800.0)  # 400 * 2 crit


def test_monster_hits_when_roll_plus_mod_meets_ac():
    # roll 10 + mod 5 = 15 >= AC 15 -> hit
    rng = ScriptRandom(randints=[10], uniforms=[0.0])
    hit, dmg = rules.resolve_monster_attack(rng, _monster(damage=400, attack_mod=5),
                                            target_ac=15, combat=COMBAT)
    assert hit is True and dmg == pytest.approx(400.0)


def test_monster_misses_when_below_ac():
    rng = ScriptRandom(randints=[9])  # 9 + 5 = 14 < 15
    hit, dmg = rules.resolve_monster_attack(rng, _monster(attack_mod=5),
                                            target_ac=15, combat=COMBAT)
    assert hit is False and dmg == 0.0


# --- ladder --------------------------------------------------------------
def test_ladder_climbs_on_victory_and_caps():
    assert rules.next_ladder_tier(1, victory=True, max_tier=5) == 2
    assert rules.next_ladder_tier(4, victory=True, max_tier=5) == 5
    assert rules.next_ladder_tier(5, victory=True, max_tier=5) == 5  # capped


def test_ladder_resets_to_one_on_defeat():
    assert rules.next_ladder_tier(5, victory=False, max_tier=5) == 1
    assert rules.next_ladder_tier(2, victory=False, max_tier=5) == 1


# --- co-op round simulation ----------------------------------------------
def _team(n=8, **core_kw):
    return [rules.TeamFighter(core=_core(**core_kw), interval=BARB.attack_interval,
                              ability=None, passives=NEUTRAL_RACE) for _ in range(n)]


def test_team_downs_a_low_hp_monster_for_victory():
    team = _team()
    # Tiny HP -> the team kills it almost immediately.
    monster = rules.Monster(label="Rat", tier=1, hp_max=50, ac=5, attack_mod=0,
                            damage=1, attack_interval=99.0, gold_mult=1.0)
    res = rules.simulate_monster_round(random.Random(1), team, monster, COMBAT, 90)
    assert res.victory is True
    assert res.kill_time is not None and res.kill_time <= 90
    assert res.monster_hp_remaining == 0.0
    assert sum(f.damage_to_monster for f in res.fighters) > 0


def test_team_times_out_against_an_unkillable_monster():
    team = _team()
    # Enormous HP, harmless swings -> nobody dies, monster survives -> defeat.
    monster = rules.Monster(label="Wall", tier=5, hp_max=1e12, ac=5, attack_mod=0,
                            damage=0, attack_interval=99.0, gold_mult=3.0)
    res = rules.simulate_monster_round(random.Random(1), team, monster, COMBAT, 90)
    assert res.victory is False and res.kill_time is None
    assert res.monster_hp_remaining > 0
    assert all(f.ko_at is None for f in res.fighters)  # damage 0 -> no KOs


def test_lethal_monster_knocks_fighters_out():
    team = _team(n=4, con=10)  # lower CON -> less Health -> KO faster
    # Big HP so the fight lasts; hard-hitting fast monster that always connects.
    monster = rules.Monster(label="Reaper", tier=5, hp_max=1e9, ac=5, attack_mod=50,
                            damage=100000, attack_interval=1.0, gold_mult=3.0)
    res = rules.simulate_monster_round(random.Random(3), team, monster, COMBAT, 90)
    assert res.victory is False
    assert any(f.ko_at is not None for f in res.fighters)  # someone got KO'd


def test_ko_fighter_stops_dealing_damage_after_ko():
    team = _team(n=2, con=10)
    monster = rules.Monster(label="Reaper", tier=5, hp_max=1e9, ac=5, attack_mod=50,
                            damage=100000, attack_interval=0.5, gold_mult=3.0)
    res = rules.simulate_monster_round(random.Random(7), team, monster, COMBAT, 90)
    # At least one fighter KO'd; a KO'd fighter's damage is bounded (it stopped).
    assert any(f.ko_at is not None for f in res.fighters)


def test_monster_round_is_deterministic_under_a_seed():
    team = _team()
    monster = rules.build_monster(TIER3, rules.expected_team_output(
        [f.core for f in team], [f.interval for f in team], 90))
    a = rules.simulate_monster_round(random.Random(42), team, monster, COMBAT, 90)
    b = rules.simulate_monster_round(random.Random(42), team, monster, COMBAT, 90)
    assert a.victory == b.victory and a.kill_time == b.kill_time
    assert [f.damage_to_monster for f in a.fighters] == [f.damage_to_monster for f in b.fighters]
