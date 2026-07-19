"""Tests for config loading, validation, and the tuner's coeff-override helper."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from server.config import Config, ConfigError, with_coeffs
from server.sim import write_coeffs_to_toml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GAME_CONFIG = PROJECT_ROOT / "config" / "game.toml"

EXPECTED_CLASSES = {
    "barbarian", "fighter", "rogue", "monk",
    "paladin", "ranger", "warlock", "wizard",
    # Phase 2 additions:
    "cleric", "bard", "artificer", "druid", "sorcerer",
}


def test_real_config_loads_and_validates():
    cfg = Config.load(GAME_CONFIG)
    assert set(cfg.classes) == EXPECTED_CLASSES
    assert len(cfg.damage.roll_multipliers) == 18
    assert cfg.damage.display_scale > 0
    assert cfg.round.lifespan_battles == 25
    assert cfg.xp.levels_max == 10


def test_wizard_primary_is_wis_by_design():
    cfg = Config.load(GAME_CONFIG)
    assert cfg.classes["wizard"].primary == "WIS"  # intentional — do not "fix" to INT


def test_class_attack_intervals_match_spec():
    cfg = Config.load(GAME_CONFIG)
    expected = {
        "barbarian": 4.0, "fighter": 3.0, "rogue": 2.0, "monk": 1.5,
        "paladin": 3.5, "ranger": 2.5, "warlock": 4.0, "wizard": 5.0,
        "cleric": 3.5, "bard": 2.5, "artificer": 3.0, "druid": 4.0, "sorcerer": 4.5,
    }
    assert {name: c.attack_interval for name, c in cfg.classes.items()} == expected


def test_phase2_classes_have_spec_stats_and_abilities():
    cfg = Config.load(GAME_CONFIG)
    # primary/secondary are fixed by PLAN.md §4.2; abilities were designed.
    spec = {
        "cleric": ("STR", "WIS"), "bard": ("CHA", "DEX"), "artificer": ("INT", "DEX"),
        "druid": ("WIS", "CON"), "sorcerer": ("CHA", "CON"),
    }
    for name, (primary, secondary) in spec.items():
        cd = cfg.classes[name]
        assert (cd.primary, cd.secondary) == (primary, secondary)
        assert cd.ability is not None and cd.ability.kind in (
            "damage_buff", "no_miss", "crit_buff", "burst"
        )


def test_with_coeffs_overrides_only_named_classes():
    cfg = Config.load(GAME_CONFIG)
    tuned = with_coeffs(cfg, {"wizard": 0.123})
    assert tuned.classes["wizard"].coeff == 0.123
    assert tuned.classes["barbarian"].coeff == cfg.classes["barbarian"].coeff
    # original config is untouched
    assert cfg.classes["wizard"].coeff != 0.123


def _write_min_config(path: Path, roll_table_len: int) -> Path:
    mults = ", ".join(["1.0"] * roll_table_len)
    path.write_text(
        f"""
[timings]
intermission_seconds = 90
roster_lock_seconds = 10
combat_seconds = 60
results_seconds = 20
[round]
fighters_per_round = 10
roster_limit = 3
lifespan_battles = 20
[stats]
dice = 4
sides = 6
keep = 3
reroll_below = 2
[damage]
roll_multipliers = [{mults}]
crit_primary_mult = 2.0
crit_final_mult = 2.0
display_scale = 10.0
[xp]
levels_max = 10
base_per_round = 100
placement_bonus = [150, 100, 60, 30, 30]
curve_coeff = 100
per_level_primary_bonus = 1
[classes.barbarian]
primary = "STR"
secondary = "CON"
attack_interval = 4.0
coeff = 1.0
""",
        encoding="utf-8",
    )
    return path


def test_wrong_roll_table_length_is_rejected(tmp_path):
    bad = _write_min_config(tmp_path / "bad.toml", roll_table_len=17)
    with pytest.raises(ConfigError):
        Config.load(bad)


def test_minimal_valid_config_loads(tmp_path):
    good = _write_min_config(tmp_path / "good.toml", roll_table_len=18)
    cfg = Config.load(good)
    assert cfg.classes["barbarian"].coeff == 1.0


def test_leveling_mode_defaults_to_placement():
    cfg = Config.load(GAME_CONFIG)
    assert cfg.xp.mode == "placement"


def test_invalid_leveling_mode_is_rejected(tmp_path):
    good = _write_min_config(tmp_path / "m.toml", roll_table_len=18)
    text = good.read_text(encoding="utf-8").replace("[xp]", '[xp]\nmode = "bogus"')
    good.write_text(text, encoding="utf-8")
    with pytest.raises(ConfigError):
        Config.load(good)


def test_queue_selection_defaults_to_fifo():
    cfg = Config.load(GAME_CONFIG)
    assert cfg.queue.selection == "fifo"
    assert cfg.queue.miss_weight >= 0


def test_minimal_config_without_queue_section_defaults_fifo(tmp_path):
    # The [queue] table is optional; absence must not break loading.
    good = _write_min_config(tmp_path / "noqueue.toml", roll_table_len=18)
    cfg = Config.load(good)
    assert cfg.queue.selection == "fifo"


def test_invalid_queue_selection_is_rejected(tmp_path):
    good = _write_min_config(tmp_path / "q.toml", roll_table_len=18)
    text = good.read_text(encoding="utf-8") + '\n[queue]\nselection = "nonsense"\n'
    good.write_text(text, encoding="utf-8")
    with pytest.raises(ConfigError):
        Config.load(good)


def test_arena_boots_closed_by_default():
    cfg = Config.load(GAME_CONFIG)
    assert cfg.arena.open_on_launch is False  # shipped default: mods !start


def test_minimal_config_without_arena_section_defaults_closed(tmp_path):
    # The [arena] table is optional; absence must not break loading.
    good = _write_min_config(tmp_path / "noarena.toml", roll_table_len=18)
    cfg = Config.load(good)
    assert cfg.arena.open_on_launch is False


def test_arena_open_on_launch_parses_true(tmp_path):
    good = _write_min_config(tmp_path / "arena.toml", roll_table_len=18)
    text = good.read_text(encoding="utf-8") + "\n[arena]\nopen_on_launch = true\n"
    good.write_text(text, encoding="utf-8")
    cfg = Config.load(good)
    assert cfg.arena.open_on_launch is True


def test_monsters_default_disabled_and_tiers_parse():
    cfg = Config.load(GAME_CONFIG)
    assert cfg.monsters.enabled is False  # shipped default: every_n = 0
    assert cfg.monsters.max_tier == 5
    assert cfg.monsters.tier(1).gold_mult == 1.0
    assert cfg.monsters.tier(5).gold_mult == 3.0


def test_monsters_enabled_requires_moore_engine(tmp_path):
    text = GAME_CONFIG.read_text(encoding="utf-8").replace(
        "every_n          = 0", "every_n          = 4"
    )
    bad = tmp_path / "mon.toml"
    bad.write_text(text, encoding="utf-8")
    with pytest.raises(ConfigError):  # engine is still "classic"
        Config.load(bad)


def test_monsters_enabled_under_moore_loads(tmp_path):
    text = GAME_CONFIG.read_text(encoding="utf-8")
    text = text.replace("every_n          = 0", "every_n          = 4")
    text = text.replace('engine            = "classic"', 'engine            = "moore"')
    ok = tmp_path / "mon_moore.toml"
    ok.write_text(text, encoding="utf-8")
    cfg = Config.load(ok)
    assert cfg.monsters.enabled and cfg.monsters.every_n == 4


def _two_class_toml(path: Path, *, with_moore: bool) -> Path:
    moore_line = "moore_coeff = 0.5\n" if with_moore else ""
    path.write_text(
        f"""[classes.barbarian]
primary = "STR"
secondary = "CON"
attack_interval = 4.0
coeff = 1.0
{moore_line}
[classes.fighter]
primary = "STR"
secondary = "DEX"
attack_interval = 3.0
coeff = 0.8
{moore_line}""",
        encoding="utf-8",
    )
    return path


def test_write_moore_coeff_replaces_existing_no_duplicate(tmp_path):
    # Regression: an existing moore_coeff must be overwritten in place, never
    # duplicated (a duplicate key makes tomllib reject the file entirely).
    cfg = _two_class_toml(tmp_path / "cfg.toml", with_moore=True)
    write_coeffs_to_toml(cfg, {"barbarian": 0.991, "fighter": 0.7977}, field="moore_coeff")
    text = cfg.read_text(encoding="utf-8")
    lines = [ln for ln in text.splitlines() if ln.strip().startswith("moore_coeff")]
    assert len(lines) == 2  # one per class, not four
    data = tomllib.loads(text)  # would raise TOMLDecodeError on a duplicate key
    assert data["classes"]["barbarian"]["moore_coeff"] == 0.991
    assert data["classes"]["fighter"]["moore_coeff"] == 0.7977
    assert data["classes"]["barbarian"]["coeff"] == 1.0  # classic coeff untouched


def test_write_moore_coeff_inserts_after_coeff_when_absent(tmp_path):
    cfg = _two_class_toml(tmp_path / "cfg.toml", with_moore=False)
    write_coeffs_to_toml(cfg, {"barbarian": 0.42, "fighter": 0.37}, field="moore_coeff")
    text = cfg.read_text(encoding="utf-8")
    data = tomllib.loads(text)
    assert data["classes"]["barbarian"]["moore_coeff"] == 0.42
    assert data["classes"]["fighter"]["moore_coeff"] == 0.37
    # inserted directly after the classic coeff line
    body = text.splitlines()
    ci = body.index("coeff = 1.0")
    assert body[ci + 1] == "moore_coeff = 0.42"
