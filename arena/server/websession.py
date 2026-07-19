"""Signed session tokens for the player website (stdlib-only, no JWT dep).

Format: ``b64url(json(payload + iat/exp)) + "." + b64url(hmac_sha256(secret, body))``.
The payload is readable by the client (it's not encrypted — never put secrets in
it), but any tampering breaks the HMAC. Used for the ``dnd_session`` cookie
(who you are) and the short-lived ``dnd_oauth_state`` cookie (CSRF state for
the Twitch OAuth roundtrip). Logout is client-side cookie deletion; rotating
the secret invalidates every outstanding session (the kill switch).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

DEFAULT_MAX_AGE_S = 30 * 86400  # 30 days


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


class SessionSigner:
    """Signs and verifies small JSON payloads with HMAC-SHA256."""

    def __init__(self, secret: str, *, max_age_s: int = DEFAULT_MAX_AGE_S) -> None:
        if not secret:
            raise ValueError("session secret must be non-empty")
        self._key = secret.encode("utf-8")
        self.max_age_s = max_age_s

    def _mac(self, body: str) -> str:
        return _b64(hmac.new(self._key, body.encode("ascii"), hashlib.sha256).digest())

    def sign(self, payload: dict[str, Any], *, max_age_s: int | None = None) -> str:
        now = int(time.time())
        full = dict(payload)
        full["iat"] = now
        full["exp"] = now + (max_age_s if max_age_s is not None else self.max_age_s)
        body = _b64(json.dumps(full, separators=(",", ":")).encode("utf-8"))
        return f"{body}.{self._mac(body)}"

    def verify(self, token: str) -> dict[str, Any] | None:
        """The payload if the signature is valid and unexpired, else None."""
        if not token or "." not in token:
            return None
        body, _, mac = token.rpartition(".")
        if not hmac.compare_digest(mac, self._mac(body)):
            return None
        try:
            payload = json.loads(_unb64(body))
        except (ValueError, UnicodeDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        exp = payload.get("exp")
        if not isinstance(exp, int) or exp < int(time.time()):
            return None
        return payload
