"""Application entrypoint — wires the single-process game server together.

    python -m server.app                          # full: Postgres + Twitch + renderer WS
    python -m server.app --memory                 # in-memory store, no DB (preview/dev)
    python -m server.app --no-twitch              # arena + renderer WS, no chat
    python -m server.app --memory --no-twitch --console  # drive commands from stdin

One asyncio event loop hosts: the arena round loop, the FastAPI WebSocket feed
for Godot, optional platform chat adapters (Twitch in v1), and a config
hot-reload watcher. The arena emits to a fan-out of the WebSocket hub (renderer)
and the chat announcer; chat ingress flows adapter -> MessageRouter -> commands,
with the router emitting the primary ticker feedback to the same WebSocket hub.

Requires the runtime deps (fastapi/uvicorn/asyncpg/twitchio) for the modes that
use them; ``--memory --no-twitch`` still needs fastapi/uvicorn for the WS feed.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import os
from pathlib import Path

from .adapters import ChatAdapter, MessageRouter
from .announce import ChatAnnouncer
from .arena import Arena
from .config import Config
from .events import FanoutSink
from .ws import WebSocketHub, build_app

log = logging.getLogger("dndarena.app")

CONFIG_RELOAD_INTERVAL_S = 5.0


async def _config_watcher(cfg: Config) -> None:
    while True:
        await asyncio.sleep(CONFIG_RELOAD_INTERVAL_S)
        try:
            if cfg.maybe_reload():
                log.info("game config reloaded from %s", cfg.path)
        except Exception:
            log.exception("config reload failed; keeping previous config")


async def _supervise_adapter(name: str, adapter: ChatAdapter) -> None:
    """Run a chat adapter in isolation: a crash or disconnect is logged and
    contained here — it must never propagate to the round loop or other adapters
    (PLAN.md §6.0, hard rule #3)."""
    try:
        await adapter.run()
    except asyncio.CancelledError:
        raise
    except Exception:
        log.exception("chat adapter %s crashed; round loop and other adapters unaffected", name)


async def _run(args: argparse.Namespace) -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except Exception:
        pass

    cfg = Config.load(args.config)

    # --- store -----------------------------------------------------------
    dsn = os.environ.get("DATABASE_URL")
    store: object
    if args.memory or not dsn:
        from .store import MemoryStore

        store = MemoryStore(starting_gold=cfg.economy.starting_gold)
        log.info("using in-memory store (no persistence)")
    else:
        from .pgstore import PgStore

        store = await PgStore.connect(dsn, starting_gold=cfg.economy.starting_gold)
        log.info("connected to Postgres")

    # --- chat adapters (optional) ---------------------------------------
    # Populated below; the announcer broadcasts to every send-capable adapter so
    # no feature depends on any one platform's chat (the ticker is primary).
    adapters: list[ChatAdapter] = []
    use_twitch = not args.no_twitch and bool(os.environ.get("TWITCH_BOT_OAUTH_TOKEN"))

    async def announce(message: str) -> None:
        delivered = False
        for adapter in adapters:
            if adapter.can_send:
                await adapter.send(message)
                delivered = True
        if not delivered:
            log.info("[chat] %s", message)

    # --- sinks + arena ---------------------------------------------------
    from .economy import Presence

    presence = Presence()  # active chatters -> per-round gold accrual
    hub = WebSocketHub()
    announcer = ChatAnnouncer(announce)
    sink = FanoutSink(hub, announcer)
    arena = Arena(cfg, store, sink, presence=presence)  # type: ignore[arg-type]
    hub.set_snapshot_provider(arena.snapshot)

    # --- command layer + router (shared by all adapters) ----------------
    from .commands import GameCommands

    commands = GameCommands(cfg, store, arena)  # type: ignore[arg-type]
    router = MessageRouter(commands, sink, presence=presence)

    if use_twitch:
        from .twitch_bot import TwitchAdapter

        adapters.append(
            TwitchAdapter(
                router.dispatch,
                channel=os.environ["TWITCH_CHANNEL"],
                bot_id=os.environ.get("TWITCH_BOT_ID", ""),
                client_id=os.environ.get("TWITCH_CLIENT_ID", ""),
                client_secret=os.environ.get("TWITCH_CLIENT_SECRET", ""),
                token=os.environ["TWITCH_BOT_OAUTH_TOKEN"],
                refresh_token=os.environ.get("TWITCH_BOT_REFRESH_TOKEN", ""),
            )
        )

    if args.console:
        from .console_adapter import ConsoleAdapter

        adapters.append(ConsoleAdapter(router.dispatch))
        log.info("console adapter enabled — type commands in this terminal")

    # --- EventSub rewards (optional; needs the broadcaster's user id) -----
    from .rewards import RewardRouter

    reward_router = RewardRouter(cfg, store, sink)  # type: ignore[arg-type]
    eventsub = None
    broadcaster_id = os.environ.get("TWITCH_BROADCASTER_ID", "")
    if use_twitch and broadcaster_id:
        from .eventsub import TwitchEventSubAdapter

        eventsub = TwitchEventSubAdapter(
            reward_router,
            broadcaster_id=broadcaster_id,
            bot_id=os.environ.get("TWITCH_BOT_ID", ""),
            client_id=os.environ.get("TWITCH_CLIENT_ID", ""),
            client_secret=os.environ.get("TWITCH_CLIENT_SECRET", ""),
            token=os.environ["TWITCH_BOT_OAUTH_TOKEN"],
            refresh_token=os.environ.get("TWITCH_BOT_REFRESH_TOKEN", ""),
        )
        log.info("EventSub rewards enabled for broadcaster %s", broadcaster_id)

    # --- web server for the Godot feed ----------------------------------
    import uvicorn

    ws_host = os.environ.get("WS_HOST", "127.0.0.1")
    ws_auth_token = os.environ.get("WS_AUTH_TOKEN") or None
    if ws_auth_token is None and ws_host not in ("127.0.0.1", "::1", "localhost"):
        # Remote deployments should bind loopback behind the reverse proxy AND
        # set a token; binding wide open without one is almost never intended.
        log.warning(
            "WS feed binds %s with no WS_AUTH_TOKEN — anyone who can reach the "
            "port can watch the event stream. Set WS_AUTH_TOKEN (see README "
            "'Remote deployment').",
            ws_host,
        )
    ws_app = build_app(hub, auth_token=ws_auth_token)

    # --- player website: /api + SPA on the same app/process (hard rule #2:
    # the web layer mutates only through this process's Store) ------------
    from pathlib import Path

    from .portal_auth import PortalAuth
    from .webapi import TwitchOAuth, WebDeps, attach_web_api, mount_spa
    from .websession import SessionSigner

    session_secret = os.environ.get("WEB_SESSION_SECRET", "")
    if not session_secret:
        import secrets as _secrets

        session_secret = _secrets.token_urlsafe(48)
        log.warning(
            "WEB_SESSION_SECRET is unset — using an ephemeral secret; "
            "website logins will not survive a restart."
        )
    # MooreDnD portal-session bridge (PLAN §8): verify portal RS256 tokens with the
    # portal's PUBLIC key only. Provide it as a PEM file path (preferred) or inline;
    # unset = portal auth off (the Twitch-cookie flow still works).
    portal_pubkey = os.environ.get("PORTAL_JWT_PUBLIC_KEY", "")
    portal_pubkey_path = os.environ.get("PORTAL_JWT_PUBLIC_KEY_PATH", "")
    if portal_pubkey_path:
        try:
            portal_pubkey = Path(portal_pubkey_path).expanduser().read_text()
        except OSError as exc:
            log.warning("PORTAL_JWT_PUBLIC_KEY_PATH unreadable (%s) — portal auth off", exc)
            portal_pubkey = ""
    web_deps = WebDeps(
        cfg=cfg,
        store=store,
        arena=arena,
        sink=sink,
        signer=SessionSigner(session_secret),
        oauth=TwitchOAuth(
            client_id=os.environ.get("TWITCH_CLIENT_ID", ""),
            client_secret=os.environ.get("TWITCH_CLIENT_SECRET", ""),
            base_url=os.environ.get("WEB_BASE_URL", ""),
        ),
        portal=PortalAuth(portal_pubkey) if portal_pubkey else None,
    )
    attach_web_api(ws_app, web_deps)
    mount_spa(ws_app, Path(os.environ.get("WEB_DIST", "web/dist")))

    server = uvicorn.Server(
        uvicorn.Config(
            ws_app,
            host=ws_host,
            port=int(os.environ.get("WS_PORT", "8765")),
            log_level="warning",
        )
    )

    # --- run everything --------------------------------------------------
    # Core tasks (arena, ws, config watcher) are critical; each chat adapter runs
    # under a supervisor that contains its failures so a dead platform never
    # stops the game.
    tasks = [
        asyncio.create_task(arena.run(), name="arena"),
        asyncio.create_task(server.serve(), name="ws"),
        asyncio.create_task(_config_watcher(cfg), name="config-watcher"),
    ]
    for adapter in adapters:
        tasks.append(
            asyncio.create_task(
                _supervise_adapter(adapter.platform, adapter), name=f"adapter:{adapter.platform}"
            )
        )
    if eventsub is not None:
        tasks.append(
            asyncio.create_task(_supervise_adapter("eventsub", eventsub), name="eventsub")
        )

    log.info("D&D Arena server up (%d tasks, %d chat adapter(s))", len(tasks), len(adapters))
    try:
        await asyncio.gather(*tasks)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        for t in tasks:
            t.cancel()
        with contextlib.suppress(Exception):
            await asyncio.gather(*tasks, return_exceptions=True)
        for adapter in adapters:
            with contextlib.suppress(Exception):
                await adapter.close()
        if eventsub is not None:
            with contextlib.suppress(Exception):
                await eventsub.close()
        if hasattr(store, "close"):
            await store.close()  # type: ignore[attr-defined]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="D&D Arena game server")
    parser.add_argument("--config", type=Path, default=Path("config/game.toml"))
    parser.add_argument("--memory", action="store_true", help="use in-memory store (no DB)")
    parser.add_argument("--no-twitch", action="store_true", help="don't start the chat bot")
    parser.add_argument(
        "--console",
        action="store_true",
        help="read commands from stdin (dev/testing without Twitch)",
    )
    args = parser.parse_args(argv)
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(_run(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
