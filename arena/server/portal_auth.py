"""Verify MooreDnD portal JWTs (RS256) — the portal-session bridge (PLAN §8).

The MooreDnD portal signs access tokens with its RSA **private** key; the arena
holds only the **public** key, so it can verify a portal session without any
shared database or secret. A valid token carries a ``twitch_uid`` claim (the
Twitch user id the player linked on the portal), which is exactly this game's
``(platform='twitch', platform_user_id)`` key — so a portal session resolves to
the *same* arena user the chat/Twitch-login flow produces (rule #4 stands: we
only resolve which existing twitch user acts, we never link or merge accounts).

This is additive: the existing signed-cookie Twitch-login flow (websession.py)
remains the fallback. If no public key is configured, portal auth is simply off.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import jwt  # PyJWT[crypto] — RS256 verification with the RSA public key

log = logging.getLogger("dndarena.portal_auth")

# The portal issues v2 access tokens (sub = users.rwid, ver = 2). We accept only
# access tokens; refresh tokens never reach the arena.
_ACCESS_TYPE = "access"


@dataclass(frozen=True)
class PortalIdentity:
    """The arena-relevant identity extracted from a verified portal token."""

    rwid: int                    # the portal's canonical account id (audit/log only)
    twitch_uid: str              # (platform='twitch', platform_user_id) — the arena key
    twitch_login: str | None     # display handle, for register_user
    name: str | None             # portal display name


class PortalAuth:
    """Verifies portal RS256 tokens against the portal's public key."""

    def __init__(self, public_key_pem: str, *, algorithms: tuple[str, ...] = ("RS256",)) -> None:
        self._key = public_key_pem or ""
        self._algorithms = list(algorithms)

    @property
    def configured(self) -> bool:
        return bool(self._key)

    def verify(self, token: str) -> PortalIdentity | None:
        """Return the identity if ``token`` is a valid portal access token that
        carries a ``twitch_uid``; otherwise ``None`` (never raises)."""
        if not self._key or not token:
            return None
        try:
            payload = jwt.decode(token, self._key, algorithms=self._algorithms)
        except jwt.PyJWTError as exc:  # bad signature, expired, malformed, wrong alg
            log.debug("portal token rejected: %s", exc)
            return None

        if payload.get("type") != _ACCESS_TYPE:
            return None
        twitch_uid = payload.get("twitch_uid")
        if not twitch_uid:
            # A portal account with no linked Twitch cannot act in the arena.
            return None
        try:
            rwid = int(payload["sub"])
        except (KeyError, TypeError, ValueError):
            return None
        return PortalIdentity(
            rwid=rwid,
            twitch_uid=str(twitch_uid),
            twitch_login=payload.get("twitch_login"),
            name=payload.get("name"),
        )
