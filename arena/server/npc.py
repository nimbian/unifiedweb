"""House NPC generation.

When fewer than 10 real characters are queued, the arena fills the remaining
slots with NPCs so rounds always look full (PLAN.md §5.2). NPCs are clearly
labelled ``[NPC]``, never persisted as characters (their round entries carry
``character_id = NULL``), and excluded from leaderboards / Hall of Fame.
"""

from __future__ import annotations

import random

from . import content, rules
from .config import Config
from .models import Character

# Flavor names for filler fighters. Cosmetic only.
_NPC_NAMES = (
    "Rusty", "Grumbold", "Old Sparring Post", "Sir Practice", "Whetstone",
    "Dummy McFight", "Bramble", "Cask", "Turnip", "Gravel",
    "Mossback", "Pewter", "Scrap", "Flint", "Barrel",
)


def generate_npc(rng: random.Random, cfg: Config, level: int) -> Character:
    """Build a throwaway NPC fighter at ``level``. Not persisted; ``id`` is a
    sentinel and ``is_npc`` is True so results skip it for XP/leaderboards."""
    class_name = rng.choice(list(cfg.classes))
    cd = cfg.classes[class_name]
    # Match live !create: sorted-4d6 by class priority under the moore engine (R1),
    # independent per-stat roll under classic — so NPC fill is drawn from the same
    # distribution as the real characters they stand in for.
    stats = (
        rules.roll_sorted_stat_block(rng, cfg.stats, cd)
        if cfg.combat.engine == "moore"
        else rules.roll_stat_block(rng, cfg.stats)
    )
    # Fold the level's primary bumps into the stat block, matching real chars.
    stats[cd.primary] += (level - 1) * cfg.xp.per_level_primary_bonus

    sprites = cfg.assets.get("sprite_sets", {}).get(class_name)
    sprite = rng.choice(sprites) if sprites else f"{class_name}_01"

    return Character(
        id=0,  # sentinel; NPCs are never stored, entries use character_id=None
        user_id=None,
        name=f"[NPC] {rng.choice(_NPC_NAMES)}",
        class_name=class_name,
        race="npc",
        stats=stats,
        level=level,
        sprite_set=sprite,
        personality=rng.choice(content.PERSONALITIES),
        is_npc=True,
        owner_login=None,
    )
