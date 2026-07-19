"""Integration tests for the public API endpoints (no auth required)."""


def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_list_users(client):
    resp = client.get("/api/users")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["name"] == "Alice"
    # did must serialize as a string so large Discord ids don't lose precision in JS.
    assert rows[0]["did"] == "111"
    assert isinstance(rows[0]["did"], str)
    assert rows[0]["card_count"] == 1
    # Alice owns one card worth 5.
    assert float(rows[0]["collection_value"]) == 5.0


def test_last_active_surfaced(client, db):
    # The owner's most recent card date appears on both the users list and search.
    from datetime import datetime, timezone

    from app.models import Collection, Mon

    db.add(Mon(rwid=70, cr="1", name="Fresh (#1)", exp="Base", class_="Monsters"))
    db.add(
        Collection(
            rwid=300, uid=1, monid=70, grade=10, holo=1, value=1,
            date=datetime.now(timezone.utc), ed="First",
        )
    )
    db.commit()

    assert client.get("/api/users").json()[0]["last_active"] is not None
    item = client.get("/api/search", params={"name": "Fresh"}).json()["items"][0]
    assert item["last_active"] is not None


def test_user_profile(client):
    assert client.get("/api/users/111").json()["name"] == "Alice"
    assert client.get("/api/users/999").status_code == 404


def test_full_collection_presentation(client):
    rows = client.get("/api/users/111/cards", params={"category": "full"}).json()
    assert len(rows) == 1
    card = rows[0]
    assert card["name"] == "Goblin (#1)"
    assert card["holo"] is True          # holo int 1 -> bool
    assert card["edition"] == "First"
    assert card["set_name"] == "Starter Creatures"


def test_category_filter_items(client):
    # Alice owns no items, so the items category is empty.
    rows = client.get("/api/users/111/cards", params={"category": "items"}).json()
    assert rows == []


def test_cr_drilldown(client):
    rows = client.get("/api/users/111/cards/cr/1").json()
    assert len(rows) == 1
    assert rows[0]["cr"] == "1"


def test_search(client):
    body = client.get("/api/search").json()
    assert body["total"] == 1
    assert body["limit"] == 50
    assert body["offset"] == 0
    assert len(body["items"]) == 1
    assert body["items"][0]["user"] == "Alice"


def test_search_filter(client):
    # Matches the card name "Goblin (#1)" case-insensitively.
    hit = client.get("/api/search", params={"q": "goblin"}).json()
    assert hit["total"] == 1
    assert hit["items"][0]["name"] == "Goblin (#1)"

    # No match -> empty page, zero total.
    miss = client.get("/api/search", params={"q": "nonesuch"}).json()
    assert miss["total"] == 0
    assert miss["items"] == []


def test_search_holo_filter(client):
    # Alice's one card is holo, so holo=true returns it and holo=false is empty.
    yes = client.get("/api/search", params={"holo": "true"}).json()
    assert yes["total"] == 1
    assert yes["items"][0]["holo"] is True

    no = client.get("/api/search", params={"holo": "false"}).json()
    assert no["total"] == 0
    assert no["items"] == []


def test_search_name_filter(client):
    # Card name "Goblin (#1)" — the per-column Card filter is a substring match.
    assert client.get("/api/search", params={"name": "gob"}).json()["total"] == 1
    assert client.get("/api/search", params={"name": "dragon"}).json()["total"] == 0


def test_search_active_filter(client, db):
    # Alice's seeded card has no date -> she is inactive. Add a fresh card so a
    # second owner is active, then filter by activity.
    from datetime import datetime, timezone

    from app.models import Collection, Mon, User

    db.add(User(rwid=2, name="Bob", did=222, gp=0))
    db.add(Mon(rwid=70, cr="1", name="Fresh (#1)", exp="Base", class_="Monsters"))
    db.add(
        Collection(
            rwid=300, uid=2, monid=70, grade=10, holo=1, value=1,
            date=datetime.now(timezone.utc), ed="First",
        )
    )
    db.commit()

    active = client.get("/api/search", params={"active": "true"}).json()
    assert {i["user"] for i in active["items"]} == {"Bob"}

    inactive = client.get("/api/search", params={"active": "false"}).json()
    assert {i["user"] for i in inactive["items"]} == {"Alice"}


def test_search_exp_grade_cr_filters(client):
    # Alice's card is exp "Base", grade 10, cr "1".
    assert client.get("/api/search", params={"exp": "Base"}).json()["total"] == 1
    assert client.get("/api/search", params={"exp": "Nope"}).json()["total"] == 0
    assert client.get("/api/search", params={"grade": 10}).json()["total"] == 1
    assert client.get("/api/search", params={"grade": 5}).json()["total"] == 0
    assert client.get("/api/search", params={"cr": "1"}).json()["total"] == 1
    assert client.get("/api/search", params={"cr": "99"}).json()["total"] == 0


def test_search_sort(client, db):
    # Seed a second, higher-value card so ordering is observable.
    from app.models import Collection, Mon

    db.add(Mon(rwid=60, cr="2", name="Zebra (#2)", exp="Base", class_="Monsters"))
    db.add(Collection(rwid=300, uid=1, monid=60, grade=8, holo=0, value=99, ed="First"))
    db.commit()

    desc = client.get("/api/search", params={"sort": "value", "direction": "desc"}).json()
    assert [float(i["value"]) for i in desc["items"]] == [99.0, 5.0]

    asc = client.get("/api/search", params={"sort": "name", "direction": "asc"}).json()
    assert [i["name"] for i in asc["items"]] == ["Goblin (#1)", "Zebra (#2)"]


def test_search_facets(client):
    facets = client.get("/api/search/facets").json()
    assert facets["expansions"] == ["Base"]
    assert facets["grades"] == [10]
    assert facets["crs"] == ["1"]


def test_search_paging(client):
    # offset past the only row yields an empty page but the true total.
    body = client.get("/api/search", params={"limit": 1, "offset": 1}).json()
    assert body["total"] == 1
    assert body["items"] == []


def test_sidebar(client):
    sidebar = client.get("/api/sets/sidebar").json()
    names = [s["name"] for s in sidebar["creature_sets"]]
    # "Starter Creatures" is also an expansion, so it is excluded from creature_sets.
    assert "Starter Creatures" not in names
    assert sidebar["expansions"][0]["name"] == "Starter Creatures"


def test_base_sets_broken_out_by_class(client, db):
    # Seed a base set (rwid <= 0) with one creature and one item card.
    from app.models import CardInSet, Mon, Set

    db.add(Set(rwid=0, name="Base Set", role="base"))
    db.add(Mon(rwid=40, cr="1", name="Base Goblin (#1)", exp="Base", class_="Monsters"))
    db.add(Mon(rwid=41, cr="2", name="Base Sword (#2)", exp="Base", class_="Item"))
    db.add(CardInSet(rwid=900, setid=0, monid=40))
    db.add(CardInSet(rwid=901, setid=0, monid=41))
    db.commit()

    creatures = client.get("/api/users/111/sets/BaseCreatures").json()
    assert [c["name"] for c in creatures] == ["Base Goblin (#1)"]

    items = client.get("/api/users/111/sets/BaseItems").json()
    assert [c["name"] for c in items] == ["Base Sword (#2)"]

    # No base locations were seeded.
    assert client.get("/api/users/111/sets/BaseLocations").json() == []


def test_set_view_ownership(client):
    rows = client.get("/api/users/111/sets/Starter_Creatures").json()
    assert len(rows) == 1
    slot = rows[0]
    assert slot["name"] == "Goblin (#1)"
    assert slot["has"] is True
    assert slot["count"] == 1
    assert slot["cards"][0]["collection_id"] == 100


def test_card_layer_image_served(client):
    resp = client.get("/api/cards/Color/Blue.png")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"


def test_card_layers_manifest(client):
    body = client.get("/api/card-layers").json()
    assert "Blue.png" in body["color"]
    assert "1.png" in body["cards"]
    assert body["holo"] and all(h.endswith(".png") for h in body["holo"])
    assert body["grade"]


def test_protected_me_requires_auth(client):
    assert client.get("/api/auth/me").status_code == 401
