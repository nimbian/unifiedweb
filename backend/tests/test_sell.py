"""Tests for the sell-cards feature (ownership enforcement + payout + GP credit)."""


def test_sell_requires_auth(client):
    resp = client.post("/api/me/sell", json={"collection_ids": [100]})
    assert resp.status_code == 401


def test_sell_own_card_credits_gp_and_transfers(client, auth_headers):
    # Alice (did=111, gp=10) owns collection 100 worth 5.0.
    resp = client.post("/api/me/sell", json={"collection_ids": [100]}, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # Straight sale: payout = round(5.0 * 0.7, 3) = 3.5, no roll.
    assert float(body["total_payout"]) == 3.5
    assert float(body["new_gp"]) == 13.5
    assert body["rate"] == 0.7
    assert body["roll"] is None
    assert body["sold"][0]["collection_id"] == 100

    # The card is no longer in Alice's collection (transferred to system uid 0).
    cards = client.get("/api/users/111/cards").json()
    assert cards == []


def test_haggle_sell_uses_d20_rate(client, auth_headers, monkeypatch):
    # Force a "great" roll (20 -> 90%). Alice's card is worth 5.0.
    monkeypatch.setattr("app.services.collection_service.random.randint", lambda a, b: 20)
    resp = client.post(
        "/api/me/sell",
        json={"collection_ids": [100], "haggle": True},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["roll"] == 20
    assert body["rate"] == 0.9
    assert float(body["total_payout"]) == 4.5  # round(5.0 * 0.9, 3)
    assert float(body["new_gp"]) == 14.5


def test_haggle_sell_terrible_roll(client, auth_headers, monkeypatch):
    # A natural 1 -> 50%.
    monkeypatch.setattr("app.services.collection_service.random.randint", lambda a, b: 1)
    body = client.post(
        "/api/me/sell",
        json={"collection_ids": [100], "haggle": True},
        headers=auth_headers,
    ).json()
    assert body["roll"] == 1
    assert body["rate"] == 0.5
    assert float(body["total_payout"]) == 2.5  # round(5.0 * 0.5, 3)


def test_sell_enqueues_sold_cards(client, auth_headers, db):
    from sqlalchemy import select

    from app.models import Queue

    resp = client.post("/api/me/sell", json={"collection_ids": [100]}, headers=auth_headers)
    assert resp.status_code == 200, resp.text

    rows = db.execute(select(Queue)).scalars().all()
    assert len(rows) == 1
    q = rows[0]
    assert q.did == 111            # seller's Discord id (not rwid)
    assert q.collection_id == 100  # the sold card's collections.rwid
    assert float(q.value) == 3.5   # payout = round(5.0 * 0.7, 3)


def test_failed_sale_enqueues_nothing(client, auth_headers, db):
    # A rejected sale (card not owned -> 403) is refused before any writes, so
    # nothing is enqueued.
    from sqlalchemy import select

    from app.models import Queue

    resp = client.post("/api/me/sell", json={"collection_ids": [999]}, headers=auth_headers)
    assert resp.status_code == 403
    assert db.execute(select(Queue)).scalars().all() == []


def test_cannot_sell_someone_elses_card(client, auth_headers):
    # collection 999 does not belong to Alice -> 403, nothing changes.
    resp = client.post("/api/me/sell", json={"collection_ids": [999]}, headers=auth_headers)
    assert resp.status_code == 403

    # Alice still owns her card.
    assert len(client.get("/api/users/111/cards").json()) == 1


def test_sell_empty_list_rejected(client, auth_headers):
    resp = client.post("/api/me/sell", json={"collection_ids": []}, headers=auth_headers)
    assert resp.status_code == 422  # min_length=1
