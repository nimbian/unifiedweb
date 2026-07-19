"""Data access for sets / expansions (ports the set queries from ``sqlhelper.py``).

The numeric ``sets.rwid`` ranges that classify a set are defined here once as
named constants instead of being inlined into query strings as in the original.
"""

from collections.abc import Sequence

from sqlalchemy import Row, and_, distinct, func, select
from sqlalchemy.orm import Session

from app.models import CardInSet, Collection, CompletedSet, Expansion, Mon, Set, User

# rwid range semantics inferred from the legacy queries.
BASE_SET_MAX = 0          # rwid <= 0           -> base sets
CREATURE_MIN, CREATURE_MAX = 1, 50     # 0 < rwid < 50
ITEM_MIN, ITEM_MAX = 50, 99            # 50 <= rwid < 99
LOCATION_MIN, LOCATION_MAX = 300, 400  # 300 <= rwid < 400


class SetRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def creature_set_names(self) -> Sequence[str]:
        """Was ``getMonSets`` — creature sets that are not also expansions."""
        expansion_names = select(Expansion.expansion)
        stmt = (
            select(Set.name)
            .where(
                and_(
                    Set.rwid > BASE_SET_MAX,
                    Set.rwid < CREATURE_MAX,
                    Set.name.notin_(expansion_names),
                )
            )
            .order_by(Set.rwid)
        )
        return list(self.db.execute(stmt).scalars().all())

    def item_set_names(self) -> Sequence[str]:
        """Was ``getItemSets``."""
        stmt = (
            select(Set.name)
            .where(and_(Set.rwid >= ITEM_MIN, Set.rwid < ITEM_MAX))
            .order_by(Set.rwid)
        )
        return list(self.db.execute(stmt).scalars().all())

    def location_set_names(self) -> Sequence[str]:
        """Was ``getLocSets``."""
        stmt = (
            select(Set.name)
            .where(and_(Set.rwid >= LOCATION_MIN, Set.rwid < LOCATION_MAX))
            .order_by(Set.rwid)
        )
        return list(self.db.execute(stmt).scalars().all())

    def expansions(self) -> Sequence[Row]:
        """Was ``getExpansions`` — (exp, expansion) ordered by the set's rwid."""
        stmt = (
            select(Expansion.exp.label("exp"), Expansion.expansion.label("name"))
            .join(Set, Expansion.expansion == Set.name)
            .order_by(Set.rwid)
        )
        return self.db.execute(stmt).all()

    def cards_in_set_by_name(self, name: str) -> Sequence[Row]:
        """Was ``getCardsInSetByName`` — (monid, mon name) for a named set."""
        stmt = (
            select(CardInSet.monid.label("monid"), Mon.name.label("name"))
            .join(Mon, CardInSet.monid == Mon.rwid)
            .join(Set, CardInSet.setid == Set.rwid)
            .where(Set.name == name)
        )
        return self.db.execute(stmt).all()

    def base_set_cards(self, klass: str | None = None) -> Sequence[Row]:
        """Was ``getBaseSetCards`` — (monid, mon name) for base sets (rwid <= 0).

        ``klass`` optionally restricts to a single mon class ('Monsters' / 'Item'
        / 'Locations') so the base sets can be shown broken out per category.
        """
        stmt = (
            select(CardInSet.monid.label("monid"), Mon.name.label("name"))
            .join(Mon, CardInSet.monid == Mon.rwid)
            .join(Set, CardInSet.setid == Set.rwid)
            .where(Set.rwid <= BASE_SET_MAX)
        )
        if klass is not None:
            stmt = stmt.where(Mon.class_ == klass)
        return self.db.execute(stmt).all()

    # ── Progress (completion counts per set) ─────────────────────────────────
    def named_set_totals(self) -> Sequence[Row]:
        """(name, rwid, total) — card slots in each non-base set (rwid > 0).

        ``rwid`` is included so callers can classify the set into its Unique Sets
        sub-group (creature / item / location) by the same numeric ranges used
        elsewhere in this module.
        """
        stmt = (
            select(
                Set.name.label("name"),
                Set.rwid.label("rwid"),
                Set.role.label("role"),
                func.count(CardInSet.monid).label("total"),
            )
            .join(CardInSet, CardInSet.setid == Set.rwid)
            .where(Set.rwid > BASE_SET_MAX)
            .group_by(Set.name, Set.rwid, Set.role)
        )
        return self.db.execute(stmt).all()

    def named_set_owned(self, did: int) -> Sequence[Row]:
        """(name, owned) — distinct mons of each non-base set the user owns."""
        stmt = (
            select(
                Set.name.label("name"),
                func.count(distinct(CardInSet.monid)).label("owned"),
            )
            .join(CardInSet, CardInSet.setid == Set.rwid)
            .join(Collection, Collection.monid == CardInSet.monid)
            .join(User, Collection.uid == User.rwid)
            .where(Set.rwid > BASE_SET_MAX, User.did == did)
            .group_by(Set.name)
        )
        return self.db.execute(stmt).all()

    def base_set_totals(self) -> Sequence[Row]:
        """(class, total) — base-set (rwid <= 0) card slots per mon class."""
        stmt = (
            select(Mon.class_.label("klass"), func.count(CardInSet.monid).label("total"))
            .join(Mon, CardInSet.monid == Mon.rwid)
            .join(Set, CardInSet.setid == Set.rwid)
            .where(Set.rwid <= BASE_SET_MAX)
            .group_by(Mon.class_)
        )
        return self.db.execute(stmt).all()

    # ── Roles (completed sets a user may display) ────────────────────────────
    def completed_sets(self, did: int) -> Sequence[Row]:
        """(rwid, name, role) for every set the user has completed.

        ``completedsets.setname`` references ``sets.role`` (not the set name).
        """
        stmt = (
            select(
                Set.rwid.label("rwid"),
                Set.name.label("name"),
                Set.role.label("role"),
            )
            .join(CompletedSet, CompletedSet.setname == Set.role)
            .where(CompletedSet.did == did)
            .order_by(Set.name)
            .distinct()
        )
        return self.db.execute(stmt).all()

    def role_string(self, set_rwid: int) -> str | None:
        """The ``sets.role`` text for a set rwid (the displayed role)."""
        return self.db.execute(
            select(Set.role).where(Set.rwid == set_rwid)
        ).scalar_one_or_none()

    def base_set_owned(self, did: int) -> Sequence[Row]:
        """(class, owned) — distinct base-set mons per class the user owns."""
        stmt = (
            select(
                Mon.class_.label("klass"),
                func.count(distinct(CardInSet.monid)).label("owned"),
            )
            .join(Mon, CardInSet.monid == Mon.rwid)
            .join(Set, CardInSet.setid == Set.rwid)
            .join(Collection, Collection.monid == CardInSet.monid)
            .join(User, Collection.uid == User.rwid)
            .where(Set.rwid <= BASE_SET_MAX, User.did == did)
            .group_by(Mon.class_)
        )
        return self.db.execute(stmt).all()
