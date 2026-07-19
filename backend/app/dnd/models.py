"""Read-only ORM models mapping the DnD bot's tables (separate database).

Only the columns the website displays are mapped. JSONB columns are mapped as
generic JSON (read-only; psycopg returns dicts/lists either way, and SQLite —
used by tests — supports JSON). See ``dndbot/db/migrations`` for the full DDL.
"""

from datetime import datetime

from sqlalchemy import JSON, BigInteger, Boolean, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime

from app.dnd.database import DndBase


class Player(DndBase):
    __tablename__ = "players"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # character key
    username: Mapped[str] = mapped_column(Text)
    char_name: Mapped[str | None] = mapped_column(Text)
    discord_id: Mapped[int | None] = mapped_column(BigInteger, index=True)  # owner
    slot: Mapped[int] = mapped_column(Integer, default=1)
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    hardcore: Mapped[bool] = mapped_column(Boolean, default=False)  # permadeath run
    speedrun: Mapped[bool] = mapped_column(Boolean, default=False)  # race to level 20

    class_: Mapped[str] = mapped_column("class", Text)
    level: Mapped[int] = mapped_column(Integer)
    xp: Mapped[int] = mapped_column(Integer)
    gold: Mapped[int] = mapped_column(Integer)
    hp: Mapped[int] = mapped_column(Integer)
    max_hp: Mapped[int] = mapped_column(Integer)

    strength: Mapped[int] = mapped_column(Integer)
    dexterity: Mapped[int] = mapped_column(Integer)
    constitution: Mapped[int] = mapped_column(Integer)
    intelligence: Mapped[int] = mapped_column(Integer)
    wisdom: Mapped[int] = mapped_column(Integer)
    charisma: Mapped[int] = mapped_column(Integer)

    current_zone: Mapped[str | None] = mapped_column(Text)
    bag_capacity: Mapped[int] = mapped_column(Integer)

    weapon: Mapped[str | None] = mapped_column(Text)
    armor: Mapped[str | None] = mapped_column(Text)
    charm: Mapped[str | None] = mapped_column(Text)
    weapon_gear_id: Mapped[int | None] = mapped_column(BigInteger)
    armor_gear_id: Mapped[int | None] = mapped_column(BigInteger)
    charm_gear_id: Mapped[int | None] = mapped_column(BigInteger)
    affix_bonuses: Mapped[dict | None] = mapped_column(JSON)

    subclass: Mapped[str | None] = mapped_column(Text)
    displayed_title: Mapped[str | None] = mapped_column(Text)
    resource: Mapped[int] = mapped_column(Integer, default=0)

    abyss_best_floor: Mapped[int] = mapped_column(Integer, default=0)
    abyss_weekly_floor: Mapped[int] = mapped_column(Integer, default=0)
    abyss_week: Mapped[str | None] = mapped_column(Text)
    duel_wins: Mapped[int] = mapped_column(Integer, default=0)
    duel_losses: Mapped[int] = mapped_column(Integer, default=0)
    daily_streak: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reached_level_20_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Gear(DndBase):
    __tablename__ = "gear"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    base_item_id: Mapped[str] = mapped_column(Text)
    slot: Mapped[str] = mapped_column(Text)
    rarity: Mapped[str] = mapped_column(Text)
    affixes: Mapped[list | None] = mapped_column(JSON)
    name: Mapped[str] = mapped_column(Text)
    equipped_slot: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(Text)


class Inventory(DndBase):
    __tablename__ = "inventory"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    item_id: Mapped[str] = mapped_column(Text, primary_key=True)
    quantity: Mapped[int] = mapped_column(Integer)


class Bestiary(DndBase):
    __tablename__ = "bestiary"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    monster_id: Mapped[str] = mapped_column(Text, primary_key=True)
    kills: Mapped[int] = mapped_column(Integer, default=0)
    first_killed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PlayerAchievement(DndBase):
    __tablename__ = "player_achievements"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    achievement_id: Mapped[str] = mapped_column(Text, primary_key=True)
    earned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WorldBoss(DndBase):
    __tablename__ = "world_boss"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    boss_id: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    max_hp: Mapped[int] = mapped_column(Integer)
    hp: Mapped[int] = mapped_column(Integer)
    ac: Mapped[int] = mapped_column(Integer)
    spawned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    defeated: Mapped[bool] = mapped_column(Boolean, default=False)
    defeated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BossDamage(DndBase):
    __tablename__ = "boss_damage"

    boss_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    damage: Mapped[int] = mapped_column(Integer, default=0)
