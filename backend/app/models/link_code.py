"""LinkCode model — maps ``public.link_codes``.

A one-time short code that lets a bot-first user link their Discord to their
MooreDnD website account **without an OAuth roundtrip** (PLAN §6 "``/link``"). The
Discord bot generates the code (``/link``) and stores the row; the portal
redeems it on ``/account`` (``POST /auth/link/redeem``), attaching the code's
``did`` to the signed-in ``rwid`` and stamping ``consumed_at``.

Like ``queue`` this is a **web-app-owned** table (created by Alembic migration
``0005``, not a pre-existing bot table) — but both the bot (insert) and the
portal (select/consume) touch it, since it is the hand-off channel between them.
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class LinkCode(Base):
    __tablename__ = "link_codes"

    # The short human-typed code (uppercase, unambiguous alphabet) is the PK.
    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    # Discord id this code will link (``users.did``); written by the bot.
    did: Mapped[int] = mapped_column(BigInteger, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # NULL until redeemed; set once so a code can never be reused.
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
