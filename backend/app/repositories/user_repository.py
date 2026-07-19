"""Data access for users (ports the user queries from ``sqlhelper.py``)."""

from collections.abc import Sequence

from sqlalchemy import Row, func, select, update
from sqlalchemy.orm import Session

from app.models import Collection, User


class UserRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_did(self, did: int) -> User | None:
        """Was ``getUserName(did)`` (returned just the name)."""
        return self.db.execute(select(User).where(User.did == did)).scalar_one_or_none()

    # ── linked-login identities ──────────────────────────────────────────────
    def get_by_google_sub(self, sub: str) -> User | None:
        return self.db.execute(
            select(User).where(User.google_sub == sub)
        ).scalar_one_or_none()

    def get_by_twitch_uid(self, uid: str) -> User | None:
        return self.db.execute(
            select(User).where(User.twitch_uid == uid)
        ).scalar_one_or_none()

    def set_google_link(self, rwid: int, sub: str | None, name: str | None) -> None:
        self.db.execute(
            update(User).where(User.rwid == rwid).values(google_sub=sub, google_name=name)
        )

    def set_twitch_link(self, rwid: int, uid: str | None, login: str | None) -> None:
        self.db.execute(
            update(User).where(User.rwid == rwid).values(twitch_uid=uid, twitch_login=login)
        )

    def set_role(self, uid: int, roleid: int | None) -> None:
        """Set (or clear, with ``None``) a user's chosen role (``users.roleid``)."""
        self.db.execute(update(User).where(User.rwid == uid).values(roleid=roleid))

    def list_with_stats(self) -> Sequence[Row]:
        """Was ``getAllUsers``.

        SELECT name, did, count(value), sum(value), gp FROM users
            JOIN collections ON users.rwid = collections.uid
            WHERE did > 0 GROUP BY (name, did, gp)
        """
        stmt = (
            select(
                User.name.label("name"),
                User.did.label("did"),
                func.count(Collection.value).label("card_count"),
                func.coalesce(func.sum(Collection.value), 0).label("collection_value"),
                func.coalesce(User.gp, 0).label("gp"),
                func.max(Collection.date).label("last_active"),
            )
            .join(Collection, Collection.uid == User.rwid)
            .where(User.did > 0)
            .group_by(User.name, User.did, User.gp)
            .order_by(User.name.asc())
        )
        return self.db.execute(stmt).all()
