"""Tests for the user progress endpoint (general stats + per-set completion)."""


def test_progress_unknown_user_404(client):
    assert client.get("/api/users/999/progress").status_code == 404


def test_progress_stats_basic(client):
    # Seeded Alice owns one card (Goblin, value 5), in the "Starter Creatures" set.
    body = client.get("/api/users/111/progress").json()
    stats = body["stats"]
    assert float(stats["total_value"]) == 5.0
    assert float(stats["top_value"]) == 5.0
    assert stats["total_cards"] == 1
    assert stats["unique_cards"] == 1


def test_progress_top_value_dedupes_to_most_valuable(client, db):
    # A second, more valuable copy of the same mon (Goblin, monid 10).
    from app.models import Collection

    db.add(Collection(rwid=200, uid=1, monid=10, grade=9, holo=0, value=12, ed="First"))
    db.commit()

    stats = client.get("/api/users/111/progress").json()["stats"]
    # total counts both copies; top_value keeps only the most valuable per mon.
    assert float(stats["total_value"]) == 17.0
    assert float(stats["top_value"]) == 12.0
    assert stats["total_cards"] == 2
    assert stats["unique_cards"] == 1


def test_progress_set_completion(client):
    # "Starter Creatures" has one slot (Goblin) which Alice owns -> 1/1.
    # It is also an expansion (seeded), so it lands in the expansions category.
    sets = client.get("/api/users/111/progress").json()["sets"]
    by_name = {s["name"]: s for s in sets}
    assert "Starter Creatures" in by_name
    sc = by_name["Starter Creatures"]
    assert sc["owned"] == 1
    assert sc["total"] == 1
    assert sc["category"] == "expansions"
    assert sc["slug"] == "Starter_Creatures"
    assert sc["role"] == "starter_creatures"  # sets.role, shown when complete


def test_progress_unique_set_partial(client, db):
    # A creature set (rwid 1..49) that is NOT an expansion -> "sets" category.
    # Two slots, Alice owns one of them.
    from app.models import CardInSet, Mon, Set

    db.add(Set(rwid=7, name="Forest Pack", role="forest_pack"))
    db.add(Mon(rwid=70, cr="1", name="Wolf (#1)", exp="Base", class_="Monsters"))
    db.add(Mon(rwid=71, cr="2", name="Bear (#2)", exp="Base", class_="Monsters"))
    db.add(CardInSet(rwid=700, setid=7, monid=70))  # owned (monid 10? no) -> owned via collection
    db.add(CardInSet(rwid=701, setid=7, monid=71))  # not owned
    # Alice owns Wolf now.
    from app.models import Collection

    db.add(Collection(rwid=300, uid=1, monid=70, grade=8, holo=0, value=3, ed="First"))
    db.commit()

    sets = client.get("/api/users/111/progress").json()["sets"]
    fp = next(s for s in sets if s["name"] == "Forest Pack")
    assert fp["category"] == "sets"
    assert fp["group"] == "Creatures"  # rwid 7 -> creature range
    assert fp["total"] == 2
    assert fp["owned"] == 1
    assert fp["slug"] == "Forest_Pack"


def test_progress_base_sets_broken_out_by_class(client, db):
    # A base set (rwid <= 0) with a creature and an item slot; Alice owns the item.
    from app.models import CardInSet, Collection, Mon, Set

    db.add(Set(rwid=0, name="Base Set", role="base"))
    db.add(Mon(rwid=80, cr="1", name="Base Goblin (#1)", exp="Base", class_="Monsters"))
    db.add(Mon(rwid=81, cr="2", name="Base Sword (#2)", exp="Base", class_="Item"))
    db.add(CardInSet(rwid=800, setid=0, monid=80))
    db.add(CardInSet(rwid=801, setid=0, monid=81))
    db.add(Collection(rwid=400, uid=1, monid=81, grade=10, holo=0, value=4, ed="First"))
    db.commit()

    sets = client.get("/api/users/111/progress").json()["sets"]
    base = {s["name"]: s for s in sets if s["category"] == "baseSets"}
    assert base["Creatures"]["slug"] == "BaseCreatures"
    assert base["Creatures"] == {
        "name": "Creatures",
        "slug": "BaseCreatures",
        "category": "baseSets",
        "group": None,
        "role": "base",  # sets.rwid 0 (Creatures) carries the base-set role
        "owned": 0,
        "total": 1,
    }
    assert base["Items"]["owned"] == 1
    assert base["Items"]["total"] == 1
