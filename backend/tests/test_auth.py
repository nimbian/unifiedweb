"""Auth tests — resolve-or-create login, provider linking (incl. Discord), and
the v1-token grace path.

The only network boundary (``AuthService._fetch_identity``) is patched so no real
OAuth traffic happens; every test drives the full router -> service -> repo path.
"""

import os
from datetime import UTC, datetime, timedelta

from jose import jwt
from sqlalchemy import select

from app.core.security import create_access_token
from app.models import User
from app.services.auth_service import AuthService, ProviderIdentity


def _patch_identity(monkeypatch, identity: ProviderIdentity) -> None:
    """Make the next provider exchange resolve to ``identity`` (no HTTP)."""

    async def fake(self, provider, code):  # noqa: ANN001, ARG001
        return identity

    monkeypatch.setattr(AuthService, "_fetch_identity", fake)


def _hdr(resp) -> dict[str, str]:
    """Bearer header from a login/refresh response's access token."""
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _v2_headers(rwid: int, *, did: str | None = None, name: str | None = None) -> dict[str, str]:
    """A v2 access token (sub = rwid) for an already-registered user."""
    claims: dict[str, object] = {"ver": 2}
    if did is not None:
        claims["did"] = did
    if name is not None:
        claims["name"] = name
    return {"Authorization": f"Bearer {create_access_token(str(rwid), extra_claims=claims)}"}


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


# ── login: resolve existing ───────────────────────────────────────────────────
def test_discord_login_resolves_existing(client, monkeypatch):
    # The seeded user (did=111, rwid=1, name="Alice") signs in with Discord.
    _patch_identity(monkeypatch, ProviderIdentity("discord", "111", "Alice#Ds"))
    resp = client.post("/api/auth/discord", json={"code": "x"})
    assert resp.status_code == 200

    me = client.get("/api/auth/me", headers=_hdr(resp)).json()
    assert me["did"] == "111"
    assert me["rwid"] == 1
    assert me["name"] == "Alice"


# ── login: create-on-first-login, per provider ───────────────────────────────
def test_twitch_login_creates_account(client, db, monkeypatch):
    _patch_identity(monkeypatch, ProviderIdentity("twitch", "t-new", "TwitchFirst"))
    resp = client.post("/api/auth/twitch", json={"code": "x"})
    assert resp.status_code == 200

    me = client.get("/api/auth/me", headers=_hdr(resp)).json()
    assert me["rwid"] and me["rwid"] != 1   # a brand-new row
    assert me["did"] is None                # web-first: no Discord yet

    row = db.execute(select(User).where(User.twitch_uid == "t-new")).scalar_one()
    assert row.rwid == me["rwid"]
    assert row.name == "TwitchFirst"
    assert row.created_via == "twitch"
    assert row.created_at is not None
    assert row.did is None


def test_google_login_creates_account(client, db, monkeypatch):
    _patch_identity(monkeypatch, ProviderIdentity("google", "g-new", "GoogFirst"))
    resp = client.post("/api/auth/google", json={"code": "x"})
    assert resp.status_code == 200

    me = client.get("/api/auth/me", headers=_hdr(resp)).json()
    assert me["did"] is None

    row = db.execute(select(User).where(User.google_sub == "g-new")).scalar_one()
    assert row.created_via == "google"
    assert row.google_name == "GoogFirst"


def test_discord_login_creates_account(client, db, monkeypatch):
    _patch_identity(monkeypatch, ProviderIdentity("discord", "999", "NewDiscord"))
    resp = client.post("/api/auth/discord", json={"code": "x"})
    assert resp.status_code == 200

    me = client.get("/api/auth/me", headers=_hdr(resp)).json()
    assert me["did"] == "999"

    row = db.execute(select(User).where(User.did == 999)).scalar_one()
    assert row.rwid == me["rwid"]
    assert row.created_via == "discord"


# ── linking a non-Discord provider, then logging in with it ───────────────────
def test_link_then_login_with_google(client, auth_headers, monkeypatch):
    # Alice (rwid=1) links her Google account…
    _patch_identity(monkeypatch, ProviderIdentity("google", "g-123", "Alice on YT"))
    linked = client.post("/api/auth/google/link", json={"code": "x"}, headers=auth_headers).json()
    assert linked["google"]["linked"] is True
    assert linked["google"]["handle"] == "Alice on YT"
    assert linked["discord"]["linked"] is True

    # …and can now sign in with Google, landing on the same rwid.
    _patch_identity(monkeypatch, ProviderIdentity("google", "g-123", "Alice on YT"))
    resp = client.post("/api/auth/google", json={"code": "y"})
    assert resp.status_code == 200
    me = client.get("/api/auth/me", headers=_hdr(resp)).json()
    assert me["did"] == "111"
    assert me["rwid"] == 1


# ── Discord is now linkable / unlinkable ──────────────────────────────────────
def test_discord_link_and_unlink_on_web_first_account(client, monkeypatch):
    # A Twitch-first account (did NULL).
    _patch_identity(monkeypatch, ProviderIdentity("twitch", "t-web", "WebUser"))
    headers = _hdr(client.post("/api/auth/twitch", json={"code": "x"}))

    links = client.get("/api/auth/links", headers=headers).json()
    assert links["discord"]["linked"] is False
    assert links["twitch"]["linked"] is True

    # Link Discord (keyed on rwid — works even though the token carries no did).
    _patch_identity(monkeypatch, ProviderIdentity("discord", "555", "MyDiscord"))
    linked = client.post("/api/auth/discord/link", json={"code": "x"}, headers=headers).json()
    assert linked["discord"]["linked"] is True

    # Unlink Discord again; Twitch remains, so it is allowed.
    resp = client.delete("/api/auth/discord/link", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["discord"]["linked"] is False
    assert resp.json()["twitch"]["linked"] is True


def test_unlink_google_keeps_discord(client, auth_headers, monkeypatch):
    _patch_identity(monkeypatch, ProviderIdentity("google", "g-drop", "Drop Me"))
    client.post("/api/auth/google/link", json={"code": "x"}, headers=auth_headers)

    resp = client.delete("/api/auth/google/link", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["google"]["linked"] is False
    assert resp.json()["discord"]["linked"] is True


# ── a row must always keep ≥ 1 provider ───────────────────────────────────────
def test_cannot_unlink_last_provider(client, monkeypatch):
    _patch_identity(monkeypatch, ProviderIdentity("twitch", "t-only", "Solo"))
    headers = _hdr(client.post("/api/auth/twitch", json={"code": "x"}))

    resp = client.delete("/api/auth/twitch/link", headers=headers)
    assert resp.status_code == 400
    assert "at least one" in resp.json()["detail"].lower()

    # Still connected — nothing was removed.
    assert client.get("/api/auth/links", headers=headers).json()["twitch"]["linked"] is True


# ── conflicts (409) ───────────────────────────────────────────────────────────
def test_link_conflict_when_already_linked_elsewhere(client, db, auth_headers, monkeypatch):
    db.add(User(rwid=2, name="Bob", did=222, gp=0))
    db.commit()

    # Alice links a Twitch account.
    _patch_identity(monkeypatch, ProviderIdentity("twitch", "t-shared", "shared_tv"))
    assert client.post(
        "/api/auth/twitch/link", json={"code": "x"}, headers=auth_headers
    ).status_code == 200

    # Bob tries to link the *same* Twitch account -> 409.
    _patch_identity(monkeypatch, ProviderIdentity("twitch", "t-shared", "shared_tv"))
    resp = client.post(
        "/api/auth/twitch/link", json={"code": "x"}, headers=_v2_headers(2, did="222")
    )
    assert resp.status_code == 409


def test_discord_link_conflict_uses_guidance_message(client, monkeypatch):
    # A Twitch-first account tries to link Discord 111, which the seeded Alice owns.
    _patch_identity(monkeypatch, ProviderIdentity("twitch", "t-conf", "Conf"))
    headers = _hdr(client.post("/api/auth/twitch", json={"code": "x"}))

    _patch_identity(monkeypatch, ProviderIdentity("discord", "111", "AliceDiscord"))
    resp = client.post("/api/auth/discord/link", json={"code": "x"}, headers=headers)
    assert resp.status_code == 409
    # The PLAN §7 guidance message.
    assert "Satchemon profile" in resp.json()["detail"]
    assert "Sign in with Discord" in resp.json()["detail"]


def test_relinking_same_account_to_self_is_ok(client, auth_headers, monkeypatch):
    ident = ProviderIdentity("twitch", "t-self", "self_tv")
    _patch_identity(monkeypatch, ident)
    assert client.post(
        "/api/auth/twitch/link", json={"code": "x"}, headers=auth_headers
    ).status_code == 200
    _patch_identity(monkeypatch, ident)
    resp = client.post("/api/auth/twitch/link", json={"code": "x"}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["twitch"]["linked"] is True


# ── v1-token grace (PLAN §5) ──────────────────────────────────────────────────
def test_v1_token_grace(client):
    """A v1 access token (sub = did, no ver, signed with the OLD HS256 secret)
    still verifies and resolves to the right principal, and downstream Satchemon
    routes work through it."""
    now = datetime.now(UTC)
    payload = {
        "sub": "111",           # v1: subject is the Discord id
        "type": "access",
        "name": "Alice",
        "rwid": 1,              # old tokens carried rwid as a claim
        "iat": now,
        "exp": now + timedelta(minutes=15),
    }
    token = jwt.encode(payload, os.environ["JWT_LEGACY_SECRET"], algorithm="HS256")
    headers = {"Authorization": f"Bearer {token}"}

    me = client.get("/api/auth/me", headers=headers).json()
    assert me["did"] == "111"
    assert me["rwid"] == 1

    # And a Satchemon /me route resolves via the v1 did.
    prof = client.get("/api/me", headers=headers)
    assert prof.status_code == 200
    assert prof.json()["did"] == "111"


def test_v1_token_with_wrong_secret_rejected(client):
    now = datetime.now(UTC)
    payload = {"sub": "111", "type": "access", "iat": now, "exp": now + timedelta(minutes=15)}
    token = jwt.encode(payload, "some-other-secret", algorithm="HS256")
    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


# ── refresh mints a fresh v2 access token ─────────────────────────────────────
def test_refresh_after_login(client, monkeypatch):
    _patch_identity(monkeypatch, ProviderIdentity("discord", "111", "Alice"))
    client.post("/api/auth/discord", json={"code": "x"})   # sets the refresh cookie

    resp = client.post("/api/auth/refresh")
    assert resp.status_code == 200
    me = client.get("/api/auth/me", headers=_hdr(resp)).json()
    assert me["rwid"] == 1
    assert me["did"] == "111"


# ── did-less users get a clean 409 (not a 500) on Satchemon /me ───────────────
def test_web_first_user_blocked_from_satchemon_me(client, monkeypatch):
    _patch_identity(monkeypatch, ProviderIdentity("twitch", "t-nosat", "NoSat"))
    headers = _hdr(client.post("/api/auth/twitch", json={"code": "x"}))

    resp = client.get("/api/me", headers=headers)
    assert resp.status_code == 409
    assert "discord" in resp.json()["detail"].lower()


# ── auth required ─────────────────────────────────────────────────────────────
def test_links_requires_auth(client):
    assert client.get("/api/auth/links").status_code == 401
