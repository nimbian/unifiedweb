"""Tests for the leaderboard endpoint (top pulls per window + Perfect 30)."""

from datetime import datetime, timedelta, timezone


def _add_card(db, *, rwid, monid, value, date, name, uid=1):
    from app.models import Collection, Mon

    db.add(Mon(rwid=monid, cr="10", name=name, exp="Base", class_="Monsters"))
    db.add(Collection(rwid=rwid, uid=uid, monid=monid, grade=10, holo=1, value=value, date=date))


def test_leaderboard_windows_and_ties(client, db):
    now = datetime.now(timezone.utc)
    # Today: two cards tie at the top value (9000), one lower (100).
    _add_card(db, rwid=200, monid=20, value=9000, date=now, name="Dragon (#10)")
    _add_card(db, rwid=201, monid=21, value=9000, date=now, name="Hydra (#10)")
    _add_card(db, rwid=202, monid=22, value=100, date=now, name="Rat (#10)")
    # 3 days ago: a higher card that only counts in the 7-day / month windows.
    _add_card(db, rwid=203, monid=23, value=12000, date=now - timedelta(days=3), name="Titan (#10)")
    db.commit()

    body = client.get("/api/leaderboard").json()

    # Today's top = the two tied 9000 cards (the 100 card is excluded).
    today = body["today"]
    assert len(today) == 2
    assert {c["name"] for c in today} == {"Dragon (#10)", "Hydra (#10)"}
    assert all(float(c["value"]) == 9000 for c in today)

    # Past 7 days top = the 12000 card pulled 3 days ago (3 < 7, date-independent).
    assert len(body["past_7_days"]) == 1
    assert body["past_7_days"][0]["name"] == "Titan (#10)"
    assert float(body["past_7_days"][0]["value"]) == 12000

    # The month window always contains today's pulls, so its top is at least
    # today's top (and equals 12000 whenever the 3-days-ago card is in-month).
    assert len(body["this_month"]) >= 1
    assert float(body["this_month"][0]["value"]) >= 9000


def test_leaderboard_perfect_thirty(client, db):
    now = datetime.now(timezone.utc)
    _add_card(db, rwid=210, monid=30, value=10000, date=now, name="Perfect A (#10)")
    _add_card(db, rwid=211, monid=31, value=10000, date=now - timedelta(days=400), name="Perfect B (#10)")
    _add_card(db, rwid=212, monid=32, value=9999.999, date=now, name="Almost (#10)")
    db.commit()

    perfect = client.get("/api/leaderboard").json()["perfect_thirty"]
    names = {c["name"] for c in perfect}
    assert names == {"Perfect A (#10)", "Perfect B (#10)"}  # exactly 10000, any date
    assert all(float(c["value"]) == 10000 for c in perfect)


def test_leaderboard_empty_windows(client):
    # The seeded card (value 5, no date) is not a top pull today and not 10000.
    body = client.get("/api/leaderboard").json()
    assert body["today"] == []
    assert body["perfect_thirty"] == []


def test_leaderboard_top_collections_and_best_copy(client, db):
    from app.models import Collection, Mon, User

    # Second user, Bob, owns two copies of the SAME mon (values 30 and 20).
    db.add(User(rwid=2, name="Bob", did=222, gp=0))
    db.add(Mon(rwid=50, cr="5", name="Bob Mon (#5)", exp="Base", class_="Monsters"))
    db.add(Collection(rwid=500, uid=2, monid=50, grade=10, holo=0, value=30))
    db.add(Collection(rwid=501, uid=2, monid=50, grade=9, holo=0, value=20))
    db.commit()

    body = client.get("/api/leaderboard").json()

    # Total collection value: Bob 50 (30+20) > Alice 5 (seeded).
    tops = body["top_collections"]
    assert [t["user"] for t in tops] == ["Bob", "Alice"]
    assert float(tops[0]["value"]) == 50.0
    assert tops[0]["did"] == "222"
    assert isinstance(tops[0]["did"], str)

    # Best copy: Bob's two copies of monid 50 collapse to the most valuable (30).
    best = body["best_copy_collections"]
    assert [b["user"] for b in best] == ["Bob", "Alice"]
    assert float(best[0]["value"]) == 30.0
    assert float(best[1]["value"]) == 5.0


def test_leaderboard_excludes_web_first_users(client, db):
    """A web-first (did NULL) account never appears on the leaderboard, even
    holding a would-be #1 card — Satchemon is played through the Discord bot, so
    only Discord-linked players have standings (PLAN §6.2)."""
    from app.models import Collection, Mon, User

    now = datetime.now(timezone.utc)
    # A Twitch/Google-first user (no Discord link) with a huge dated card.
    db.add(User(rwid=3, name="WebFirst", did=None, gp=0))
    db.add(Mon(rwid=90, cr="10", name="Ghost (#10)", exp="Base", class_="Monsters"))
    db.add(Collection(rwid=900, uid=3, monid=90, grade=10, holo=1, value=99999, date=now))
    db.commit()

    body = client.get("/api/leaderboard").json()
    # Absent from every ranking despite the top value.
    assert all(c["name"] != "Ghost (#10)" for c in body["today"])
    assert all(r["user"] != "WebFirst" for r in body["top_collections"])
    assert all(r["user"] != "WebFirst" for r in body["best_copy_collections"])
    assert all(r["user"] != "WebFirst" for r in body["pristine_hunters"])


def test_leaderboard_pristine_hunters(client, db):
    from app.models import Collection, Mon, User

    # Bob holds two pristine cards (grade 10 + holo); Alice has one (the seeded
    # Goblin: grade 10, holo 1). A grade-10 non-holo and a holo non-10 don't count.
    db.add(User(rwid=2, name="Bob", did=222, gp=0))
    db.add(Mon(rwid=60, cr="5", name="Pristine Mon (#5)", exp="Base", class_="Monsters"))
    db.add(Collection(rwid=600, uid=2, monid=60, grade=10, holo=1, value=1))
    db.add(Collection(rwid=601, uid=2, monid=60, grade=10, holo=1, value=1))
    db.add(Collection(rwid=602, uid=2, monid=60, grade=10, holo=0, value=1))  # not holo
    db.add(Collection(rwid=603, uid=2, monid=60, grade=9, holo=1, value=1))   # not grade 10
    db.commit()

    hunters = client.get("/api/leaderboard").json()["pristine_hunters"]
    assert [h["user"] for h in hunters] == ["Bob", "Alice"]
    assert hunters[0]["count"] == 2
    assert hunters[1]["count"] == 1
    assert hunters[0]["did"] == "222"
    assert isinstance(hunters[0]["did"], str)
