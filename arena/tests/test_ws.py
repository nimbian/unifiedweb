"""WebSocket feed auth tests (README "Remote deployment").

The `/ws` endpoint must reject clients without the shared token whenever
``WS_AUTH_TOKEN`` is configured, and stay open (local dev) when it isn't.
FastAPI's TestClient drives the real handshake path. These tests need the
optional runtime deps (fastapi + httpx); they skip cleanly without them so the
stdlib-only suite stays green.
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402
from starlette.websockets import WebSocketDisconnect  # noqa: E402

from server.ws import WebSocketHub, build_app  # noqa: E402

TOKEN = "sekrit-overlay-token"


def _snapshot() -> dict:
    return {"type": "sync", "phase": "idle", "round": None, "fighters": []}


def _client(auth_token: str | None) -> tuple[TestClient, WebSocketHub]:
    hub = WebSocketHub(snapshot_provider=_snapshot)
    return TestClient(build_app(hub, auth_token=auth_token)), hub


def test_open_without_configured_token():
    client, _ = _client(None)
    with client.websocket_connect("/ws") as ws:
        assert ws.receive_json()["type"] == "sync"  # snapshot on connect


def test_bearer_header_accepted():
    client, _ = _client(TOKEN)
    with client.websocket_connect(
        "/ws", headers={"Authorization": f"Bearer {TOKEN}"}
    ) as ws:
        assert ws.receive_json()["type"] == "sync"


def test_query_param_accepted():
    client, _ = _client(TOKEN)
    with client.websocket_connect(f"/ws?token={TOKEN}") as ws:
        assert ws.receive_json()["type"] == "sync"


def test_missing_token_rejected():
    client, hub = _client(TOKEN)
    with pytest.raises(WebSocketDisconnect), client.websocket_connect("/ws") as ws:
        ws.receive_json()
    assert hub.client_count == 0


def test_wrong_token_rejected():
    client, hub = _client(TOKEN)
    bad_header = {"Authorization": "Bearer nope"}
    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect("/ws", headers=bad_header) as ws,
    ):
        ws.receive_json()
    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect("/ws?token=nope") as ws,
    ):
        ws.receive_json()
    assert hub.client_count == 0


def test_healthz_is_open_regardless_of_token():
    client, _ = _client(TOKEN)
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_broadcast_reaches_authed_client():
    import asyncio

    client, hub = _client(TOKEN)
    with client.websocket_connect(f"/ws?token={TOKEN}") as ws:
        assert ws.receive_json()["type"] == "sync"
        asyncio.run(hub.emit({"type": "ticker", "kind": "info", "text": "hi"}))
        msg = ws.receive_json()
        assert msg["type"] == "ticker" and msg["text"] == "hi"
