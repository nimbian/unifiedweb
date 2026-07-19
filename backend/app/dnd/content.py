"""Static DnD game content (a bundled snapshot of the bot's ``data/*.json``).

The bot stores ids in the database (``class``, ``weapon``, ``monster_id`` …) and
resolves their display names/stats from JSON content files. We bundle a snapshot
of those files here so the website can do the same id -> name resolution without
reaching into the bot's source tree at runtime. Refresh by re-copying the bot's
``data/*.json`` if its content changes.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_DATA = Path(__file__).resolve().parent / "data"


@lru_cache(maxsize=None)
def _load(name: str) -> dict | list:
    with (_DATA / name).open(encoding="utf-8") as fh:
        return json.load(fh)


# ── classes ──────────────────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def classes() -> dict[str, dict]:
    return _load("classes.json")  # type: ignore[return-value]


def class_def(class_id: str | None) -> dict | None:
    return classes().get(class_id) if class_id else None


def class_name(class_id: str | None) -> str | None:
    c = class_def(class_id)
    return c.get("name") if c else class_id


# ── items (weapons/armor/charms/potions/loot) ────────────────────────────────
@lru_cache(maxsize=1)
def items() -> dict[str, dict]:
    return _load("items.json")  # type: ignore[return-value]


def item_def(item_id: str | None) -> dict | None:
    return items().get(item_id) if item_id else None


def item_name(item_id: str | None) -> str | None:
    it = item_def(item_id)
    return it.get("name") if it else item_id


# ── monsters ─────────────────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def monsters() -> dict[str, dict]:
    return _load("monsters.json")  # type: ignore[return-value]


def monster_def(monster_id: str | None) -> dict | None:
    return monsters().get(monster_id) if monster_id else None


# ── achievements ─────────────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def achievements() -> list[dict]:
    return _load("achievements.json").get("achievements", [])  # type: ignore[union-attr]


@lru_cache(maxsize=1)
def _achievements_by_id() -> dict[str, dict]:
    return {a["id"]: a for a in achievements()}


def achievement_def(achievement_id: str) -> dict | None:
    return _achievements_by_id().get(achievement_id)


# ── subclasses (keyed per class) ─────────────────────────────────────────────
@lru_cache(maxsize=1)
def _subclasses_by_id() -> dict[str, dict]:
    data = _load("subclasses.json")
    out: dict[str, dict] = {}
    for key, val in data.items():  # type: ignore[union-attr]
        if key.startswith("_") or not isinstance(val, list):
            continue
        for sub in val:
            out[sub["id"]] = sub
    return out


def subclass_name(subclass_id: str | None) -> str | None:
    if not subclass_id:
        return None
    sub = _subclasses_by_id().get(subclass_id)
    return sub.get("name") if sub else subclass_id


# ── derived combat math (mirrors engine/progression + resources) ─────────────
def ability_modifier(score: int) -> int:
    return (score - 10) // 2


def proficiency_bonus(level: int) -> int:
    return 2 + (level - 1) // 4


@lru_cache(maxsize=1)
def _resource_cfg() -> dict:
    return _load("economy.json").get("resource", {})  # type: ignore[union-attr]


def max_resource(level: int) -> int:
    cfg = _resource_cfg()
    return int(cfg.get("base", 4)) + int(cfg.get("per_level", 1)) * level
