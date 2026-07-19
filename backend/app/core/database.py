"""Database engine and session management (SQLAlchemy 2.0).

Replaces ``mydb.py`` (raw ``psycopg2.pool.SimpleConnectionPool`` +
``db_cursor`` contextmanager) with a SQLAlchemy engine, a session factory,
and a FastAPI dependency (``get_db``) for per-request sessions.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

# SQLite (used by the test suite) uses a singleton/static pool that rejects the
# QueuePool sizing kwargs, so only pass them for real database backends.
_engine_kwargs: dict = {"echo": settings.db_echo, "pool_pre_ping": True, "future": True}
if not settings.database_url.startswith("sqlite"):
    _engine_kwargs.update(pool_size=5, max_overflow=5)

engine = create_engine(settings.database_url, **_engine_kwargs)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    class_=Session,
)


def get_db() -> Generator[Session, None, None]:
    """Yield a request-scoped session, committing on success and rolling back on error.

    Mirrors the transactional semantics of the old ``db_cursor`` contextmanager.
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
