"""Read-only data access for the DnD bot's database."""

from collections.abc import Sequence
from typing import Literal

from sqlalchemy import ColumnElement, Row, desc, func, select
from sqlalchemy.orm import Session

from app.dnd.models import (
    Bestiary,
    BossDamage,
    Gear,
    Inventory,
    Player,
    PlayerAchievement,
    WorldBoss,
)

# The three character game modes the leaderboards are split across.
Mode = Literal["normal", "hardcore", "speedrun"]


def _mode_conditions(mode: Mode) -> tuple[ColumnElement[bool], ...]:
    """WHERE conditions selecting characters of a single mode. The groups are
    disjoint: speedrun wins over hardcore, and normal is neither flag set."""
    if mode == "speedrun":
        return (Player.speedrun.is_(True),)
    if mode == "hardcore":
        return (Player.hardcore.is_(True), Player.speedrun.is_(False))
    return (Player.hardcore.is_(False), Player.speedrun.is_(False))


class DndRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ── characters ───────────────────────────────────────────────────────────
    def list_characters(self) -> Sequence[Player]:
        stmt = select(Player).order_by(Player.level.desc(), Player.xp.desc(), Player.user_id)
        return self.db.execute(stmt).scalars().all()

    def get_character(self, key: int) -> Player | None:
        return self.db.get(Player, key)

    def get_gear(self, gear_id: int) -> Gear | None:
        return self.db.get(Gear, gear_id)

    def get_inventory(self, user_id: int) -> Sequence[Inventory]:
        stmt = select(Inventory).where(Inventory.user_id == user_id).order_by(Inventory.item_id)
        return self.db.execute(stmt).scalars().all()

    def inventory_used(self, user_id: int) -> int:
        val = self.db.execute(
            select(func.coalesce(func.sum(Inventory.quantity), 0)).where(
                Inventory.user_id == user_id
            )
        ).scalar_one()
        return int(val)

    def bestiary_kills(self, user_id: int) -> dict[str, int]:
        rows = self.db.execute(
            select(Bestiary.monster_id, Bestiary.kills).where(Bestiary.user_id == user_id)
        ).all()
        return {r.monster_id: r.kills for r in rows}

    def earned_achievements(self, user_id: int) -> Sequence[PlayerAchievement]:
        stmt = (
            select(PlayerAchievement)
            .where(PlayerAchievement.user_id == user_id)
            .order_by(PlayerAchievement.earned_at)
        )
        return self.db.execute(stmt).scalars().all()

    # ── leaderboards ─────────────────────────────────────────────────────────
    # Every board is scoped to one character mode (normal / hardcore / speedrun).
    def top_by_level(self, mode: Mode, limit: int = 10) -> Sequence[Player]:
        stmt = (
            select(Player)
            .where(*_mode_conditions(mode))
            .order_by(Player.level.desc(), Player.xp.desc())
            .limit(limit)
        )
        return self.db.execute(stmt).scalars().all()

    def top_by_gold(self, mode: Mode, limit: int = 10) -> Sequence[Player]:
        stmt = (
            select(Player)
            .where(*_mode_conditions(mode))
            .order_by(Player.gold.desc())
            .limit(limit)
        )
        return self.db.execute(stmt).scalars().all()

    def top_by_abyss(self, mode: Mode, limit: int = 10) -> Sequence[Player]:
        stmt = (
            select(Player)
            .where(Player.abyss_best_floor > 0, *_mode_conditions(mode))
            .order_by(Player.abyss_best_floor.desc())
            .limit(limit)
        )
        return self.db.execute(stmt).scalars().all()

    def top_by_duels(self, mode: Mode, limit: int = 10) -> Sequence[Player]:
        stmt = (
            select(Player)
            .where(Player.duel_wins > 0, *_mode_conditions(mode))
            .order_by(Player.duel_wins.desc())
            .limit(limit)
        )
        return self.db.execute(stmt).scalars().all()

    def speedrun_completions(self, mode: Mode) -> Sequence[Player]:
        """Characters of the given mode that have reached level 20, with both
        timestamps present.

        The elapsed time (and thus ordering) is computed in the service to keep
        the query database-agnostic — interval arithmetic differs across engines.
        """
        stmt = select(Player).where(
            Player.created_at.is_not(None),
            Player.reached_level_20_at.is_not(None),
            *_mode_conditions(mode),
        )
        return self.db.execute(stmt).scalars().all()

    # ── world boss ───────────────────────────────────────────────────────────
    def active_boss(self) -> WorldBoss | None:
        stmt = (
            select(WorldBoss)
            .where(WorldBoss.defeated.is_(False))
            .order_by(WorldBoss.id.desc())
            .limit(1)
        )
        return self.db.execute(stmt).scalars().first()

    def boss_contributors(self, boss_id: int, limit: int = 15) -> Sequence[Row]:
        stmt = (
            select(
                Player.user_id.label("key"),
                Player.char_name.label("char_name"),
                Player.username.label("username"),
                BossDamage.damage.label("damage"),
            )
            .join(Player, Player.user_id == BossDamage.user_id, isouter=True)
            .where(BossDamage.boss_id == boss_id)
            .order_by(BossDamage.damage.desc())
            .limit(limit)
        )
        return self.db.execute(stmt).all()

    def recent_defeated(self, limit: int = 5) -> Sequence[WorldBoss]:
        stmt = (
            select(WorldBoss)
            .where(WorldBoss.defeated.is_(True))
            .order_by(desc(WorldBoss.defeated_at))
            .limit(limit)
        )
        return self.db.execute(stmt).scalars().all()

    # ── achievements ─────────────────────────────────────────────────────────
    def achievement_counts(self) -> dict[str, int]:
        rows = self.db.execute(
            select(PlayerAchievement.achievement_id, func.count())
            .group_by(PlayerAchievement.achievement_id)
        ).all()
        return {r[0]: r[1] for r in rows}

    def player_count(self) -> int:
        return int(self.db.execute(select(func.count()).select_from(Player)).scalar_one())
