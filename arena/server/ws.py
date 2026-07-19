"""FastAPI WebSocket endpoint for the Godot client (PLAN.md §2, §7).

FastAPI hosts *only* this Godot-facing socket — it is not the chat ingress. The
``WebSocketHub`` is an :class:`~server.events.EventSink`: the arena emits events
and the hub broadcasts them as JSON to every connected renderer. On connect a
client immediately receives a ``sync`` snapshot so it can join mid-round.

A dead/slow client is dropped, never allowed to stall the game (hard rule: Godot
disconnects don't stop the server). Requires ``fastapi`` + ``uvicorn`` (declared
runtime deps); this module is imported only by the app entrypoint.

Remote deployment (README "Remote deployment"): uvicorn stays bound to
127.0.0.1 and an httpd reverse proxy terminates TLS. When ``WS_AUTH_TOKEN`` is
set, the ``/ws`` handshake requires the shared token (Authorization header or
``?token=`` query param) — unauthenticated clients are rejected before accept.
"""

from __future__ import annotations

import json
import logging
import secrets
from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

log = logging.getLogger("dndarena.ws")


class WebSocketHub:
    """Broadcasts arena events to all connected Godot clients."""

    def __init__(self, snapshot_provider: Callable[[], dict[str, Any]] | None = None) -> None:
        self._clients: set[WebSocket] = set()
        self._snapshot = snapshot_provider

    async def emit(self, event: dict[str, Any]) -> None:
        if not self._clients:
            return
        data = json.dumps(event)
        for ws in list(self._clients):
            try:
                await ws.send_text(data)
            except Exception:  # noqa: BLE001 - drop dead clients, never stall the loop
                self._clients.discard(ws)

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._clients.add(ws)
        if self._snapshot is not None:
            try:
                await ws.send_text(json.dumps(self._snapshot()))
            except Exception:  # noqa: BLE001
                self._clients.discard(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._clients.discard(ws)

    def set_snapshot_provider(self, fn: Callable[[], dict[str, Any]]) -> None:
        self._snapshot = fn

    @property
    def client_count(self) -> int:
        return len(self._clients)


def _authorized(ws: WebSocket, auth_token: str | None) -> bool:
    """True when the handshake carries the shared token (or none is required).

    Accepts ``Authorization: Bearer <token>`` (the Godot client's path) or a
    ``?token=`` query param (handy for wscat/browser debugging). Constant-time
    comparison so the token can't be timing-probed."""
    if auth_token is None or auth_token == "":
        return True
    header = ws.headers.get("authorization", "")
    if header.startswith("Bearer ") and secrets.compare_digest(header[7:], auth_token):
        return True
    query = ws.query_params.get("token", "")
    return bool(query) and secrets.compare_digest(query, auth_token)


def build_app(hub: WebSocketHub, auth_token: str | None = None) -> FastAPI:
    app = FastAPI(title="D&D Arena renderer feed")

    @app.get("/healthz")
    async def healthz() -> dict[str, Any]:
        return {"ok": True, "clients": hub.client_count}

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        if not _authorized(ws, auth_token):
            # Closing before accept() rejects the handshake (HTTP 403).
            log.info("rejected unauthenticated websocket client")
            await ws.close(code=1008)
            return
        await hub.connect(ws)
        try:
            # The client is a pure renderer; we don't expect inbound messages,
            # but we must keep receiving to detect disconnects.
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            hub.disconnect(ws)
        except Exception:  # noqa: BLE001
            log.exception("websocket error; dropping client")
            hub.disconnect(ws)

    return app
