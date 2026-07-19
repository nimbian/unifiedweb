"""Data access for owned cards (ports the collection queries from ``sqlhelper.py``).

The shared shape is the legacy join:

    collections
      INNER JOIN users ON collections.uid = users.rwid
      INNER JOIN mons  ON collections.monid = mons.rwid
      LEFT JOIN (
        SELECT monid, setid, name FROM cardsinsets
          INNER JOIN sets ON sets.rwid = cardsinsets.setid WHERE sets.rwid > 0
      ) AS c ON c.monid = collections.monid

A mon present in multiple (rwid > 0) sets intentionally yields multiple rows,
matching the original behaviour exactly.
"""

from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import Row, Select, case, func, insert, literal_column, or_, select, text, update
from sqlalchemy.orm import Session

from app.models import CardInSet, Collection, Mon, Queue, Set, User

# The system "user" that sold cards are transferred to (was uid = 0 in the bot).
SYSTEM_UID = 0

# A user is "active" if their most recent card is newer than this window (mirrors
# the frontend's ACTIVE_WINDOW_MS).
ACTIVE_WINDOW_DAYS = 30

# Challenge-rating display order (mirrors the frontend ``CR_ORDER``); used to sort
# the custom "1/8, 1/4, 1/2, 1, 2 … 30" sequence rather than lexically.
CR_ORDER = [
    "1/8", "1/4", "1/2", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10",
    "11", "12", "13", "14", "15", "16", "17", "18", "19", "20", "21", "22",
    "23", "24", "25", "26", "27", "28", "29", "30",
]

# Maps a search "sort" key (the column accessor sent by the table) to its ORDER BY
# expression. ``cr`` and ``set_name`` are handled specially in ``_sort_expression``.
_SORT_COLUMNS = {
    "collection_id": Collection.rwid,
    "user": User.name,
    "name": Mon.name,
    "exp": Mon.exp,
    "grade": Collection.grade,
    "value": Collection.value,
    "edition": Collection.ed,
}


def _set_name_subquery():
    """The ``c`` subquery: a mon's set name, restricted to real sets (rwid > 0)."""
    return (
        select(
            CardInSet.monid.label("monid"),
            CardInSet.setid.label("setid"),
            Set.name.label("set_name"),
        )
        .join(Set, Set.rwid == CardInSet.setid)
        .where(Set.rwid > 0)
        .subquery()
    )


class CollectionRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _user_card_columns(self, cset, *, include_meta: bool):
        cols = [
            Collection.rwid.label("collection_id"),
            Mon.cr.label("cr"),
            Mon.name.label("name"),
            Mon.exp.label("exp"),
            Collection.grade.label("grade"),
            Collection.holo.label("holo"),
            Collection.ed.label("ed"),
            Collection.value.label("value"),
            cset.c.set_name.label("set_name"),
        ]
        if include_meta:
            cols += [
                Collection.date.label("date"),
                Mon.rwid.label("mon_id"),
            ]
        return cols

    def _base_user_query(self, did: int, *, include_meta: bool):
        cset = _set_name_subquery()
        return (
            select(*self._user_card_columns(cset, include_meta=include_meta))
            .select_from(Collection)
            .join(User, Collection.uid == User.rwid)
            .join(Mon, Collection.monid == Mon.rwid)
            .join(cset, cset.c.monid == Collection.monid, isouter=True)
            .where(User.did == did)
        )

    def get_full_collection(self, did: int) -> Sequence[Row]:
        """Was ``getFullCollection`` (includes date + mon_id)."""
        return self.db.execute(self._base_user_query(did, include_meta=True)).all()

    def get_by_class(self, did: int, klass: str) -> Sequence[Row]:
        """Was ``getAllMonsters`` / ``getAllItems`` / ``getAllLocations``.

        ``klass`` is one of the legacy literals: 'Monsters', 'Item', 'Locations'.
        """
        stmt = self._base_user_query(did, include_meta=False).where(Mon.class_ == klass)
        return self.db.execute(stmt).all()

    def get_cards_for_cr(self, did: int, cr_code: str) -> Sequence[Row]:
        """Was ``getCardsForUser`` — the CR drill-down: ``mons.name LIKE '%(#<code>)%'``."""
        stmt = self._base_user_query(did, include_meta=True).where(
            Mon.name.like(f"%(#{cr_code})%")
        )
        return self.db.execute(stmt).all()

    # ── Progress stats ───────────────────────────────────────────────────────
    def progress_stats(self, did: int) -> tuple[Decimal, Decimal, int, int]:
        """Headline collection stats for one user, returned as
        ``(total_value, top_value, total_cards, unique_cards)``:

          * ``total_value``  — sum of every owned card's value.
          * ``top_value``    — sum of *one of each* card, taking the most valuable
                               copy per mon (the value of a deduped collection).
          * ``total_cards``  — number of owned card instances.
          * ``unique_cards`` — number of distinct mons owned.
        """
        total_value, total_cards, unique_cards = self.db.execute(
            select(
                func.coalesce(func.sum(Collection.value), 0),
                func.count(Collection.rwid),
                func.count(func.distinct(Collection.monid)),
            )
            .select_from(Collection)
            .join(User, Collection.uid == User.rwid)
            .where(User.did == did)
        ).one()

        # Most valuable copy per mon, then summed.
        per_mon_max = (
            select(func.max(Collection.value).label("maxval"))
            .select_from(Collection)
            .join(User, Collection.uid == User.rwid)
            .where(User.did == did)
            .group_by(Collection.monid)
            .subquery()
        )
        top_value = self.db.execute(
            select(func.coalesce(func.sum(per_mon_max.c.maxval), 0))
        ).scalar_one()

        return Decimal(total_value), Decimal(top_value), int(total_cards), int(unique_cards)

    # ── Selling ──────────────────────────────────────────────────────────────
    def resolve_uid(self, did: int) -> int | None:
        return self.db.execute(select(User.rwid).where(User.did == did)).scalar_one_or_none()

    def get_owned_for_sale(self, did: int, ids: Sequence[int]) -> Sequence[Row]:
        """Return (collection_id, name, value) for the cards in ``ids`` that the
        user actually owns — the server-side equivalent of the bot's ``yourCard``
        check. Cards not owned by ``did`` are simply absent from the result.
        """
        stmt = (
            select(
                Collection.rwid.label("collection_id"),
                Mon.name.label("name"),
                Collection.value.label("value"),
            )
            .join(User, Collection.uid == User.rwid)
            .join(Mon, Collection.monid == Mon.rwid, isouter=True)
            .where(User.did == did, Collection.rwid.in_(ids))
        )
        return self.db.execute(stmt).all()

    # ── Buying (from the shop / system user uid 0) ───────────────────────────
    def get_gp(self, uid: int) -> Decimal | None:
        return self.db.execute(select(User.gp).where(User.rwid == uid)).scalar_one_or_none()

    def get_shop_cards_for_buy(self, ids: Sequence[int]) -> Sequence[Row]:
        """Return (collection_id, name, value) for the cards in ``ids`` that are
        currently in the shop (owned by the system user, uid 0) — the buy-side
        equivalent of the bot's ``yourCard(c, 0)`` check. Non-shop cards are
        simply absent from the result.
        """
        stmt = (
            select(
                Collection.rwid.label("collection_id"),
                Mon.name.label("name"),
                Collection.value.label("value"),
            )
            .join(Mon, Collection.monid == Mon.rwid, isouter=True)
            .where(Collection.uid == SYSTEM_UID, Collection.rwid.in_(ids))
        )
        return self.db.execute(stmt).all()

    def execute_buy(
        self, buyer_uid: int, ids: Sequence[int], total_cost: Decimal
    ) -> Decimal:
        """Atomically transfer the shop cards to the buyer and debit their GP.
        Returns the new GP. The UPDATE is re-scoped to ``uid == SYSTEM_UID`` as
        defense in depth, so only cards still in the shop can be transferred.
        """
        self.db.execute(
            update(Collection)
            .where(Collection.rwid.in_(ids), Collection.uid == SYSTEM_UID)
            .values(uid=buyer_uid)
        )
        self.db.execute(
            update(User).where(User.rwid == buyer_uid).values(gp=User.gp - total_cost)
        )
        return self.db.execute(select(User.gp).where(User.rwid == buyer_uid)).scalar_one()

    def execute_sale(
        self,
        uid: int,
        did: int,
        payouts: Sequence[tuple[int, Decimal]],
        total_payout: Decimal,
    ) -> Decimal:
        """Atomically: remove pending trades on the sold cards, transfer the cards
        to the system user, enqueue each sold card for later processing, and
        credit the seller's GP. Returns the new GP.

        ``payouts`` is a sequence of ``(collection_id, payout)`` for the cards
        being sold. Runs inside the request's transaction (``get_db`` commits on
        success and rolls back on any error), so a partial sale — or a queue row
        without the matching transfer/credit — can never be persisted. Ownership
        is enforced by the caller (only owned cards reach here) AND by re-scoping
        the UPDATE to ``uid`` as defense in depth.
        """
        owned_ids = [cid for cid, _ in payouts]
        for cid in owned_ids:
            self._remove_trades_with_card(cid)

        self.db.execute(
            update(Collection)
            .where(Collection.rwid.in_(owned_ids), Collection.uid == uid)
            .values(uid=SYSTEM_UID)
        )

        # Enqueue each sold card (did, card number = collection rwid, payout) for
        # the later out-of-band processor.
        if payouts:
            self.db.execute(
                insert(Queue),
                [
                    {"did": did, "collection_id": cid, "value": payout}
                    for cid, payout in payouts
                ],
            )

        self.db.execute(
            update(User).where(User.rwid == uid).values(gp=User.gp + total_payout)
        )
        return self.db.execute(select(User.gp).where(User.rwid == uid)).scalar_one()

    def _remove_trades_with_card(self, cid: int) -> None:
        """Port of the bot's ``removeTradesWithCard`` + ``deleteTrade``.

        Deletes any pending trade that offers or requests this card, refunding the
        proposer's escrowed money first. The ``trades`` row delete cascades to
        ``ptrades``/``rtrades``/``pmoney`` via existing ON DELETE CASCADE FKs.
        These are Discord-bot-owned tables; we WRITE to them operationally but do
        not let Alembic manage their schema.
        """
        trade_ids: set[int] = set()
        for join_table in ("rtrades", "ptrades"):
            rows = self.db.execute(
                text(
                    f"SELECT trades.rwid FROM trades "  # noqa: S608 — table name is a literal
                    f"JOIN {join_table} ON trades.rwid = {join_table}.tid WHERE cid = :cid"
                ),
                {"cid": cid},
            ).all()
            trade_ids.update(r[0] for r in rows)

        for tid in trade_ids:
            self._delete_trade(tid)

    def _delete_trade(self, trade_id: int) -> None:
        money = self.db.execute(
            text("SELECT money FROM pmoney WHERE tid = :tid"), {"tid": trade_id}
        ).scalar_one_or_none()
        if money is not None:
            self.db.execute(
                text(
                    "UPDATE users SET gp = gp + :money "
                    "WHERE rwid = (SELECT pid FROM trades WHERE rwid = :tid)"
                ),
                {"money": money, "tid": trade_id},
            )
        self.db.execute(text("DELETE FROM trades WHERE rwid = :tid"), {"tid": trade_id})

    def _search_query(
        self,
        q: str | None,
        holo: bool | None = None,
        exp: str | None = None,
        grade: int | None = None,
        cr: str | None = None,
        name: str | None = None,
        active: bool | None = None,
    ) -> Select:
        """Was ``getAllCollections`` (global search). Adds the user name column.

        ``q`` applies a case-insensitive substring filter across the user, card,
        expansion and set columns (the fields the legacy client-side DataTable
        filter searched). ``name`` is the same kind of substring filter but scoped
        to the card name (the Card column filter). ``holo`` optionally restricts to
        holo (truthy) or non-holo (0/null) cards, matching the ``bool(holo)``
        presentation. ``exp``, ``grade`` and ``cr`` restrict to an exact expansion /
        grade / challenge rating (the "selections" offered by the column filters).
        The query is left unordered/unpaged here; callers add ordering +
        limit/offset (or wrap it for a count).
        """
        cset = _set_name_subquery()
        # Each owner's most recent card date — for the Active pill. Joined 1:1 on
        # uid, so it never multiplies rows (and leaves the count unchanged).
        last_active_sq = (
            select(
                Collection.uid.label("uid"),
                func.max(Collection.date).label("last_active"),
            )
            .group_by(Collection.uid)
            .subquery()
        )
        stmt = (
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
                cset.c.set_name.label("set_name"),
                last_active_sq.c.last_active.label("last_active"),
            )
            .select_from(Collection)
            .join(User, Collection.uid == User.rwid)
            .join(Mon, Collection.monid == Mon.rwid)
            .join(cset, cset.c.monid == Collection.monid, isouter=True)
            .join(last_active_sq, last_active_sq.c.uid == User.rwid, isouter=True)
            .where(User.did > 0)
        )
        if q:
            like = f"%{q}%"
            stmt = stmt.where(
                or_(
                    User.name.ilike(like),
                    Mon.name.ilike(like),
                    Mon.exp.ilike(like),
                    cset.c.set_name.ilike(like),
                )
            )
        if holo is not None:
            # holo is an integer (0/1, occasionally NULL); bool(holo) is the
            # displayed value, so treat NULL/0 as "No" and anything else as "Yes".
            is_holo = func.coalesce(Collection.holo, 0) != 0
            stmt = stmt.where(is_holo if holo else ~is_holo)
        if exp is not None:
            stmt = stmt.where(Mon.exp == exp)
        if grade is not None:
            stmt = stmt.where(Collection.grade == grade)
        if cr is not None:
            stmt = stmt.where(Mon.cr == cr)
        if name:
            stmt = stmt.where(Mon.name.ilike(f"%{name}%"))
        if active is not None:
            cutoff = datetime.now(timezone.utc) - timedelta(days=ACTIVE_WINDOW_DAYS)
            la = last_active_sq.c.last_active
            # Active = a card newer than the cutoff. Inactive = no recent card,
            # including owners whose cards have no date at all (NULL).
            stmt = stmt.where(la >= cutoff) if active else stmt.where(
                or_(la < cutoff, la.is_(None))
            )
        return stmt

    def count_all_collections(
        self,
        q: str | None = None,
        holo: bool | None = None,
        exp: str | None = None,
        grade: int | None = None,
        cr: str | None = None,
        name: str | None = None,
        active: bool | None = None,
    ) -> int:
        """Total rows the (filtered) global search would yield — for paging."""
        subq = self._search_query(q, holo, exp, grade, cr, name, active).subquery()
        return self.db.execute(select(func.count()).select_from(subq)).scalar_one()

    @staticmethod
    def _sort_expression(sort: str | None, direction: str):
        """Build an ORDER BY expression for a search ``sort`` key, or None if the
        key isn't sortable. ``cr`` uses the custom challenge-rating order.
        """
        if sort == "cr":
            col = case(
                {v: i for i, v in enumerate(CR_ORDER)},
                value=Mon.cr,
                else_=len(CR_ORDER),
            )
        elif sort == "set_name":
            col = literal_column("set_name")  # the labeled output column
        else:
            col = _SORT_COLUMNS.get(sort or "")
        if col is None:
            return None
        return col.desc() if direction == "desc" else col.asc()

    def get_all_collections(
        self,
        q: str | None = None,
        holo: bool | None = None,
        exp: str | None = None,
        grade: int | None = None,
        cr: str | None = None,
        name: str | None = None,
        active: bool | None = None,
        sort: str | None = None,
        direction: str = "asc",
        *,
        limit: int,
        offset: int,
    ) -> Sequence[Row]:
        """A page of the global search. Ordered by the requested column (default
        mon name), always with ``collection_id`` as a tiebreaker so paging stays
        stable across requests.
        """
        order = self._sort_expression(sort, direction)
        order_by = [order, Collection.rwid] if order is not None else [Mon.name, Collection.rwid]
        stmt = (
            self._search_query(q, holo, exp, grade, cr, name, active)
            .order_by(*order_by)
            .limit(limit)
            .offset(offset)
        )
        return self.db.execute(stmt).all()

    def search_facets(self) -> tuple[Sequence[str], Sequence[int], Sequence[str]]:
        """Distinct expansions, grades and challenge ratings across all (real-user)
        collections, for populating the search column-filter dropdowns. Returns
        (expansions, grades, crs). CR ordering is left to the client (custom sort).
        """
        exp_rows = self.db.execute(
            select(Mon.exp)
            .select_from(Collection)
            .join(User, Collection.uid == User.rwid)
            .join(Mon, Collection.monid == Mon.rwid)
            .where(User.did > 0, Mon.exp.is_not(None))
            .distinct()
            .order_by(Mon.exp)
        ).scalars().all()
        grade_rows = self.db.execute(
            select(Collection.grade)
            .select_from(Collection)
            .join(User, Collection.uid == User.rwid)
            .where(User.did > 0, Collection.grade.is_not(None))
            .distinct()
            .order_by(Collection.grade)
        ).scalars().all()
        cr_rows = self.db.execute(
            select(Mon.cr)
            .select_from(Collection)
            .join(User, Collection.uid == User.rwid)
            .join(Mon, Collection.monid == Mon.rwid)
            .where(User.did > 0, Mon.cr.is_not(None))
            .distinct()
            .order_by(Mon.cr)
        ).scalars().all()
        return exp_rows, grade_rows, cr_rows
