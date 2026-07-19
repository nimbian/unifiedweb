"""Auth tests — multi-provider OAuth login and account linking.

The only network boundary (``AuthService._fetch_identity``) is patched so no real
OAuth traffic happens; every test drives the full router -> service -> repo path.
"""

from app.core.security import create_access_token
from app.models import User
from app.services.auth_service import AuthService, ProviderIdentity


def _patch_identity(monkeypatch, identity: ProviderIdentity) -> None:
    """Make the next provider exchange resolve to ``identity`` (no HTTP)."""

    async def fake(self, provider, code):  # noqa: ANN001, ARG001
        return identity

    monkeypatch.setattr(AuthService, "_fetch_identity", fake)


def _headers_for(did: str) -> dict[str, str]:
    token = create_access_token(did, extra_claims={"name": f"user-{did}"})
    return {"Authorization": f"Bearer {token}"}


# ── authorize URLs ────────────────────────────────────────────────────────────
def test_authorize_url_per_provider(client):
    for provider, host in [
        ("discord", "discord.com"),
        ("google", "accounts.google.com"),
        ("twitch", "id.twitch.tv"),
    ]:
        body = client.get(f"/api/auth/{provider}/url").json()
        assert host in body["url"]
        assert body["state"]


def test_unknown_provider_404(client):
    assert client.get("/api/auth/myspace/url").status_code == 404


# ── login ─────────────────────────────────────────────────────────────────────
def test_discord_login_issues_tokens(client, monkeypatch):
    # The seeded user (did=111, rwid=1, name="Alice") signs in with Discord.
    _patch_identity(monkeypatch, ProviderIdentity("discord", "111", "Alice#Ds"))
    resp = client.post("/api/auth/discord", json={"code": "x"})
    assert resp.status_code == 200
    token = resp.json()["access_token"]

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert me["did"] == "111"
    assert me["rwid"] == 1
    assert me["name"] == "Alice"


def test_google_login_requires_link(client, monkeypatch):
    # An unlinked Google account cannot sign in.
    _patch_identity(monkeypatch, ProviderIdentity("google", "g-unlinked", "Nobody"))
    resp = client.post("/api/auth/google", json={"code": "x"})
    assert resp.status_code == 401
    assert "link" in resp.json()["detail"].lower()


# ── linking ───────────────────────────────────────────────────────────────────
def test_link_then_login_with_google(client, auth_headers, monkeypatch):
    # Alice (did=111) links her Google account…
    _patch_identity(monkeypatch, ProviderIdentity("google", "g-123", "Alice on YT"))
    linked = client.post("/api/auth/google/link", json={"code": "x"}, headers=auth_headers).json()
    assert linked["google"]["linked"] is True
    assert linked["google"]["handle"] == "Alice on YT"
    assert linked["discord"]["linked"] is True

    # …and can now sign in with Google, landing on the same Discord identity.
    _patch_identity(monkeypatch, ProviderIdentity("google", "g-123", "Alice on YT"))
    resp = client.post("/api/auth/google", json={"code": "y"})
    assert resp.status_code == 200
    me = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {resp.json()['access_token']}"},
    ).json()
    assert me["did"] == "111"
    assert me["rwid"] == 1


def test_link_conflict_when_already_linked_elsewhere(client, db, auth_headers, monkeypatch):
    # A second registered user.
    db.add(User(rwid=2, name="Bob", did=222, gp=0))
    db.commit()

    # Alice links a Twitch account.
    _patch_identity(monkeypatch, ProviderIdentity("twitch", "t-shared", "shared_tv"))
    assert client.post("/api/auth/twitch/link", json={"code": "x"}, headers=auth_headers).status_code == 200

    # Bob tries to link the *same* Twitch account -> 409.
    _patch_identity(monkeypatch, ProviderIdentity("twitch", "t-shared", "shared_tv"))
    resp = client.post("/api/auth/twitch/link", json={"code": "x"}, headers=_headers_for("222"))
    assert resp.status_code == 409


def test_relinking_same_account_to_self_is_ok(client, auth_headers, monkeypatch):
    ident = ProviderIdentity("twitch", "t-self", "self_tv")
    _patch_identity(monkeypatch, ident)
    assert client.post("/api/auth/twitch/link", json={"code": "x"}, headers=auth_headers).status_code == 200
    _patch_identity(monkeypatch, ident)
    resp = client.post("/api/auth/twitch/link", json={"code": "x"}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["twitch"]["linked"] is True


def test_unlink(client, auth_headers, monkeypatch):
    _patch_identity(monkeypatch, ProviderIdentity("google", "g-drop", "Drop Me"))
    client.post("/api/auth/google/link", json={"code": "x"}, headers=auth_headers)

    resp = client.delete("/api/auth/google/link", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["google"]["linked"] is False


def test_cannot_link_or_unlink_discord(client, auth_headers, monkeypatch):
    _patch_identity(monkeypatch, ProviderIdentity("discord", "111", "Alice"))
    assert client.post("/api/auth/discord/link", json={"code": "x"}, headers=auth_headers).status_code == 400
    assert client.delete("/api/auth/discord/link", headers=auth_headers).status_code == 400


def test_links_requires_auth(client):
    assert client.get("/api/auth/links").status_code == 401
