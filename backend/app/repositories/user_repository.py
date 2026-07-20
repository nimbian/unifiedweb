"""Data access for users (ports the user queries from ``sqlhelper.py``)."""

from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import Row, func, select, update
from sqlalchemy.orm import Session

from app.models import Collection, LinkCode, User


class UserRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_did(self, did: int) -> User | None:
        """Was ``getUserName(did)`` (returned just the name)."""
        return self.db.execute(select(User).where(User.did == did)).scalar_one_or_none()

    def get_by_rwid(self, rwid: int) -> User | None:
        """Resolve a user by the canonical account id (``users.rwid``)."""
        return self.db.execute(select(User).where(User.rwid == rwid)).scalar_one_or_none()

    # ── linked-login identities ──────────────────────────────────────────────
    def get_by_google_sub(self, sub: str) -> User | None:
        return self.db.execute(
            select(User).where(User.google_sub == sub)
        ).scalar_one_or_none()

    def get_by_twitch_uid(self, uid: str) -> User | None:
        return self.db.execute(
            select(User).where(User.twitch_uid == uid)
        ).scalar_one_or_none()

    def create_from_identity(
        self, provider: str, account_id: str, display: str | None
    ) -> User:
        """Create a brand-new ``users`` row for a first-time sign-in (PLAN §5).

        INSERT only — never rewrites an existing row. ``rwid`` (the serial PK) is
        assigned by the database on flush and becomes the account id. Only the
        signing-in provider is set; the other provider columns stay NULL. ``did``
        is NULL for a Twitch/Google-first account (Satchemon data is empty until
        the user links Discord, which is correct — Satchemon is played via the bot).
        """
        user = User(
            name=display,
            gp=0,
            pulls=0,
            created_at=datetime.now(UTC),
            created_via=provider,
        )
        if provider == "discord":
            user.did = int(account_id)
        elif provider == "google":
            user.google_sub = account_id
            user.google_name = display
        elif provider == "twitch":
            user.twitch_uid = account_id
            user.twitch_login = display
        else:  # pragma: no cover - guarded by the Provider Literal upstream
            raise ValueError(f"Unknown provider: {provider}")
        self.db.add(user)
        self.db.flush()  # assign rwid without ending the request transaction
        return user

    def set_name(self, rwid: int, name: str) -> None:
        self.db.execute(update(User).where(User.rwid == rwid).values(name=name))

    def set_discord_link(self, rwid: int, did: int | None) -> None:
        """Attach (or clear, with ``None``) a Discord id on an existing row.

        Discord is now linkable/unlinkable like the other providers (PLAN §5).
        """
        self.db.execute(update(User).where(User.rwid == rwid).values(did=did))

    def set_google_link(self, rwid: int, sub: str | None, name: str | None) -> None:
        self.db.execute(
            update(User).where(User.rwid == rwid).values(google_sub=sub, google_name=name)
        )

    def set_twitch_link(self, rwid: int, uid: str | None, login: str | None) -> None:
        self.db.execute(
            update(User).where(User.rwid == rwid).values(twitch_uid=uid, twitch_login=login)
        )

    # ── Discord-bot link codes (PLAN §6 /link) ───────────────────────────────
    def get_unconsumed_link_code(self, code: str) -> LinkCode | None:
        """The link-code row for ``code`` if it exists and has not been redeemed.

        The expiry check is done by the caller in Python so it is dialect-safe
        (aware/naive timestamp normalization), not in SQL.
        """
        return self.db.execute(
            select(LinkCode).where(
                LinkCode.code == code, LinkCode.consumed_at.is_(None)
            )
        ).scalar_one_or_none()

    def consume_link_code(self, code: str, when: datetime) -> None:
        """Mark a code redeemed so it can never be reused."""
        self.db.execute(
            update(LinkCode).where(LinkCode.code == code).values(consumed_at=when)
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
