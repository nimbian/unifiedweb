"""Tests for the buy-from-shop feature (shop-ownership + cost + GP debit)."""


def _add_shop_card(db, *, rwid, monid, value, name):
    """Add a card to the shop (system user uid 0)."""
    from app.models import Collection, Mon

    db.add(Mon(rwid=monid, cr="5", name=name, exp="Base", class_="Monsters"))
    db.add(Collection(rwid=rwid, uid=0, monid=monid, grade=8, holo=0, value=value))


def test_buy_requires_auth(client):
    assert client.post("/api/me/buy", json={"collection_ids": [400]}).status_code == 401


def test_buy_straight_debits_gp_and_transfers(client, auth_headers, db):
    from app.models import Collection

    # Alice (did=111, gp=10). Shop has card 400 worth 4.
    _add_shop_card(db, rwid=400, monid=70, value=4, name="Relic (#5)")
    db.commit()

    body = client.post("/api/me/buy", json={"collection_ids": [400]}, headers=auth_headers).json()
    assert body["rate"] == 1.5
    assert body["roll"] is None
    assert float(body["total_cost"]) == 6.0  # round(4 * 1.5, 3)
    assert float(body["new_gp"]) == 4.0

    # The card now belongs to Alice (rwid 1), not the shop.
    assert db.get(Collection, 400).uid == 1


def test_buy_rejects_non_shop_card(client, auth_headers, db):
    # Collection 100 is Alice's own card (uid 1), not a shop card.
    resp = client.post("/api/me/buy", json={"collection_ids": [100]}, headers=auth_headers)
    assert resp.status_code == 403


def test_buy_rejects_when_too_expensive(client, auth_headers, db):
    _add_shop_card(db, rwid=401, monid=71, value=100, name="Crown (#5)")  # cost 150 > gp 10
    db.commit()
    resp = client.post("/api/me/buy", json={"collection_ids": [401]}, headers=auth_headers)
    assert resp.status_code == 400


def test_haggle_buy_uses_d20_rate(client, auth_headers, db, monkeypatch):
    # A natural 20 -> 130% (cheapest).
    monkeypatch.setattr("app.services.collection_service.random.randint", lambda a, b: 20)
    _add_shop_card(db, rwid=402, monid=72, value=4, name="Charm (#5)")
    db.commit()

    body = client.post(
        "/api/me/buy", json={"collection_ids": [402], "haggle": True}, headers=auth_headers
    ).json()
    assert body["roll"] == 20
    assert body["rate"] == 1.3
    assert float(body["total_cost"]) == 5.2  # round(4 * 1.3, 3)
    assert float(body["new_gp"]) == 4.8


def test_haggle_buy_requires_worst_case_affordability(client, auth_headers, db, monkeypatch):
    # Value 6 -> worst case 6 * 1.7 = 10.2 > gp 10, so the haggle is refused even
    # though a good roll might have been affordable.
    monkeypatch.setattr("app.services.collection_service.random.randint", lambda a, b: 20)
    _add_shop_card(db, rwid=403, monid=73, value=6, name="Idol (#5)")
    db.commit()
    resp = client.post(
        "/api/me/buy", json={"collection_ids": [403], "haggle": True}, headers=auth_headers
    )
    assert resp.status_code == 400