"""Player website API (/api/*) + SPA hosting, attached to the existing FastAPI app.

Runs INSIDE the single game-server process and mutates only through the shared
``Store`` — hard rule #2 (only the server writes to Postgres) holds with no
second writer. It is NOT chat ingress (rule #3): web actions call Store/Arena
directly, never the chat command layer. Every mutation emits a ticker on the
overlay via the shared sink (rule #5), suffixed "(web)".

Auth: "Login with Twitch" OAuth (authorization-code, EMPTY scope — identity
only). The callback maps the Twitch user onto the game's ``(platform='twitch',
platform_user_id)`` key via the existing ``register_user`` upsert (rule #4) and
issues a signed ``dnd_session`` cookie (see websession.py). Twitch tokens are
discarded immediately — never stored.

Concurrency: rename and gear changes while that character is mid-round are safe
(the round holds detached copies snapshotted at roster lock); retire is the one
guarded mutation (409 while queued/fighting), mirrored by chat !retire.
"""

from __future__ import annotations

import logging
import secrets
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from . import events, names
from .arena import Arena
from .config import Config, ShopItem
from .models import Character
from .portal_auth import PortalAuth
from .store import SHOP_INSUFFICIENT, SHOP_OWNED, Store, utcnow
from .websession import SessionSigner

log = logging.getLogger("dndarena.webapi")

SESSION_COOKIE = "dnd_session"
STATE_COOKIE = "dnd_oauth_state"
STATE_MAX_AGE_S = 600
GEAR_SLOTS = ("weapon", "armor", "trinket")
MUTATIONS_PER_MINUTE = 10

TWITCH_AUTHORIZE = "https://id.twitch.tv/oauth2/authorize"
TWITCH_TOKEN = "https://id.twitch.tv/oauth2/token"  # noqa: S105 - URL, not a secret
TWITCH_USERS = "https://api.twitch.tv/helix/users"
TWITCH_VALIDATE = "https://id.twitch.tv/oauth2/validate"


class OAuthError(Exception):
    """Twitch-side failure during the OAuth roundtrip (details logged, not echoed)."""


class TwitchOAuth:
    """Authorization-code flow against the existing Twitch app registration."""

    def __init__(self, client_id: str, client_secret: str, base_url: str) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = base_url.rstrip("/")

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret and self.base_url)

    @property
    def redirect_uri(self) -> str:
        return f"{self.base_url}/api/auth/callback"

    def authorize_url(self, state: str) -> str:
        return TWITCH_AUTHORIZE + "?" + urlencode(
            {
                "response_type": "code",
                "client_id": self.client_id,
                "redirect_uri": self.redirect_uri,
                "scope": "",  # identity only
                "state": state,
            }
        )

    async def exchange(self, code: str) -> tuple[str, str, str]:
        """Exchange the auth code; returns ``(twitch_user_id, login, display_name)``.

        The access token is used once (identity lookup) and discarded."""
        import httpx  # runtime dep; imported here so the module loads without it

        async with httpx.AsyncClient(timeout=10.0) as client:
            token_resp = await client.post(
                TWITCH_TOKEN,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": self.redirect_uri,
                },
            )
            if token_resp.status_code != 200:
                log.warning("twitch token exchange failed: %s %s",
                            token_resp.status_code, token_resp.text[:200])
                raise OAuthError("token exchange failed")
            access_token = token_resp.json().get("access_token", "")
            if not access_token:
                raise OAuthError("no access token in response")

            users_resp = await client.get(
                TWITCH_USERS,
                headers={"Authorization": f"Bearer {access_token}",
                         "Client-Id": self.client_id},
            )
            if users_resp.status_code == 200 and users_resp.json().get("data"):
                u = users_resp.json()["data"][0]
                return str(u["id"]), u.get("login", ""), u.get("display_name") or u.get("login", "")

            # Fallback: validate gives user_id + login with zero scopes too.
            val_resp = await client.get(
                TWITCH_VALIDATE, headers={"Authorization": f"OAuth {access_token}"}
            )
            if val_resp.status_code != 200:
                log.warning("twitch identity lookup failed: helix %s, validate %s",
                            users_resp.status_code, val_resp.status_code)
                raise OAuthError("identity lookup failed")
            v = val_resp.json()
            return str(v["user_id"]), v.get("login", ""), v.get("login", "")


@dataclass
class WebDeps:
    """Everything the web API needs from the running server (single process)."""

    cfg: Config
    store: Store
    arena: Arena
    sink: Any  # EventSink — tickers for every mutation (rule #5)
    signer: SessionSigner
    oauth: TwitchOAuth
    # MooreDnD portal-session bridge (PLAN §8). None/unconfigured = portal auth
    # off; the signed-cookie Twitch flow above is unaffected either way.
    portal: PortalAuth | None = None
    rate: dict[int, deque[float]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _err(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


def _session(deps: WebDeps, request: Request) -> dict[str, Any] | None:
    token = request.cookies.get(SESSION_COOKIE, "")
    return deps.signer.verify(token) if token else None


def _bearer_token(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth[:7].lower() == "bearer ":
        token = auth[7:].strip()
        return token or None
    return None


async def _portal_session(deps: WebDeps, request: Request) -> dict[str, Any] | None:
    """Resolve a MooreDnD portal session from an ``Authorization: Bearer`` token.

    Verified against the portal's public key; the ``twitch_uid`` claim maps to the
    game's ``(platform='twitch', platform_user_id)`` user via ``register_user``
    (the same upsert the Twitch-login callback uses — rule #4 key, not linking).
    Writes go through ``Store`` (rule #2). Returns a session dict shaped like the
    cookie flow's so downstream ownership checks are unchanged.
    """
    if deps.portal is None or not deps.portal.configured:
        return None
    token = _bearer_token(request)
    if token is None:
        return None
    ident = deps.portal.verify(token)
    if ident is None:
        return None
    login = ident.twitch_login or ""
    display = ident.name or ident.twitch_login or ""
    uid = await deps.store.register_user("twitch", ident.twitch_uid, login, display)
    return {"uid": uid, "login": login, "name": display, "via": "portal"}


async def _resolve_session(deps: WebDeps, request: Request) -> dict[str, Any] | None:
    """The signed cookie first (fast, unchanged), then a portal Bearer token."""
    sess = _session(deps, request)
    if sess is not None:
        return sess
    return await _portal_session(deps, request)


def _cookie_secure(deps: WebDeps) -> bool:
    return deps.oauth.base_url.startswith("https://")


def _origin_ok(deps: WebDeps, request: Request) -> bool:
    """CSRF backstop for mutations: when an Origin header is present it must be
    our own origin (SameSite=Lax already blocks cross-site POST cookies)."""
    origin = request.headers.get("origin")
    if not origin:
        return True
    allowed = {f"{request.url.scheme}://{request.url.netloc}"}
    if deps.oauth.base_url:
        parts = urlsplit(deps.oauth.base_url)
        allowed.add(f"{parts.scheme}://{parts.netloc}")
    return origin.rstrip("/") in allowed


def _rate_limited(deps: WebDeps, uid: int) -> bool:
    now = time.monotonic()
    window = deps.rate.setdefault(uid, deque())
    while window and now - window[0] > 60.0:
        window.popleft()
    if len(window) >= MUTATIONS_PER_MINUTE:
        return True
    window.append(now)
    return False


def _item_json(item: ShopItem) -> dict[str, Any]:
    return {
        "item_id": item.item_id,
        "slot": item.slot,
        "name": item.name,
        "price": item.price,
        "grants": {
            "ap_mult": item.ap_mult,
            "ac_bonus": item.ac_bonus,
            "speed_mult": item.speed_mult,
            "crit_pp": item.crit_pp,
            "loot_pp": item.loot_pp,
        },
    }


async def _char_json(
    deps: WebDeps, ch: Character, *, owner: bool
) -> dict[str, Any]:
    catalog = deps.cfg.shop.items
    equipment = {
        slot: (_item_json(catalog[iid]) if iid in catalog else {"item_id": iid})
        for slot, iid in ch.equipment.items()
    }
    lineage: dict[str, Any] = {"generation": ch.generation, "trained_by": None}
    if ch.trained_by_a and ch.trained_by_b:
        parents = []
        for pid in (ch.trained_by_a, ch.trained_by_b):
            p = await deps.store.get_character(pid)
            parents.append({"id": pid, "name": p.name if p else "?"})
        lineage["trained_by"] = parents
    out: dict[str, Any] = {
        "id": ch.id,
        "name": ch.name,
        "class_name": ch.class_name,
        "race": ch.race,
        "level": ch.level,
        "xp": ch.xp,
        "stats": dict(ch.stats),
        "battles_fought": ch.battles_fought,
        "battles_left": max(0, deps.cfg.round.lifespan_battles - ch.battles_fought),
        "wins": ch.wins,
        "losses": ch.losses,
        "lifetime_damage": ch.lifetime_damage,
        "lifetime_hits": ch.lifetime_hits,
        "lifetime_crits": ch.lifetime_crits,
        "highest_hit": ch.highest_hit,
        "sprite_set": ch.sprite_set,
        "personality": ch.personality,
        "equipment": equipment,
        "lineage": lineage,
        "is_retired": ch.is_retired,
        "retired_at": ch.retired_at.isoformat() if ch.retired_at else None,
        "owner_login": ch.owner_login,
        "owner_platform": ch.owner_platform,
    }
    if owner:
        equipped = set(ch.equipment.values())
        inv = await deps.store.get_inventory(ch.id)
        out["inventory"] = [
            {**_item_json(catalog[iid]), "equipped": iid in equipped}
            for iid in inv
            if iid in catalog
        ]
    return out


async def _ticker(deps: WebDeps, kind: str, text: str) -> None:
    """Overlay ticker for a web mutation (rule #5); chat mirroring not needed —
    the router only mirrors chat-initiated outcomes, the ticker is primary."""
    try:
        await deps.sink.emit(events.ticker(kind, f"{text} (web)", "twitch"))
    except Exception:  # noqa: BLE001 - a dead overlay must never fail a web request
        log.exception("ticker emit failed")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
def attach_web_api(app: FastAPI, deps: WebDeps) -> None:  # noqa: PLR0915 - route table
    # -- auth ---------------------------------------------------------------
    @app.get("/api/auth/login")
    async def auth_login(request: Request, next: str = "/") -> Response:
        if not deps.oauth.configured:
            return _err(503, "login_unconfigured",
                        "Twitch login is not configured (WEB_BASE_URL / client id/secret)")
        state = secrets.token_urlsafe(24)
        # Only same-site relative paths ("/roster"), never absolute URLs.
        dest = next if next.startswith("/") and not next.startswith("//") else "/"
        resp = RedirectResponse(deps.oauth.authorize_url(state), status_code=302)
        resp.set_cookie(
            STATE_COOKIE,
            deps.signer.sign({"state": state, "next": dest}, max_age_s=STATE_MAX_AGE_S),
            max_age=STATE_MAX_AGE_S, httponly=True, samesite="lax",
            secure=_cookie_secure(deps), path="/",
        )
        return resp

    @app.get("/api/auth/callback")
    async def auth_callback(request: Request, code: str = "", state: str = "") -> Response:
        saved = deps.signer.verify(request.cookies.get(STATE_COOKIE, ""))
        if not code or saved is None or not secrets.compare_digest(saved.get("state", ""), state):
            return _err(400, "invalid_state", "login session expired or invalid — try again")
        try:
            twitch_id, login, display_name = await deps.oauth.exchange(code)
        except OAuthError:
            return _err(502, "oauth_failed", "Twitch login failed — try again")
        uid = await deps.store.register_user("twitch", twitch_id, login, display_name)
        resp = RedirectResponse(saved.get("next", "/"), status_code=302)
        resp.set_cookie(
            SESSION_COOKIE,
            deps.signer.sign({"uid": uid, "login": login, "name": display_name}),
            max_age=deps.signer.max_age_s, httponly=True, samesite="lax",
            secure=_cookie_secure(deps), path="/",
        )
        resp.delete_cookie(STATE_COOKIE, path="/")
        return resp

    @app.post("/api/auth/logout")
    async def auth_logout() -> Response:
        resp = JSONResponse({"ok": True})
        resp.delete_cookie(SESSION_COOKIE, path="/")
        return resp

    # -- session reads --------------------------------------------------------
    @app.get("/api/me")
    async def me(request: Request) -> Response:
        sess = await _resolve_session(deps, request)
        if sess is None:
            return _err(401, "unauthenticated", "log in first")
        gold = await deps.store.get_gold(int(sess["uid"]))
        return JSONResponse({
            "user": {"id": sess["uid"], "login": sess.get("login", ""),
                     "display_name": sess.get("name", "")},
            "gold": gold,
        })

    @app.get("/api/characters")
    async def characters(request: Request) -> Response:
        sess = await _resolve_session(deps, request)
        if sess is None:
            return _err(401, "unauthenticated", "log in first")
        uid = int(sess["uid"])
        living = [
            await _char_json(deps, ch, owner=True)
            for ch in await deps.store.living_roster(uid)
        ]
        retired = [
            await _char_json(deps, ch, owner=True)
            for ch in await deps.store.retired_roster(uid)
        ]
        return JSONResponse({"living": living, "retired": retired})

    @app.get("/api/characters/{character_id}")
    async def character_sheet(request: Request, character_id: int) -> Response:
        ch = await deps.store.get_character(character_id)
        if ch is None or ch.is_npc:
            return _err(404, "not_found", "no such character")
        sess = await _resolve_session(deps, request)
        is_owner = sess is not None and ch.user_id == int(sess["uid"])
        data = await _char_json(deps, ch, owner=is_owner)
        data["is_owner"] = is_owner
        return JSONResponse(data)

    # -- mutations ------------------------------------------------------------
    async def _owned_mutation(
        request: Request, character_id: int
    ) -> tuple[dict[str, Any], Character] | Response:
        """Session + ownership + CSRF + rate-limit gauntlet for every mutation."""
        sess = await _resolve_session(deps, request)
        if sess is None:
            return _err(401, "unauthenticated", "log in first")
        if not _origin_ok(deps, request):
            return _err(403, "forbidden", "cross-origin request rejected")
        ch = await deps.store.get_character(character_id)
        if ch is None or ch.is_npc:
            return _err(404, "not_found", "no such character")
        if ch.user_id != int(sess["uid"]):
            return _err(403, "forbidden", "not your character")
        if _rate_limited(deps, int(sess["uid"])):
            return _err(429, "rate_limited", "too many changes — slow down")
        return sess, ch

    async def _json_body(request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            return {}
        return body if isinstance(body, dict) else {}

    @app.post("/api/characters/{character_id}/rename")
    async def rename(request: Request, character_id: int) -> Response:
        gate = await _owned_mutation(request, character_id)
        if isinstance(gate, Response):
            return gate
        _, ch = gate
        if ch.is_retired:
            return _err(400, "invalid_request", "retired characters can't be renamed")
        raw = str((await _json_body(request)).get("name", ""))
        try:
            new_name = names.validate_name(raw)
        except names.InvalidName as e:
            return _err(400, "invalid_name", str(e))
        old = ch.name
        await deps.store.rename_character(ch.id, new_name)
        await _ticker(deps, "info", f"{old} is now known as {new_name}")
        updated = await deps.store.get_character(ch.id)
        assert updated is not None
        return JSONResponse(await _char_json(deps, updated, owner=True))

    @app.post("/api/characters/{character_id}/retire")
    async def retire(request: Request, character_id: int) -> Response:
        gate = await _owned_mutation(request, character_id)
        if isinstance(gate, Response):
            return gate
        _, ch = gate
        if ch.is_retired:
            return _err(400, "invalid_request", "already retired")
        if deps.arena.is_queued(ch.id) or deps.arena.is_fighting(ch.id):
            return _err(409, "character_busy",
                        f"{ch.name} is queued or fighting — finish the round first")
        await deps.store.retire_character(ch.id)
        await _ticker(deps, "retire", f"{ch.name} has retired. Thanks for the memories!")
        updated = await deps.store.get_character(ch.id)
        assert updated is not None
        return JSONResponse({"ok": True, "retired_at":
                             updated.retired_at.isoformat() if updated.retired_at else None})

    async def _gear_state(ch_id: int) -> dict[str, Any]:
        refreshed = await deps.store.get_character(ch_id)
        assert refreshed is not None
        view = await _char_json(deps, refreshed, owner=True)
        return {"equipment": view["equipment"], "inventory": view["inventory"]}

    @app.post("/api/characters/{character_id}/equip")
    async def equip(request: Request, character_id: int) -> Response:
        gate = await _owned_mutation(request, character_id)
        if isinstance(gate, Response):
            return gate
        _, ch = gate
        if not deps.cfg.shop.enabled:
            return _err(409, "shop_disabled", "the shop isn't open yet")
        item_id = str((await _json_body(request)).get("item_id", ""))
        item = deps.cfg.shop.items.get(item_id)
        if item is None:
            return _err(400, "unknown_item", f"no shop item '{item_id}'")
        if not await deps.store.equip_item(ch.id, item.slot, item.item_id):
            return _err(400, "not_owned", f"{ch.name} doesn't own {item.name}")
        await _ticker(deps, "info", f"{ch.name} equipped {item.name}")
        return JSONResponse(await _gear_state(ch.id))

    @app.post("/api/characters/{character_id}/unequip")
    async def unequip(request: Request, character_id: int) -> Response:
        gate = await _owned_mutation(request, character_id)
        if isinstance(gate, Response):
            return gate
        _, ch = gate
        if not deps.cfg.shop.enabled:
            return _err(409, "shop_disabled", "the shop isn't open yet")
        slot = str((await _json_body(request)).get("slot", ""))
        if slot not in GEAR_SLOTS:
            return _err(400, "invalid_request", "slot must be weapon|armor|trinket")
        if not await deps.store.unequip_item(ch.id, slot):
            return _err(400, "invalid_request", f"nothing equipped in {slot}")
        await _ticker(deps, "info", f"{ch.name} unequipped their {slot}")
        return JSONResponse(await _gear_state(ch.id))

    @app.post("/api/characters/{character_id}/buy")
    async def buy(request: Request, character_id: int) -> Response:
        gate = await _owned_mutation(request, character_id)
        if isinstance(gate, Response):
            return gate
        sess, ch = gate
        if not deps.cfg.shop.enabled:
            return _err(409, "shop_disabled", "the shop isn't open yet")
        item_id = str((await _json_body(request)).get("item_id", ""))
        item = deps.cfg.shop.items.get(item_id)
        if item is None:
            return _err(400, "unknown_item", f"no shop item '{item_id}'")
        result = await deps.store.buy_item(
            ch.user_id, ch.id, item.slot, item.item_id, item.price
        )
        if result == SHOP_INSUFFICIENT:
            gold = await deps.store.get_gold(int(sess["uid"]))
            return _err(400, "insufficient_gold",
                        f"not enough gold for {item.name} ({item.price:,}g) — you have {gold:,}")
        if result == SHOP_OWNED:
            return _err(409, "already_owned", f"{ch.name} already owns {item.name}")
        await _ticker(deps, "info", f"{ch.name} bought {item.name}")
        state = await _gear_state(ch.id)
        state["gold"] = await deps.store.get_gold(int(sess["uid"]))
        return JSONResponse(state)

    # -- public reads -----------------------------------------------------------
    @app.get("/api/shop")
    async def shop() -> Response:
        items = sorted(deps.cfg.shop.items.values(), key=lambda i: (i.slot, i.price))
        return JSONResponse({
            "enabled": deps.cfg.shop.enabled,
            "items": [_item_json(i) for i in items],
        })

    @app.get("/api/leaderboard")
    async def leaderboard(by: str = "damage", scope: str = "season") -> Response:
        if by not in ("damage", "wins"):
            return _err(400, "invalid_request", "by must be damage|wins")
        if scope == "alltime":
            top = (
                await deps.store.top_by_damage(25) if by == "damage"
                else await deps.store.top_by_wins(25)
            )
            rows = [
                {"name": c.name, "value": c.lifetime_damage if by == "damage" else c.wins}
                for c in top
            ]
            return JSONResponse({"scope": "alltime", "by": by, "rows": rows})
        season_id = await deps.store.ensure_current_season(utcnow())
        rows_ = await deps.store.season_leaderboard(season_id, by, 25)
        return JSONResponse({
            "scope": "season", "season_id": season_id, "by": by,
            "rows": [{"name": r.name, "value": r.value} for r in rows_],
        })

    @app.get("/api/hof")
    async def hof() -> Response:
        records = await deps.store.hall_of_fame()
        return JSONResponse({"records": [
            {
                "record_key": r.record_key,
                "character_id": r.character_id,
                "character_name": r.character_name,
                "value": r.value,
                "achieved_at": r.achieved_at.isoformat() if r.achieved_at else None,
            }
            for r in records
        ]})

    @app.get("/api/arena")
    async def arena_state() -> Response:
        snap = deps.arena.snapshot()
        queue = []
        for item in deps.arena.queue_view():
            ch = await deps.store.get_character(item.character_id)
            queue.append({
                "character_id": item.character_id,
                "name": ch.name if ch else "?",
                "priority": item.priority,
            })
        return JSONResponse({
            "phase": snap.get("phase"),
            "round": snap.get("round"),
            "fighters": snap.get("fighters", []),
            "queue": queue,
            "is_open": deps.arena.is_open,
        })


def mount_spa(app: FastAPI, dist: Path) -> None:
    """Serve the built React app (web/dist). Registered LAST so /healthz, /ws,
    and /api/* keep precedence; unknown paths get index.html (SPA routing)."""
    index = dist / "index.html"
    if not index.is_file():
        log.info("web dist not found at %s — API-only mode (npm run build to enable)", dist)
        return
    assets = dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="spa-assets")
    resolved_dist = dist.resolve()

    @app.get("/{path:path}")
    async def spa(path: str) -> Response:
        if path == "api" or path.startswith("api/"):
            # Unknown API paths must 404 as JSON, never fall into the SPA.
            return _err(404, "not_found", "no such endpoint")
        candidate = (resolved_dist / path).resolve() if path else resolved_dist
        if (
            candidate != resolved_dist
            and candidate.is_relative_to(resolved_dist)  # traversal guard
            and candidate.is_file()
        ):
            return FileResponse(candidate)
        return FileResponse(index)
