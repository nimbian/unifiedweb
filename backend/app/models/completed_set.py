"""CompletedSet model — maps ``public.completedsets`` (Discord-bot-owned).

Records that a user (``did``) has completed a set. ``setname`` references
``sets.role`` (not ``sets.name``) — the same join the bot uses. Read-only from
the web app: it drives the list of roles a user may choose from.
"""

from sqlalchemy import BigInteger, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CompletedSet(Base):
    __tablename__ = "completedsets"

    rwid: Mapped[int] = mapped_column(Integer, primary_key=True)
    setname: Mapped[str | None] = mapped_column(Text)  # FKs to sets.role
    did: Mapped[int | None] = mapped_column(BigInteger, index=True)
