"""Data access for the leaderboard.

Queries the same collections/users/mons join the rest of the app uses, but
without the multi-set LEFT JOIN — the leaderboard wants exactly one row per
owned card, not a row per (card, set) pair. Only real users (``users.did > 0``)
are considered, so system-owned (sold) cards never appear.
"""

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Row, Select, func, select
from sqlalchemy.orm import Session

from app.models import Collection, Mon, User

# A "Perfect 30" card has exactly this value.
PERFECT_VALUE = Decimal("10000")


class LeaderboardRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _base(self) -> Select:
        """Collections joined to their owner and mon (one row per owned card)."""
        return (
            select(
                User.name.label("user"),
                Collection.rwid.label("collection_id"),
                Mon.cr.label("cr"),
                Mon.name.label("name"),
                Mon.exp.label("exp"),
                Collection.grade.label("grade"),
                Collection.holo.label("holo"),
                Collection.ed.label("ed"),
                Collection.value.label("value"),
                Collection.date.label("date"),
            )
            .select_from(Collection)
            .join(User, Collection.uid == User.rwid)
            .join(Mon, Collection.monid == Mon.rwid)
            .where(User.did > 0)
        )

    def top_pulled_since(self, start: datetime) -> Sequence[Row]:
        """The highest-value card(s) pulled at/after ``start`` (ties included)."""
        max_value = self.db.execute(
            select(func.max(Collection.value))
            .select_from(Collection)
            .join(User, Collection.uid == User.rwid)
            .where(User.did > 0, Collection.date >= start)
        ).scalar()
        if max_value is None:
            return []
        stmt = (
            self._base()
            .where(Collection.date >= start, Collection.value == max_value)
            .order_by(User.name, Mon.name, Collection.rwid)
        )
        return self.db.execute(stmt).all()

    def perfect_thirty(self) -> Sequence[Row]:
        """Every card whose value is exactly 10000."""
        stmt = (
            self._base()
            .where(Collection.value == PERFECT_VALUE)
            .order_by(Mon.name, User.name, Collection.rwid)
        )
        return self.db.execute(stmt).all()

    # ── Whole-collection user standings ──────────────────────────────────────
    def top_collections(self, limit: int = 3) -> Sequence[Row]:
        """(user, did, value) — users ranked by total collection value, desc."""
        stmt = (
            select(
                User.name.label("user"),
                User.did.label("did"),
                func.coalesce(func.sum(Collection.value), 0).label("value"),
            )
            .select_from(Collection)
            .join(User, Collection.uid == User.rwid)
            .where(User.did > 0)
            .group_by(User.rwid, User.name, User.did)
            .order_by(func.sum(Collection.value).desc())
            .limit(limit)
        )
        return self.db.execute(stmt).all()

    def top_best_copy(self, limit: int = 3) -> Sequence[Row]:
        """(user, did, value) — users ranked by "best copy" value, desc.

        Best-copy value keeps only the most valuable copy of each mon a user owns
        (one of each), then sums — the deduped worth of a collection.
        """
        per_mon = (
            select(
                Collection.uid.label("uid"),
                func.max(Collection.value).label("maxval"),
            )
            .group_by(Collection.uid, Collection.monid)
            .subquery()
        )
        stmt = (
            select(
                User.name.label("user"),
                User.did.label("did"),
                func.coalesce(func.sum(per_mon.c.maxval), 0).label("value"),
            )
            .select_from(per_mon)
            .join(User, per_mon.c.uid == User.rwid)
            .where(User.did > 0)
            .group_by(User.rwid, User.name, User.did)
            .order_by(func.sum(per_mon.c.maxval).desc())
            .limit(limit)
        )
        return self.db.execute(stmt).all()

    def top_pristine(self, limit: int = 3) -> Sequence[Row]:
        """(user, did, count) — users with the most "pristine" cards, desc.

        A pristine card is grade 10 and holo (holo is an int 0/1, occasionally
        NULL, so NULL/0 counts as not-holo).
        """
        stmt = (
            select(
                User.name.label("user"),
                User.did.label("did"),
                func.count(Collection.rwid).label("count"),
            )
            .select_from(Collection)
            .join(User, Collection.uid == User.rwid)
            .where(
                User.did > 0,
                Collection.grade == 10,
                func.coalesce(Collection.holo, 0) != 0,
            )
            .group_by(User.rwid, User.name, User.did)
            .order_by(func.count(Collection.rwid).desc())
            .limit(limit)
        )
        return self.db.execute(stmt).all()
