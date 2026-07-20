"""Tests for ``sqlhelper.createLinkCode`` — the bot half of PLAN §6's ``/link``.

Exercises the *real* helper against an in-memory SQLite by monkeypatching
``mydb.db_cursor`` (same approach as ``test_createuser``). The cursor wrapper
translates psycopg2 ``%s`` placeholders to sqlite ``?``; a datetime adapter is
registered so the aware timestamps the helper inserts store cleanly (and without
the deprecated default-adapter path).
"""

import contextlib
import sqlite3
from datetime import datetime

import pytest

import mydb
import sqlhelper

sqlite3.register_adapter(datetime, lambda d: d.isoformat())


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
        CREATE TABLE link_codes (
            code        TEXT PRIMARY KEY,
            did         INTEGER,
            created_at  TIMESTAMP,
            expires_at  TIMESTAMP,
            consumed_at TIMESTAMP
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


def _rows(conn, did):
    return conn.execute(
        "SELECT code, consumed_at FROM link_codes WHERE did = ?", (did,)
    ).fetchall()


def test_creates_a_live_code_row(db):
    code, expires = sqlhelper.createLinkCode(111)
    assert len(code) == sqlhelper.LINK_CODE_LEN
    assert set(code) <= set(sqlhelper.LINK_CODE_ALPHABET)  # unambiguous alphabet
    assert expires > datetime.now(expires.tzinfo)

    rows = _rows(db, 111)
    assert len(rows) == 1
    assert rows[0][0] == code
    assert rows[0][1] is None  # unconsumed


def test_regenerating_replaces_prior_unconsumed_code(db):
    first, _ = sqlhelper.createLinkCode(111)
    second, _ = sqlhelper.createLinkCode(111)
    assert second != first

    rows = _rows(db, 111)
    assert len(rows) == 1  # the stale code was cleared
    assert rows[0][0] == second


def test_regenerating_keeps_already_consumed_codes(db):
    # A redeemed code is history — /link must not delete it, only live ones.
    db.execute(
        "INSERT INTO link_codes(code, did, created_at, expires_at, consumed_at)"
        " VALUES(?,?,?,?,?)",
        ("USEDCODE", 111, "2026-01-01T00:00:00+00:00", "2026-01-01T00:15:00+00:00",
         "2026-01-01T00:05:00+00:00"),
    )
    db.commit()

    code, _ = sqlhelper.createLinkCode(111)
    codes = {r[0] for r in _rows(db, 111)}
    assert codes == {"USEDCODE", code}  # consumed row preserved alongside the new one


def test_distinct_dids_are_independent(db):
    a, _ = sqlhelper.createLinkCode(111)
    b, _ = sqlhelper.createLinkCode(222)
    assert a != b
    assert len(_rows(db, 111)) == 1
    assert len(_rows(db, 222)) == 1
