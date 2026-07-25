"""Tests for the Midweek Monster Mash donor-badge endpoints.

Exercises the ported points/total/rank computation (from the old app.js) end to
end through the router -> service -> repo path.
"""


def _add(db, name, **counts):
    from app.models import MmmDonor

    db.add(MmmDonor(name=name, **counts))


def test_badges_catalog(client):
    tiers = client.get("/api/mmm/badges").json()
    assert [t["key"] for t in tiers] == [
        "initiate", "apprentice", "knight", "master", "ascendant", "luminary", "arbiter",
    ]
    # Point values and titles match the original app.js catalog.
    assert tiers[0] == {"key": "initiate", "title": "Initiate of the Guild", "points": 0.5}
    assert tiers[-1]["title"] == "Arbiter of the Cosmic Balance"
    assert tiers[-1]["points"] == 275


def test_leaderboard_points_totals_and_tie_ranks(client, db):
    # Alice: 2 initiates (2*0.5=1) + 1 apprentice (5) = 6.0 pts, 3 badges.
    _add(db, "Alice", initiate=2, apprentice=1)
    _add(db, "Bob", knight=1)     # 25.0 pts, 1 badge
    _add(db, "Dave", knight=1)    # 25.0 pts, 1 badge — ties Bob on points
    _add(db, "Cara")              # 0 pts, 0 badges — still listed
    db.commit()

    rows = client.get("/api/mmm/donors").json()
    assert [r["name"] for r in rows] == ["Bob", "Dave", "Alice", "Cara"]

    by_name = {r["name"]: r for r in rows}
    assert by_name["Alice"]["points"] == 6.0          # exercises the 0.5 tier
    assert by_name["Alice"]["total_badges"] == 3
    assert by_name["Alice"]["badges"]["initiate"] == 2
    assert by_name["Alice"]["badges"]["arbiter"] == 0
    # Bob and Dave tie on points -> share rank 1; the next distinct score skips to 3.
    assert by_name["Bob"]["rank"] == 1
    assert by_name["Dave"]["rank"] == 1
    assert by_name["Alice"]["rank"] == 3
    assert by_name["Cara"]["rank"] == 4
    assert by_name["Cara"]["points"] == 0.0


def test_donor_by_name_is_case_insensitive(client, db):
    _add(db, "Zephyr", master=1, initiate=1)   # 75 + 0.5 = 75.5
    db.commit()

    d = client.get("/api/mmm/donors/zephyr").json()
    assert d["name"] == "Zephyr"
    assert d["points"] == 75.5
    assert d["total_badges"] == 2
    assert d["rank"] == 1


def test_unknown_donor_404(client):
    resp = client.get("/api/mmm/donors/nobody")
    assert resp.status_code == 404
    assert "nobody" in resp.json()["detail"].lower()


def test_empty_leaderboard(client):
    assert client.get("/api/mmm/donors").json() == []
