"""Portal-session bridge at the web-API layer: an Authorization: Bearer portal
token authenticates a request and maps onto the arena's (twitch, id) user, while
the signed-cookie Twitch flow keeps working (PLAN §8).
"""

from __future__ import annotations

import random
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
jwt = pytest.importorskip("jwt")
pytest.importorskip("cryptography")

from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from server.arena import Arena  # noqa: E402
from server.config import Config  # noqa: E402
from server.events import RecordingSink  # noqa: E402
from server.portal_auth import PortalAuth  # noqa: E402
from server.store import MemoryStore  # noqa: E402
from server.webapi import TwitchOAuth, WebDeps, attach_web_api  # noqa: E402
from server.websession import SessionSigner  # noqa: E402
from server.ws import WebSocketHub, build_app  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GAME_CONFIG = PROJECT_ROOT / "config" / "game.toml"
STATS = {"STR": 15, "DEX": 14, "CON": 13, "INT": 12, "WIS": 11, "CHA": 10}


def _fixed_now() -> datetime:
    return datetime(2026, 7, 1, 12, 0, 0, tzinfo=UTC)


async def _nosleep(_s: float) -> None:
    return None


def _keypair() -> tuple[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    pub = key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return priv, pub


class PortalHarness:
    def __init__(self) -> None:
        self.priv, pub = _keypair()
        cfg = Config.load(GAME_CONFIG)
        self.store = MemoryStore()
        self.sink = RecordingSink()
        self.arena = Arena(
            cfg, self.store, self.sink, rng=random.Random(1), sleep=_nosleep, now=_fixed_now
        )
        self.signer = SessionSigner("test-session-secret")
        self.deps = WebDeps(
            cfg=cfg, store=self.store, arena=self.arena, sink=self.sink,
            signer=self.signer, oauth=TwitchOAuth("cid", "csec", "http://testserver"),
            portal=PortalAuth(pub),
        )
        app = build_app(WebSocketHub())
        attach_web_api(app, self.deps)
        self.client = TestClient(app)

    def token(self, *, twitch_uid: str = "tw-1", login: str = "brian",
              name: str = "Brian", rwid: int = 7, **extra: object) -> str:
        now = int(time.time())
        claims: dict[str, object] = {
            "sub": str(rwid), "type": "access", "ver": 2,
            "twitch_uid": twitch_uid, "twitch_login": login, "name": name,
            "iat": now, "exp": now + 900,
        }
        claims.update(extra)
        return jwt.encode(claims, self.priv, algorithm="RS256")

    def bearer(self, **kw: object) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token(**kw)}"}


def test_portal_bearer_authenticates_me():
    h = PortalHarness()
    uid = h.store.add_user("brian", platform_user_id="tw-1")
    h.store.users[uid]["gold"] = 250
    body = h.client.get("/api/me", headers=h.bearer(twitch_uid="tw-1")).json()
    assert body["user"]["id"] == uid
    assert body["gold"] == 250


def test_portal_bearer_owns_its_characters():
    h = PortalHarness()
    uid = h.store.add_user("brian", platform_user_id="tw-1")
    ch = h.store.create_character(
        user_id=uid, name="Thorak", class_name="barbarian", race="orc",
        stats=dict(STATS), sprite_set="barb_01",
    )
    sheet = h.client.get(f"/api/characters/{ch.id}", headers=h.bearer(twitch_uid="tw-1")).json()
    assert sheet["is_owner"] is True

    listing = h.client.get("/api/characters", headers=h.bearer(twitch_uid="tw-1")).json()
    assert [c["id"] for c in listing["living"]] == [ch.id]


def test_portal_bearer_not_owner_of_someone_elses_character():
    h = PortalHarness()
    owner = h.store.add_user("owner", platform_user_id="tw-owner")
    ch = h.store.create_character(
        user_id=owner, name="Thorak", class_name="barbarian", race="orc",
        stats=dict(STATS), sprite_set="barb_01",
    )
    sheet = h.client.get(f"/api/characters/{ch.id}", headers=h.bearer(twitch_uid="tw-other")).json()
    assert sheet["is_owner"] is False


def test_portal_unknown_twitch_gets_empty_roster():
    # A portal user who never played the arena: register_user upserts an empty
    # user (rule #4 key), and the roster is simply empty.
    h = PortalHarness()
    body = h.client.get("/api/characters", headers=h.bearer(twitch_uid="tw-brand-new")).json()
    assert body == {"living": [], "retired": []}


def test_no_credentials_is_unauthenticated():
    h = PortalHarness()
    assert h.client.get("/api/me").status_code == 401


def test_invalid_bearer_is_unauthenticated():
    h = PortalHarness()
    resp = h.client.get("/api/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert resp.status_code == 401


def test_bearer_without_twitch_uid_rejected():
    h = PortalHarness()
    # A Discord-only portal token (no twitch_uid) cannot act in the arena.
    now = int(time.time())
    tok = jwt.encode(
        {"sub": "9", "type": "access", "ver": 2, "name": "NoTwitch",
         "iat": now, "exp": now + 900},
        h.priv, algorithm="RS256",
    )
    resp = h.client.get("/api/me", headers={"Authorization": f"Bearer {tok}"})
    assert resp.status_code == 401


def test_signed_cookie_still_works_alongside_portal():
    h = PortalHarness()
    uid = h.store.add_user("brian", platform_user_id="tw-1")
    cookie = h.signer.sign({"uid": uid, "login": "brian", "name": "Brian"})
    h.client.cookies.set("dnd_session", cookie)
    assert h.client.get("/api/me").json()["user"]["id"] == uid
