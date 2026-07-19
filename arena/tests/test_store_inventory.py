"""Gear inventory store semantics (migration 0007): buying owns + equips,
replacing keeps the old item, unequip frees the slot without losing the item.
MemoryStore is the reference implementation (PgStore mirrors it in SQL)."""

from __future__ import annotations

import asyncio

from server.store import SHOP_INSUFFICIENT, SHOP_OK, SHOP_OWNED, MemoryStore

STATS = {"STR": 15, "DEX": 14, "CON": 13, "INT": 12, "WIS": 11, "CHA": 10}


def _char(store: MemoryStore, gold: int = 5000):
    uid = store.add_user("brian")
    store.users[uid]["gold"] = gold
    return store.create_character(
        user_id=uid, name="Thorak", class_name="barbarian", race="orc",
        stats=dict(STATS), sprite_set="barb_01",
    )


def test_buy_owns_and_equips():
    store = MemoryStore()
    ch = _char(store)
    assert asyncio.run(store.buy_item(ch.user_id, ch.id, "weapon", "iron_sword", 500)) == SHOP_OK
    assert asyncio.run(store.get_inventory(ch.id)) == ["iron_sword"]
    assert asyncio.run(store.get_equipment(ch.id)) == {"weapon": "iron_sword"}
    assert store.users[ch.user_id]["gold"] == 4500


def test_buy_replacement_keeps_old_item_in_inventory():
    store = MemoryStore()
    ch = _char(store)
    asyncio.run(store.buy_item(ch.user_id, ch.id, "weapon", "iron_sword", 500))
    asyncio.run(store.buy_item(ch.user_id, ch.id, "weapon", "steel_sword", 1200))
    assert asyncio.run(store.get_equipment(ch.id)) == {"weapon": "steel_sword"}
    assert asyncio.run(store.get_inventory(ch.id)) == ["iron_sword", "steel_sword"]


def test_buy_already_owned_is_free_noop():
    store = MemoryStore()
    ch = _char(store)
    asyncio.run(store.buy_item(ch.user_id, ch.id, "weapon", "iron_sword", 500))
    gold_before = store.users[ch.user_id]["gold"]
    assert (
        asyncio.run(store.buy_item(ch.user_id, ch.id, "weapon", "iron_sword", 500))
        == SHOP_OWNED
    )
    assert store.users[ch.user_id]["gold"] == gold_before  # not charged twice


def test_buy_insufficient_gold():
    store = MemoryStore()
    ch = _char(store, gold=10)
    assert (
        asyncio.run(store.buy_item(ch.user_id, ch.id, "weapon", "iron_sword", 500))
        == SHOP_INSUFFICIENT
    )
    assert asyncio.run(store.get_inventory(ch.id)) == []


def test_equip_requires_ownership():
    store = MemoryStore()
    ch = _char(store)
    assert asyncio.run(store.equip_item(ch.id, "weapon", "iron_sword")) is False
    asyncio.run(store.add_item(ch.id, "iron_sword"))
    assert asyncio.run(store.equip_item(ch.id, "weapon", "iron_sword")) is True
    assert asyncio.run(store.get_equipment(ch.id)) == {"weapon": "iron_sword"}


def test_unequip_frees_slot_and_keeps_item():
    store = MemoryStore()
    ch = _char(store)
    asyncio.run(store.buy_item(ch.user_id, ch.id, "weapon", "iron_sword", 500))
    assert asyncio.run(store.unequip_item(ch.id, "weapon")) is True
    assert asyncio.run(store.get_equipment(ch.id)) == {}
    assert asyncio.run(store.get_inventory(ch.id)) == ["iron_sword"]
    assert asyncio.run(store.unequip_item(ch.id, "weapon")) is False  # already empty


def test_swap_between_owned_items():
    store = MemoryStore()
    ch = _char(store)
    asyncio.run(store.buy_item(ch.user_id, ch.id, "weapon", "iron_sword", 500))
    asyncio.run(store.buy_item(ch.user_id, ch.id, "weapon", "steel_sword", 1200))
    assert asyncio.run(store.equip_item(ch.id, "weapon", "iron_sword")) is True
    assert asyncio.run(store.get_equipment(ch.id)) == {"weapon": "iron_sword"}


def test_retired_roster_and_get_character():
    store = MemoryStore()
    ch = _char(store)
    assert asyncio.run(store.retired_roster(ch.user_id)) == []
    asyncio.run(store.retire_character(ch.id))
    retired = asyncio.run(store.retired_roster(ch.user_id))
    assert [c.id for c in retired] == [ch.id]
    # get_character sees retired characters (public sheets); living lookup doesn't.
    assert asyncio.run(store.get_character(ch.id)) is not None
    assert asyncio.run(store.get_living_character(ch.id)) is None
