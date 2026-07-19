"""Tests for the hardened resolve-or-create ``createUser`` (PLAN §6.1).

Exercises the *real* ``sqlhelper.createUser`` against an in-memory SQLite by
monkeypatching ``mydb.db_cursor``. Production uses psycopg2 (``%s`` paramstyle);
a thin cursor wrapper translates ``%s`` -> ``?`` so the helper's SQL — including
``ON CONFLICT (did) DO NOTHING`` (valid in both Postgres and SQLite >= 3.24) —
runs unmodified.
"""

import contextlib
import sqlite3

import pytest

import mydb
import sqlhelper


class _PgLikeCursor:
    """Adapt a sqlite3 cursor to accept psycopg2-style ``%s`` placeholders."""

    def __init__(self, cur):
        self._cur = cur

    def execute(self, sql, params=()):
        return self._cur.execute(sql.replace("%s", "?"), params)

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()


@pytest.fixture
def db(monkeypatch):
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE users (
            rwid  INTEGER PRIMARY KEY AUTOINCREMENT,
            name  TEXT,
            did   INTEGER UNIQUE,
            gp    INTEGER,
            pulls INTEGER,
            yt    INTEGER,
            tt    INTEGER
        )
        """
    )
    conn.commit()

    @contextlib.contextmanager
    def db_cursor():
        cur = conn.cursor()
        try:
            yield _PgLikeCursor(cur)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()

    monkeypatch.setattr(mydb, "db_cursor", db_cursor)
    try:
        yield conn
    finally:
        conn.close()


def _row(conn, did):
    return conn.execute(
        "SELECT rwid, name, gp, pulls FROM users WHERE did = ?", (did,)
    ).fetchone()


def _count(conn):
    return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]


def test_creates_row_and_returns_rwid(db):
    rwid = sqlhelper.createUser("alice", 111)
    assert rwid is not None and rwid > 0
    row = _row(db, 111)
    assert row[0] == rwid
    assert row[1] == "alice"
    assert (row[2], row[3]) == (0, 3)  # gp=0, pulls=3 defaults


def test_idempotent_same_did_returns_same_rwid(db):
    first = sqlhelper.createUser("alice", 111)
    # A repeat call (e.g. two commands racing past the `uid is None` check)
    # must be a no-op that resolves the same row, not a duplicate-key crash.
    second = sqlhelper.createUser("alice-again", 111)
    assert second == first
    assert _count(db) == 1
    assert _row(db, 111)[1] == "alice"  # DO NOTHING did not clobber the name


def test_preexisting_row_resolved_not_duplicated(db):
    # A web-first account already owns this did (linked Discord on the site).
    # The bot's createUser must resolve it, never overwrite or duplicate it.
    db.execute(
        "INSERT INTO users(name, did, gp, pulls, yt, tt) VALUES(?,?,?,?,?,?)",
        ("web-user", 222, 500, 1, 1, 1),
    )
    db.commit()
    rwid = sqlhelper.createUser("bot-name", 222)
    existing = _row(db, 222)
    assert rwid == existing[0]
    assert existing[1] == "web-user"  # name preserved
    assert existing[2] == 500         # gp preserved
    assert _count(db) == 1


def test_distinct_dids_get_distinct_rwids(db):
    a = sqlhelper.createUser("alice", 111)
    b = sqlhelper.createUser("bob", 333)
    assert a != b
    assert _count(db) == 2
