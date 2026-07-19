"""R5 shop economy (docs/R4_R6_plan.md): gear grants, gold accrual, the naked-gate
cap, and arena integration (performance gold replaces betting, gear boosts combat).
Config parsing/validation is here too; the chat commands live in test_commands."""

from __future__ import annotations

import asyncio
import random
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from server import rules
from server.arena import Arena
from server.config import Config, ConfigError, ShopItem
from server.events import RecordingSink
from server.store import MemoryStore

GAME_CONFIG = Path(__file__).resolve().parents[1] / "config" / "game.toml"
CFG = Config.load(GAME_CONFIG)
COMBAT = CFG.combat
BARB = CFG.classes["barbarian"]
STATS = {"STR": 16, "DEX": 12, "CON": 14, "INT": 10, "WIS": 10, "CHA": 12}


def _fixed_now() -> datetime:
    return datetime(2026, 7, 9, 12, 0, 0, tzinfo=UTC)


async def _nosleep(_seconds: float) -> None:
    return None


# --- gear grants ---------------------------------------------------------
def test_resolve_gear_sums_item_grants():
    items = [
        ShopItem("a", "weapon", "A", 100, ap_mult=0.05, crit_pp=5),
        ShopItem("b", "trinket", "B", 100, ap_mult=0.02, loot_pp=2.0, speed_mult=0.03),
    ]
    g = rules.resolve_gear(items)
    assert g.ap_mult == pytest.approx(0.07)
    assert g.crit_pp == 5
    assert g.loot_pp == pytest.approx(2.0)
    assert g.speed_mult == pytest.approx(0.03)


def test_apply_gear_to_core_boosts_stats_and_respects_cap():
    core = rules.derive_core_stats(STATS, BARB, COMBAT)
    gear = rules.GearBundle(ap_mult=0.08, ac_bonus=2, crit_pp=10, loot_pp=3.0)
    geared = rules.apply_gear_to_core(core, gear, COMBAT)
    assert geared.attack_power == pytest.approx(min(COMBAT.ap_cap, core.attack_power * 1.08))
    assert geared.armor_class == core.armor_class + 2
    assert geared.crit_damage_mult == pytest.approx(core.crit_damage_mult + 0.10)
    assert geared.loot_bonus == pytest.approx(core.loot_bonus + 3.0)


def test_apply_gear_caps_attack_power():
    core = rules.CoreStats(attack_power=990, attack_modifier=3, attack_speed=250,
                           health=450, armor_class=16, crit_damage_mult=1.5, loot_bonus=2)
    geared = rules.apply_gear_to_core(core, rules.GearBundle(ap_mult=0.5), COMBAT)
    assert geared.attack_power == COMBAT.ap_cap  # capped, not 990*1.5


def test_no_gear_is_identity():
    core = rules.derive_core_stats(STATS, BARB, COMBAT)
    assert rules.apply_gear_to_core(core, rules.NO_GEAR, COMBAT) is core


def test_geared_interval_shortens_with_speed():
    assert rules.geared_interval(3.0, rules.GearBundle(speed_mult=0.5)) == pytest.approx(2.0)
    assert rules.geared_interval(3.0, rules.NO_GEAR) == 3.0


def test_gold_from_damage():
    assert rules.gold_from_damage(1000, 2.5, 1.0) == 25
    assert rules.gold_from_damage(1000, 2.5, 2.0) == 50   # tier multiplier
    assert rules.gold_from_damage(0, 50.0, 3.0) == 0


# --- config caps ---------------------------------------------------------
def test_shop_disabled_by_default():
    assert CFG.shop.enabled is False and len(CFG.shop.items) == 9


def test_full_gear_over_cap_is_rejected(tmp_path):
    text = GAME_CONFIG.read_text(encoding="utf-8").replace(
        "ap_mult = 0.06", "ap_mult = 0.20"  # mithril blade blows past max_ap_mult
    )
    bad = tmp_path / "shop.toml"
    bad.write_text(text, encoding="utf-8")
    with pytest.raises(ConfigError):
        Config.load(bad)


# --- arena integration ---------------------------------------------------
def _shop_arena(store, seed=5):
    cfg = Config.load(GAME_CONFIG)
    cfg.combat = replace(cfg.combat, engine="moore")
    cfg.round = replace(cfg.round, event_chance=0.0)
    cfg.shop = replace(cfg.shop, enabled=True)
    sink = RecordingSink()
    arena = Arena(cfg, store, sink, rng=random.Random(seed), sleep=_nosleep, now=_fixed_now)
    return arena, sink, cfg


def _make_char(store, login, name, cls="barbarian"):
    uid = store.add_user(login)
    return store.create_character(user_id=uid, name=name, class_name=cls, race="human",
                                  stats=dict(STATS), sprite_set=f"{cls}_01", level=5)


def test_shop_enabled_pays_performance_gold_and_skips_betting():
    store = MemoryStore()
    arena, sink, _ = _shop_arena(store)
    ch = _make_char(store, "brian", "Thorak")
    gold_before = asyncio.run(store.get_gold(ch.user_id))
    asyncio.run(arena.enqueue(ch.id, ch.user_id))
    asyncio.run(arena.run_once())

    gold_after = asyncio.run(store.get_gold(ch.user_id))
    assert gold_after > gold_before  # earned performance gold from its damage
    # A gold-earned ticker was emitted; no bet settlement ticker (betting retired).
    kinds = [t["kind"] for t in sink.of_type("ticker")]
    assert "bet" not in kinds


def test_buying_gear_boosts_combat_damage():
    # Same character + seed, with vs without a big weapon -> geared deals more.
    def run(equip: bool) -> int:
        store = MemoryStore()
        arena, _, _ = _shop_arena(store, seed=9)
        ch = _make_char(store, "brian", "Thorak")
        if equip:
            asyncio.run(store.buy_item(ch.user_id, ch.id, "weapon", "mithril_blade", 0))
        asyncio.run(arena.enqueue(ch.id, ch.user_id))
        out = asyncio.run(arena.run_once())
        return next(e.total_damage for e in out.entries if e.character_id == ch.id)

    assert run(equip=True) > run(equip=False)


def test_gear_does_not_apply_when_shop_disabled():
    # A character with a purchased item deals the same as unequipped when shop off.
    def run(shop_on: bool) -> int:
        store = MemoryStore()
        cfg = Config.load(GAME_CONFIG)
        cfg.combat = replace(cfg.combat, engine="moore")
        cfg.round = replace(cfg.round, event_chance=0.0)
        cfg.shop = replace(cfg.shop, enabled=shop_on)
        arena = Arena(cfg, store, RecordingSink(), rng=random.Random(9),
                      sleep=_nosleep, now=_fixed_now)
        ch = _make_char(store, "brian", "Thorak")
        store.characters[ch.id].equipment = {"weapon": "mithril_blade"}
        asyncio.run(arena.enqueue(ch.id, ch.user_id))
        out = asyncio.run(arena.run_once())
        return next(e.total_damage for e in out.entries if e.character_id == ch.id)

    assert run(shop_on=False) < run(shop_on=True)  # gear inert until the shop is enabled
