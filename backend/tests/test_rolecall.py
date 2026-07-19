"""Tests for the rolecall / check-in endpoints (API-key auth + checkin insert)."""

from sqlalchemy import text

KEY = "test-rolecall-key"  # set in conftest via ROLECALL_API_KEY


def test_rolecall_get_records_checkin(client, db):
    resp = client.get(
        "/api/rolecall",
        params={"user": "Bob", "userid": "123", "apikey": KEY, "platform": "discord"},
    )
    assert resp.status_code == 200, resp.text
    row = db.execute(text("SELECT name, id, platform FROM checkin")).first()
    assert (row.name, row.id, row.platform) == ("Bob", "123", "discord")


def test_rolecall_invalid_key_rejected(client, db):
    resp = client.get("/api/rolecall", params={"user": "Bob", "userid": "123", "apikey": "nope"})
    assert resp.status_code == 401
    assert db.execute(text("SELECT count(*) FROM checkin")).scalar() == 0


def test_rolecall_post_prefers_body_userid(client, db):
    resp = client.post(
        "/api/rolecall",
        params={"user": "Web", "userid": "fallback", "apikey": KEY, "platform": "web"},
        content="userId=999",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code == 200, resp.text
    row = db.execute(text("SELECT id FROM checkin")).first()
    assert row.id == "999"  # body userId wins over the query-param fallback


def test_rolecall_legacy_stream_path_accepts_query_key(client, db):
    resp = client.get(
        "/api/stream/rolecall",
        params={"user": "Legacy", "userid": "456", "apikey": KEY, "platform": "legacy"},
    )
    assert resp.status_code == 200, resp.text
    row = db.execute(text("SELECT name, id, platform FROM checkin")).first()
    assert (row.name, row.id, row.platform) == ("Legacy", "456", "legacy")


def test_rolecall_accepts_bearer_authorization_header(client, db):
    resp = client.get(
        "/api/rolecall",
        params={"user": "Header", "userid": "789", "platform": "web"},
        headers={"Authorization": f"Bearer {KEY}"},
    )
    assert resp.status_code == 200, resp.text
    row = db.execute(text("SELECT name, id FROM checkin")).first()
    assert (row.name, row.id) == ("Header", "789")
