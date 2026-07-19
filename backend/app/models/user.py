"""User model — maps ``public.users``.

Legacy SQL of interest:
    SELECT name FROM users WHERE did = %s
    SELECT name, did, count(value), sum(value), gp FROM users
        JOIN collections ... WHERE did > 0 GROUP BY (name, did, gp)

``did`` is the Discord user id (UNIQUE constraint ``undid``) and is the value
the old Flask-Login session stored. ``rwid`` is the surrogate PK used by FKs.
The ``pulls/yt/tt`` columns are owned by the Discord bot; we map them so the
ORM matches the table exactly but the web app never writes them.
"""

from sqlalchemy import BigInteger, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class User(Base):
    __tablename__ = "users"

    rwid: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str | None] = mapped_column(Text)
    did: Mapped[int | None] = mapped_column(BigInteger, unique=True, index=True)
    gp: Mapped[float | None] = mapped_column(Numeric(15, 2))
    # The user's chosen "role" — the rwid of a set they have completed (see
    # ``completedsets``). NULL means no role. Written by the web app (the column
    # was added for the website); resolves to ``sets.role`` for display.
    roleid: Mapped[int | None] = mapped_column(Integer)

    # Linked-login identities (web-app-owned, like ``roleid``). Every account is
    # anchored on Discord (``did``); these let a user sign in with Google (the
    # "YouTube" login) or Twitch instead. The ``*_id`` columns hold the provider's
    # stable account id and are unique so a provider account links to one user;
    # the companion columns hold a display handle for the UI. Distinct from the
    # bot-owned ``ytusername``/``ttusername`` giveaway fields above.
    google_sub: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    google_name: Mapped[str | None] = mapped_column(String(255))
    twitch_uid: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    twitch_login: Mapped[str | None] = mapped_column(String(255))

    # Discord-bot-owned columns (mapped for fidelity; read-only from the web app).
    pulls: Mapped[int | None] = mapped_column(Integer)
    yt: Mapped[int | None] = mapped_column(Integer)
    ytentries: Mapped[int | None] = mapped_column(Integer)
    ytusername: Mapped[str | None] = mapped_column(String(100))
    tt: Mapped[int | None] = mapped_column(Integer)
    ttentries: Mapped[int | None] = mapped_column(Integer)
    ttusername: Mapped[str | None] = mapped_column(String(100))

    collections: Mapped[list["Collection"]] = relationship(  # noqa: F821
        back_populates="user",
        lazy="noload",
    )
