"""Test fixtures.

Uses an in-memory SQLite database (the mapped models are dialect-agnostic) so
tests run with no external Postgres. The ``get_db`` dependency is overridden to
hand out sessions bound to that engine, and a small fixture seeds the seven
web-app tables with representative data.
"""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("ROLECALL_API_KEY", "test-rolecall-key")
# Point the app engine at SQLite so importing it does not require the Postgres
# driver; every request is routed to the in-memory test session via override.
os.environ.setdefault("DATABASE_URL", "sqlite://")

# JWT: exercise the real RS256 path with an ephemeral key pair (no PEM files on
# disk — the inline JWT_PRIVATE_KEY/JWT_PUBLIC_KEY env vars feed config directly).
os.environ.setdefault("JWT_ALGORITHM", "RS256")
# The v1-grace legacy HS256 secret (PLAN §5). test_auth mints a v1-shape token
# signed with this to prove old sessions still verify.
os.environ.setdefault("JWT_LEGACY_SECRET", "legacy-newweb-hs256-secret-for-tests")
if "JWT_PRIVATE_KEY" not in os.environ:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    _rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    os.environ["JWT_PRIVATE_KEY"] = _rsa_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    os.environ["JWT_PUBLIC_KEY"] = (
        _rsa_key.public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )

from app.core.database import get_db  # noqa: E402
from app.dnd.database import DndBase, get_dnd_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base, CardInSet, Collection, Expansion, Mon, Set, User  # noqa: E402

engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


# Minimal stand-ins for the Discord-bot-owned tables the sell flow writes to.
# In production these already exist; here we create just enough columns so the
# trade-cleanup SQL executes (the sell tests run with no pending trades).
_BOT_TABLES_DDL = [
    "CREATE TABLE trades (rwid INTEGER PRIMARY KEY, pid INTEGER, rid INTEGER)",
    "CREATE TABLE rtrades (rwid INTEGER PRIMARY KEY, tid INTEGER, cid INTEGER)",
    "CREATE TABLE ptrades (rwid INTEGER PRIMARY KEY, tid INTEGER, cid INTEGER)",
    "CREATE TABLE pmoney (rwid INTEGER PRIMARY KEY, tid INTEGER, money NUMERIC)",
    "CREATE TABLE checkin (name VARCHAR, id VARCHAR, platform VARCHAR, date TIMESTAMP)",
]


@pytest.fixture(scope="session", autouse=True)
def _schema():
    Base.metadata.create_all(engine)
    # The DnD bot's tables live in a separate database in production; for tests we
    # create them in the same in-memory SQLite engine (no name clash) and route
    # get_dnd_db to the same session.
    DndBase.metadata.create_all(engine)
    with engine.begin() as conn:
        for ddl in _BOT_TABLES_DDL:
            conn.execute(text(ddl))
    yield
    DndBase.metadata.drop_all(engine)
    Base.metadata.drop_all(engine)


@pytest.fixture
def db():
    conn = engine.connect()
    txn = conn.begin()
    session = TestSession(bind=conn)
    try:
        yield session
    finally:
        session.close()
        txn.rollback()
        conn.close()


@pytest.fixture
def seeded(db):
    """Seed one user, three mons (one per class), a set, a card-in-set and a card."""
    user = User(rwid=1, name="Alice", did=111, gp=10)
    db.add(user)

    creature = Mon(rwid=10, cr="1", name="Goblin (#1)", exp="Base", class_="Monsters")
    item = Mon(rwid=11, cr="2", name="Sword (#2)", exp="Base", class_="Item")
    location = Mon(rwid=12, cr="3", name="Cave (#3)", exp="Base", class_="Locations")
    db.add_all([creature, item, location])

    creature_set = Set(rwid=5, name="Starter Creatures", role="starter_creatures")
    db.add(creature_set)
    db.add(CardInSet(rwid=1, setid=5, monid=10))

    db.add(
        Collection(rwid=100, uid=1, monid=10, grade=10, holo=1, value=5, ed="First")
    )
    db.add(Expansion(exp="EXP", expansion="Starter Creatures"))
    db.commit()
    return db


@pytest.fixture
def client(seeded):
    def _override():
        # Reuse the seeded session (same transaction) for the request.
        yield seeded

    app.dependency_overrides[get_db] = _override
    app.dependency_overrides[get_dnd_db] = _override  # same session serves DnD reads
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers():
    """Bearer header for the seeded user (did=111)."""
    from app.core.security import create_access_token

    token = create_access_token("111", extra_claims={"name": "Alice", "rwid": 1})
    return {"Authorization": f"Bearer {token}"}
