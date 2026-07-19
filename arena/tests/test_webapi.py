"""Player-website API tests (server/webapi.py): session auth, ownership,
gear/rename/retire mutations, public reads, OAuth callback, SPA fallback.

Needs the optional runtime deps (fastapi + httpx for TestClient); skips cleanly
without them, like tests/test_ws.py.
"""

from __future__ import annotations

import asyncio
import random
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("jwt")  # server.webapi -> portal_auth imports PyJWT

from fastapi.testclient import TestClient  # noqa: E402

from server.arena import Arena  # noqa: E402
from server.config import Config  # noqa: E402
from server.events import RecordingSink  # noqa: E402
from server.store import MemoryStore  # noqa: E402
from server.webapi import TwitchOAuth, WebDeps, attach_web_api, mount_spa  # noqa: E402
from server.websession import SessionSigner  # noqa: E402
from server.ws import WebSocketHub, build_app  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GAME_CONFIG = PROJECT_ROOT / "config" / "game.toml"
STATS = {"STR": 15, "DEX": 14, "CON": 13, "INT": 12, "WIS": 11, "CHA": 10}
SECRET = "test-session-secret"


def _fixed_now() -> datetime:
    return datetime(2026, 7, 1, 12, 0, 0, tzinfo=UTC)


async def _nosleep(_s: float) -> None:
    return None


class Harness:
    def __init__(self, *, shop_enabled: bool = True) -> None:
        cfg = Config.load(GAME_CONFIG)
        cfg.shop = replace(cfg.shop, enabled=shop_enabled)
        self.cfg = cfg
        self.store = MemoryStore()
        self.sink = RecordingSink()
        self.arena = Arena(
            cfg, self.store, self.sink, rng=random.Random(1), sleep=_nosleep, now=_fixed_now
        )
        self.signer = SessionSigner(SECRET)
        self.oauth = TwitchOAuth("cid", "csec", "http://testserver")
        self.deps = WebDeps(
            cfg=cfg, store=self.store, arena=self.arena, sink=self.sink,
            signer=self.signer, oauth=self.oauth,
        )
        app = build_app(WebSocketHub())
        attach_web_api(app, self.deps)
        self.app = app
        self.client = TestClient(app)

    def user_with_char(self, login: str = "brian", gold: int = 5000):
        uid = self.store.add_user(login)
        self.store.users[uid]["gold"] = gold
        ch = self.store.create_character(
            user_id=uid, name="Thorak", class_name="barbarian", race="orc",
            stats=dict(STATS), sprite_set="barb_01",
        )
        return uid, ch

    def login(self, uid: int, login: str = "brian") -> None:
        token = self.signer.sign({"uid": uid, "login": login, "name": login.title()})
        self.client.cookies.set("dnd_session", token)

    def tickers(self) -> list[str]:
        return [e["text"] for e in self.sink.of_type("ticker")]


# -- auth / session -----------------------------------------------------------
def test_me_requires_session():
    h = Harness()
    resp = h.client.get("/api/me")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthenticated"


def test_me_returns_user_and_gold():
    h = Harness()
    uid, _ = h.user_with_char()
    h.login(uid)
    body = h.client.get("/api/me").json()
    assert body["user"]["login"] == "brian"
    assert body["gold"] == 5000


def test_oauth_login_and_callback_register_user(monkeypatch):
    h = Harness()

    async def fake_exchange(code: str):
        assert code == "authcode"
        return "9001", "brian", "Brian"

    monkeypatch.setattr(h.oauth, "exchange", fake_exchange)
    login_resp = h.client.get(
        "/api/auth/login", params={"next": "/roster"}, follow_redirects=False
    )
    assert login_resp.status_code == 302
    location = login_resp.headers["location"]
    assert location.startswith("https://id.twitch.tv/oauth2/authorize")
    state = location.split("state=")[1].split("&")[0]

    cb = h.client.get(
        "/api/auth/callback", params={"code": "authcode", "state": state},
        follow_redirects=False,
    )
    assert cb.status_code == 302
    assert cb.headers["location"] == "/roster"
    # The user is registered under (twitch, 9001) — rule #4 — and the session works.
    me = h.client.get("/api/me").json()
    assert me["user"]["login"] == "brian"
    assert any(
        u["platform"] == "twitch" and u["platform_user_id"] == "9001"
        for u in h.store.users.values()
    )


def test_oauth_callback_rejects_bad_state():
    h = Harness()
    resp = h.client.get(
        "/api/auth/callback", params={"code": "x", "state": "forged"},
        follow_redirects=False,
    )
    assert resp.status_code == 400


def test_login_unconfigured_is_503():
    h = Harness()
    h.deps.oauth = TwitchOAuth("", "", "")
    # Re-fetch through the same routes (deps captured by closure — swap fields).
    h.oauth.client_id = ""
    h.oauth.client_secret = ""
    h.oauth.base_url = ""
    resp = h.client.get("/api/auth/login", follow_redirects=False)
    assert resp.status_code == 503


def test_logout_clears_cookie():
    h = Harness()
    uid, _ = h.user_with_char()
    h.login(uid)
    assert h.client.post("/api/auth/logout").json() == {"ok": True}


# -- roster + sheets ------------------------------------------------------------
def test_roster_lists_living_and_retired():
    h = Harness()
    uid, ch = h.user_with_char()
    ch2 = h.store.create_character(
        user_id=uid, name="Vala", class_name="wizard", race="elf",
        stats=dict(STATS), sprite_set="wizard_01",
    )
    asyncio.run(h.store.retire_character(ch2.id))
    h.login(uid)
    body = h.client.get("/api/characters").json()
    assert [c["name"] for c in body["living"]] == ["Thorak"]
    assert [c["name"] for c in body["retired"]] == ["Vala"]
    assert "inventory" in body["living"][0]  # owner view


def test_public_sheet_hides_inventory():
    h = Harness()
    _, ch = h.user_with_char()
    body = h.client.get(f"/api/characters/{ch.id}").json()
    assert body["name"] == "Thorak"
    assert body["is_owner"] is False
    assert "inventory" not in body
    assert h.client.get("/api/characters/9999").status_code == 404


# -- rename ---------------------------------------------------------------------
def test_rename_happy_path_emits_ticker():
    h = Harness()
    uid, ch = h.user_with_char()
    h.login(uid)
    resp = h.client.post(f"/api/characters/{ch.id}/rename", json={"name": "Zed"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Zed"
    assert any("Thorak is now known as Zed (web)" in t for t in h.tickers())


def test_rename_rejects_invalid_names():
    h = Harness()
    uid, ch = h.user_with_char()
    h.login(uid)
    too_long = h.client.post(
        f"/api/characters/{ch.id}/rename", json={"name": "X" * 21}
    )
    assert too_long.status_code == 400
    assert too_long.json()["error"]["code"] == "invalid_name"
    bad_chars = h.client.post(
        f"/api/characters/{ch.id}/rename", json={"name": "Zed!"}
    )
    assert bad_chars.status_code == 400


def test_rename_foreign_character_is_403():
    h = Harness()
    _, ch = h.user_with_char("brian")
    other_uid = h.store.add_user("mallory")
    h.login(other_uid, "mallory")
    resp = h.client.post(f"/api/characters/{ch.id}/rename", json={"name": "Mine"})
    assert resp.status_code == 403
    assert asyncio.run(h.store.get_character(ch.id)).name == "Thorak"


def test_mutations_require_session():
    h = Harness()
    _, ch = h.user_with_char()
    assert h.client.post(
        f"/api/characters/{ch.id}/rename", json={"name": "Zed"}
    ).status_code == 401


# -- retire -----------------------------------------------------------------------
def test_retire_and_busy_guard():
    h = Harness()
    uid, ch = h.user_with_char()
    h.login(uid)
    asyncio.run(h.arena.enqueue(ch.id, uid))
    busy = h.client.post(f"/api/characters/{ch.id}/retire", json={})
    assert busy.status_code == 409
    assert busy.json()["error"]["code"] == "character_busy"

    h.arena._queue.clear()  # dequeue for the test
    ok = h.client.post(f"/api/characters/{ch.id}/retire", json={})
    assert ok.status_code == 200 and ok.json()["ok"] is True
    again = h.client.post(f"/api/characters/{ch.id}/retire", json={})
    assert again.status_code == 400  # already retired


# -- gear -------------------------------------------------------------------------
def test_buy_equip_unequip_roundtrip():
    h = Harness()
    uid, ch = h.user_with_char()
    h.login(uid)

    buy = h.client.post(f"/api/characters/{ch.id}/buy", json={"item_id": "iron_sword"})
    assert buy.status_code == 200
    assert buy.json()["equipment"]["weapon"]["item_id"] == "iron_sword"
    assert buy.json()["gold"] == 4500

    again = h.client.post(f"/api/characters/{ch.id}/buy", json={"item_id": "iron_sword"})
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "already_owned"

    h.client.post(f"/api/characters/{ch.id}/buy", json={"item_id": "steel_sword"})
    uneq = h.client.post(f"/api/characters/{ch.id}/unequip", json={"slot": "weapon"})
    assert uneq.status_code == 200
    assert "weapon" not in uneq.json()["equipment"]
    # Both swords still owned; equip the iron one back.
    eq = h.client.post(f"/api/characters/{ch.id}/equip", json={"item_id": "iron_sword"})
    assert eq.status_code == 200
    assert eq.json()["equipment"]["weapon"]["item_id"] == "iron_sword"


def test_buy_insufficient_and_unknown():
    h = Harness()
    uid, ch = h.user_with_char(gold=10)
    h.login(uid)
    poor = h.client.post(f"/api/characters/{ch.id}/buy", json={"item_id": "iron_sword"})
    assert poor.status_code == 400
    assert poor.json()["error"]["code"] == "insufficient_gold"
    unk = h.client.post(f"/api/characters/{ch.id}/buy", json={"item_id": "bfg9000"})
    assert unk.status_code == 400
    assert unk.json()["error"]["code"] == "unknown_item"


def test_gear_endpoints_respect_shop_flag():
    h = Harness(shop_enabled=False)
    uid, ch = h.user_with_char()
    h.login(uid)
    resp = h.client.post(f"/api/characters/{ch.id}/buy", json={"item_id": "iron_sword"})
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "shop_disabled"


def test_equip_not_owned():
    h = Harness()
    uid, ch = h.user_with_char()
    h.login(uid)
    resp = h.client.post(f"/api/characters/{ch.id}/equip", json={"item_id": "iron_sword"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "not_owned"


# -- rate limit ---------------------------------------------------------------------
def test_mutation_rate_limit():
    h = Harness()
    uid, ch = h.user_with_char()
    h.login(uid)
    for i in range(10):
        assert h.client.post(
            f"/api/characters/{ch.id}/rename", json={"name": f"Name{i}"}
        ).status_code == 200
    resp = h.client.post(f"/api/characters/{ch.id}/rename", json={"name": "Over"})
    assert resp.status_code == 429


# -- public reads ----------------------------------------------------------------
def test_shop_catalog_public():
    h = Harness()
    body = h.client.get("/api/shop").json()
    assert body["enabled"] is True
    ids = [i["item_id"] for i in body["items"]]
    assert "iron_sword" in ids and "plate_armor" in ids


def test_leaderboard_and_hof_public():
    h = Harness()
    season = h.client.get("/api/leaderboard").json()
    assert season["by"] == "damage" and season["rows"] == []
    alltime = h.client.get("/api/leaderboard", params={"scope": "alltime", "by": "wins"})
    assert alltime.json()["scope"] == "alltime"
    assert h.client.get("/api/leaderboard", params={"by": "nope"}).status_code == 400
    assert h.client.get("/api/hof").json()["records"] == []


def test_arena_state_public():
    h = Harness()
    uid, ch = h.user_with_char()
    asyncio.run(h.arena.enqueue(ch.id, uid))
    body = h.client.get("/api/arena").json()
    assert body["phase"] == "idle"  # boots closed by default config
    assert body["is_open"] is False
    assert body["queue"] == [{"character_id": ch.id, "name": "Thorak", "priority": False}]


# -- SPA fallback -------------------------------------------------------------------
def test_spa_fallback_and_api_precedence(tmp_path):
    h = Harness()
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>SPA</html>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("//js", encoding="utf-8")
    mount_spa(h.app, dist)
    client = TestClient(h.app)

    assert "SPA" in client.get("/roster").text            # SPA route -> index.html
    assert client.get("/assets/app.js").text == "//js"    # real file served
    assert "SPA" in client.get("/").text
    assert client.get("/api/definitely-missing").status_code == 404  # API wins
    assert client.get("/healthz").json()["ok"] is True
    assert "SPA" in client.get("/../../etc/passwd").text  # traversal -> index, not a file
