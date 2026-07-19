"""Response schemas for the DnD-adventure section.

Discord ids (``discord_id``) are serialized as strings to avoid the JS
``Number.MAX_SAFE_INTEGER`` precision loss, matching the rest of the API.
Character ``key`` (the bot's ``players.user_id``) can be a large snowflake too,
so it is also a string.
"""

from datetime import datetime

from pydantic import BaseModel


class CharacterSummary(BaseModel):
    """One row of the Adventurers table."""

    key: str                      # players.user_id (character key)
    char_name: str | None
    username: str
    discord_id: str | None        # owner
    class_id: str
    class_name: str | None
    subclass_name: str | None
    title: str | None
    level: int
    xp: int
    gold: int
    abyss_best_floor: int
    duel_wins: int
    duel_losses: int
    active: bool


class Ability(BaseModel):
    key: str                      # str / dex / con / int / wis / cha
    score: int
    modifier: int


class EquipmentSlot(BaseModel):
    slot: str                     # weapon / armor / charm
    name: str | None              # resolved item / gear-instance name (None if empty)
    rarity: str | None
    affixed: bool                 # True when a rolled affixed instance occupies the slot
    detail: str | None            # item description / dice / bonus blurb
    affixes: list = []            # raw affix entries for an affixed instance


class InventoryItem(BaseModel):
    item_id: str
    name: str | None
    type: str | None
    rarity: str | None
    quantity: int
    value: int


class BestiaryEntry(BaseModel):
    """A monster slot. Undiscovered monsters are masked to "????" like the bot."""

    monster_id: str
    name: str
    discovered: bool
    kills: int
    cr: float | None
    family: str | None


class EarnedAchievement(BaseModel):
    id: str
    name: str
    description: str | None
    emoji: str | None
    category: str | None
    earned_at: datetime | None


class CharacterDetail(BaseModel):
    key: str
    char_name: str | None
    username: str
    discord_id: str | None
    class_id: str
    class_name: str | None
    subclass_name: str | None
    title: str | None
    active: bool

    level: int
    xp: int
    gold: int
    hp: int
    max_hp: int
    resource: int
    max_resource: int

    abilities: list[Ability]
    armor_class: int
    proficiency: int
    current_zone: str | None

    bag_used: int
    bag_capacity: int
    abyss_best_floor: int
    abyss_weekly_floor: int
    duel_wins: int
    duel_losses: int
    daily_streak: int

    affix_bonuses: dict
    equipment: list[EquipmentSlot]
    inventory: list[InventoryItem]
    bestiary: list[BestiaryEntry]
    achievements: list[EarnedAchievement]


# ── leaderboard ──────────────────────────────────────────────────────────────
class LeaderEntry(BaseModel):
    key: str
    name: str
    class_name: str | None
    level: int
    value: int                    # the ranked metric


class ModeLeaderboard(BaseModel):
    """The set of boards for one character game mode."""

    by_level: list[LeaderEntry]   # value = level
    by_gold: list[LeaderEntry]
    by_abyss: list[LeaderEntry]   # value = best abyss floor
    by_duels: list[LeaderEntry]   # value = duel wins
    by_speedrun: list[LeaderEntry]  # value = seconds from creation to level 20 (lower = faster)


class DndLeaderboard(BaseModel):
    normal: ModeLeaderboard       # characters with neither the hardcore nor speedrun flag
    hardcore: ModeLeaderboard     # permadeath characters
    speedrun: ModeLeaderboard     # characters racing to level 20


# ── world boss ───────────────────────────────────────────────────────────────
class BossContributor(BaseModel):
    key: str
    name: str
    damage: int


class ActiveBoss(BaseModel):
    id: int
    name: str
    max_hp: int
    hp: int
    ac: int
    spawned_at: datetime | None
    contributors: list[BossContributor]


class DefeatedBoss(BaseModel):
    name: str
    max_hp: int
    defeated_at: datetime | None


class WorldBossView(BaseModel):
    active: ActiveBoss | None
    recent: list[DefeatedBoss]


# ── achievements catalog ─────────────────────────────────────────────────────
class AchievementInfo(BaseModel):
    id: str
    name: str
    description: str | None
    emoji: str | None
    category: str | None
    threshold: int | None
    earned_count: int


class AchievementsView(BaseModel):
    total_players: int
    achievements: list[AchievementInfo]
