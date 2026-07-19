"""Second database connection — the DnD-adventure bot's Postgres database.

The DnD bot keeps its data in a *separate* database from Satchemon (same server
by default). This module builds an isolated engine/session for it, with its own
declarative base so its tables never mix with the Satchemon metadata (Alembic,
test ``create_all``, etc.). Everything here is read-only: the website only
displays the bot's stats and never mutates them.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class DndBase(DeclarativeBase):
    """Declarative base for the DnD bot's tables (separate from Satchemon's)."""


def dnd_database_url() -> str:
    """Resolve the DnD DB URL: the explicit setting, or the Satchemon URL with
    its database name swapped to ``dndbot`` (same server, reused credentials)."""
    if settings.dndbot_database_url:
        return settings.dndbot_database_url
    return str(make_url(settings.database_url).set(database="dndbot"))


_url = dnd_database_url()
_engine_kwargs: dict = {"pool_pre_ping": True, "future": True}
if not _url.startswith("sqlite"):
    _engine_kwargs.update(pool_size=3, max_overflow=3)

# create_engine is lazy (no connection until first use), so importing this is
# safe even if the DnD database is unreachable; failures surface per-request.
dnd_engine = create_engine(_url, **_engine_kwargs)

DndSessionLocal = sessionmaker(
    bind=dnd_engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    class_=Session,
)


def get_dnd_db() -> Generator[Session, None, None]:
    """Yield a read-only request-scoped session against the DnD database."""
    db = DndSessionLocal()
    try:
        yield db
    finally:
        db.close()
