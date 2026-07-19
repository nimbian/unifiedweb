"""Tests for selecting a role from completed sets + showing it on the profile."""


def _complete_starter_set(db):
    """Mark the seeded user (did 111) as having completed 'Starter Creatures'
    (sets.rwid 5, sets.role 'starter_creatures')."""
    from app.models import CompletedSet

    db.add(CompletedSet(rwid=1, setname="starter_creatures", did=111))
    db.commit()


def test_role_options_requires_auth(client):
    assert client.get("/api/me/roles").status_code == 401


def test_role_options_lists_completed_sets(client, db, auth_headers):
    _complete_starter_set(db)
    opts = client.get("/api/me/roles", headers=auth_headers).json()
    assert opts == [{"rwid": 5, "name": "Starter Creatures", "role": "starter_creatures"}]


def test_set_and_display_role(client, db, auth_headers):
    _complete_starter_set(db)

    # Select the role.
    res = client.put("/api/me/role", json={"roleid": 5}, headers=auth_headers)
    assert res.status_code == 200
    assert res.json() == {"roleid": 5, "role": "starter_creatures"}

    # It now shows on the public profile.
    profile = client.get("/api/users/111").json()
    assert profile["roleid"] == 5
    assert profile["role"] == "starter_creatures"


def test_clear_role(client, db, auth_headers):
    _complete_starter_set(db)
    client.put("/api/me/role", json={"roleid": 5}, headers=auth_headers)

    cleared = client.put("/api/me/role", json={"roleid": None}, headers=auth_headers)
    assert cleared.json() == {"roleid": None, "role": None}

    profile = client.get("/api/users/111").json()
    assert profile["roleid"] is None
    assert profile["role"] is None


def test_cannot_select_uncompleted_set(client, db, auth_headers):
    _complete_starter_set(db)
    # rwid 5 is completed; 999 is not.
    assert client.put("/api/me/role", json={"roleid": 999}, headers=auth_headers).status_code == 400


def test_profile_role_defaults_null(client):
    # No role set, no completed sets.
    profile = client.get("/api/users/111").json()
    assert profile["roleid"] is None
    assert profile["role"] is None
