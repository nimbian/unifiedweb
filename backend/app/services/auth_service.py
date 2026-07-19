"""Authentication business logic — multi-provider OAuth -> JWT.

Every account is anchored on **Discord**: the JWT subject is always the Discord
id (``did``), and all authorization (ownership checks, ``rwid`` resolution, FKs)
keys off it. Because everyone already has a Discord account, signing in with
Google (the "YouTube" login) or Twitch does not need a new identity model — it
just resolves the linked provider id back to the owning user's ``did``.

Flows:
  * **Login**  — exchange the provider ``code`` for a stable account id, resolve
    the owning user, and mint tokens on their ``did``. Discord always works;
    Google/Twitch only after the account has been linked.
  * **Link**   — while signed in, attach a provider's account id to the current
    user's row (rejected if that provider account already belongs to someone else).
  * **Unlink** — clear a linked provider from the current user.

The refresh token is set as an httpOnly cookie by the router. The legacy
``sessions`` table is intentionally not used; JWTs are self-contained.
"""

from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.repositories.user_repository import UserRepository
from app.schemas.auth import (
    AuthenticatedUser,
    LinkedAccounts,
    Provider,
    ProviderLink,
    TokenResponse,
)

logger = get_logger(__name__)


class AuthError(Exception):
    """Raised for any failure in the OAuth exchange or token handling (-> 401/400)."""


class AuthConflict(AuthError):
    """A provider account is already linked to a different user (-> 409)."""


@dataclass(frozen=True)
class ProviderIdentity:
    """The stable identity resolved from a provider after the OAuth exchange."""

    provider: Provider
    account_id: str          # stable id used to match/link (Discord id, Google sub, Twitch id)
    display: str | None      # handle/name for the UI


# Static per-provider OAuth endpoints. Client credentials and redirect URIs are
# read from settings at call time (see ``_creds``).
_ENDPOINTS: dict[Provider, dict[str, str]] = {
    "discord": {
        "authorize": "https://discord.com/api/oauth2/authorize",
        "token": "https://discord.com/api/oauth2/token",
        "userinfo": "https://discord.com/api/users/@me",
        "scope": "identify",
    },
    "google": {
        "authorize": "https://accounts.google.com/o/oauth2/v2/auth",
        "token": "https://oauth2.googleapis.com/token",
        "userinfo": "https://openidconnect.googleapis.com/v1/userinfo",
        "scope": "openid email profile",
    },
    "twitch": {
        "authorize": "https://id.twitch.tv/oauth2/authorize",
        "token": "https://id.twitch.tv/oauth2/token",
        "userinfo": "https://api.twitch.tv/helix/users",
        "scope": "",
    },
}

# Extra provider-specific params on the authorize redirect.
_AUTHORIZE_EXTRA: dict[Provider, dict[str, str]] = {
    "discord": {"prompt": "consent"},
    "google": {"access_type": "online", "prompt": "select_account"},
    "twitch": {},
}


def _creds(provider: Provider) -> tuple[str, str, str]:
    """(client_id, client_secret, redirect_uri) for a provider."""
    if provider == "discord":
        return (settings.discord_client_id, settings.discord_client_secret,
                settings.discord_redirect_uri)
    if provider == "google":
        return (settings.google_client_id, settings.google_client_secret,
                settings.google_redirect_uri)
    if provider == "twitch":
        return (settings.twitch_client_id, settings.twitch_client_secret,
                settings.twitch_redirect_uri)
    raise AuthError(f"Unknown provider: {provider}")


def _parse_identity(provider: Provider, data: dict) -> ProviderIdentity:
    """Turn a provider's userinfo response into a stable ``ProviderIdentity``."""
    if provider == "discord":
        return ProviderIdentity("discord", str(data["id"]),
                                data.get("global_name") or data.get("username"))
    if provider == "google":
        return ProviderIdentity("google", str(data["sub"]),
                                data.get("name") or data.get("email"))
    if provider == "twitch":
        rows = data.get("data") or []
        if not rows:
            raise AuthError("Twitch profile response was empty")
        row = rows[0]
        return ProviderIdentity("twitch", str(row["id"]),
                                row.get("display_name") or row.get("login"))
    raise AuthError(f"Unknown provider: {provider}")


class AuthService:
    def __init__(self, user_repo: UserRepository) -> None:
        self.users = user_repo

    # ── Step 1: authorize URL ────────────────────────────────────────────────
    def authorize_url(self, provider: Provider, state: str) -> str:
        ep = _ENDPOINTS[provider]
        client_id, _, redirect_uri = _creds(provider)
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": ep["scope"],
            "state": state,
            **_AUTHORIZE_EXTRA[provider],
        }
        return f"{ep['authorize']}?{urlencode(params)}"

    # ── Step 3: code -> stable identity ──────────────────────────────────────
    async def _fetch_identity(self, provider: Provider, code: str) -> ProviderIdentity:
        """Exchange the OAuth ``code`` and return the provider's stable identity.

        This is the sole network seam; tests patch it to avoid real HTTP.
        """
        ep = _ENDPOINTS[provider]
        client_id, client_secret, redirect_uri = _creds(provider)
        data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        async with httpx.AsyncClient(timeout=10.0) as client:
            token_resp = await client.post(ep["token"], data=data, headers=headers)
            if token_resp.status_code != 200:
                logger.warning("%s token exchange failed: %s", provider, token_resp.text)
                raise AuthError(f"{provider.title()} token exchange failed")
            access = token_resp.json().get("access_token")

            info_headers = {"Authorization": f"Bearer {access}"}
            if provider == "twitch":
                info_headers["Client-Id"] = client_id
            me_resp = await client.get(ep["userinfo"], headers=info_headers)
            if me_resp.status_code != 200:
                raise AuthError(f"Failed to fetch {provider.title()} profile")
            return _parse_identity(provider, me_resp.json())

    def _resolve_user(self, identity: ProviderIdentity):  # noqa: ANN201 (User | None)
        if identity.provider == "discord":
            return self.users.get_by_did(int(identity.account_id))
        if identity.provider == "google":
            return self.users.get_by_google_sub(identity.account_id)
        return self.users.get_by_twitch_uid(identity.account_id)

    # ── Login ────────────────────────────────────────────────────────────────
    async def login_with_provider(self, provider: Provider, code: str) -> tuple[TokenResponse, str]:
        """Exchange the code and return (access token response, refresh token)."""
        identity = await self._fetch_identity(provider, code)
        user = self._resolve_user(identity)

        if provider == "discord":
            # Discord is the anchor: the token subject is the Discord id itself,
            # whether or not the user is registered in ``users`` (matches legacy).
            name = user.name if user is not None else identity.display
            rwid = user.rwid if user is not None else None
            return self._issue_tokens(identity.account_id, name=name, rwid=rwid)

        if user is None:
            raise AuthError(
                f"No account is linked to that {provider.title()}. "
                "Sign in with Discord and link it under Account first."
            )
        if user.did is None:
            raise AuthError("The linked account has no Discord id to sign in as.")
        return self._issue_tokens(str(user.did), name=user.name, rwid=user.rwid)

    def _issue_tokens(
        self, did: str, name: str | None, rwid: int | None
    ) -> tuple[TokenResponse, str]:
        extra: dict[str, object] = {}
        if name is not None:
            extra["name"] = name
        if rwid is not None:
            extra["rwid"] = rwid
        access = create_access_token(subject=did, extra_claims=extra)
        refresh = create_refresh_token(subject=did)
        response = TokenResponse(
            access_token=access,
            expires_in=settings.access_token_expire_minutes * 60,
        )
        return response, refresh

    # ── Link / unlink ────────────────────────────────────────────────────────
    async def link_provider(self, provider: Provider, code: str, current_did: str) -> LinkedAccounts:
        if provider == "discord":
            raise AuthError("Discord is your primary account and is always connected.")

        me = self.users.get_by_did(int(current_did))
        if me is None:
            raise AuthError("Your account is not registered.")

        identity = await self._fetch_identity(provider, code)
        existing = self._resolve_user(identity)
        if existing is not None and existing.rwid != me.rwid:
            raise AuthConflict(
                f"That {provider.title()} account is already linked to another user."
            )

        if provider == "google":
            self.users.set_google_link(me.rwid, identity.account_id, identity.display)
        else:
            self.users.set_twitch_link(me.rwid, identity.account_id, identity.display)
        return self.linked_accounts(current_did)

    def unlink_provider(self, provider: Provider, current_did: str) -> LinkedAccounts:
        if provider == "discord":
            raise AuthError("You cannot disconnect your primary Discord account.")

        me = self.users.get_by_did(int(current_did))
        if me is None:
            raise AuthError("Your account is not registered.")

        if provider == "google":
            self.users.set_google_link(me.rwid, None, None)
        else:
            self.users.set_twitch_link(me.rwid, None, None)
        return self.linked_accounts(current_did)

    def linked_accounts(self, current_did: str) -> LinkedAccounts:
        me = self.users.get_by_did(int(current_did))
        return LinkedAccounts(
            discord=ProviderLink(linked=True, handle=me.name if me else None),
            google=ProviderLink(
                linked=bool(me and me.google_sub),
                handle=me.google_name if me else None,
            ),
            twitch=ProviderLink(
                linked=bool(me and me.twitch_uid),
                handle=me.twitch_login if me else None,
            ),
        )

    # ── Token refresh ────────────────────────────────────────────────────────
    def refresh(self, refresh_token: str) -> TokenResponse:
        payload = decode_token(refresh_token, expected_type="refresh")
        did = payload["sub"]
        user = self.users.get_by_did(int(did))
        extra: dict[str, object] = {}
        if user is not None:
            extra = {"name": user.name, "rwid": user.rwid}
        access = create_access_token(subject=did, extra_claims=extra)
        return TokenResponse(
            access_token=access,
            expires_in=settings.access_token_expire_minutes * 60,
        )

    # ── Identity resolution (used by the auth dependency) ────────────────────
    @staticmethod
    def principal_from_access(token: str) -> AuthenticatedUser:
        payload = decode_token(token, expected_type="access")
        return AuthenticatedUser(
            did=payload["sub"],
            name=payload.get("name"),
            rwid=payload.get("rwid"),
        )
