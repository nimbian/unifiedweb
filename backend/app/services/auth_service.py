"""Authentication business logic — multi-provider OAuth -> JWT.

The canonical account id is **``users.rwid``** (PLAN §3). Signing in with any of
Discord, Google (the "YouTube" login) or Twitch resolves the provider id to a
``users`` row — or **creates one** if none exists yet — and mints tokens whose
subject is that row's ``rwid``. A row can carry any subset of the three
providers; a Twitch/Google-first account simply has ``did = NULL`` until the user
links Discord.

Flows:
  * **Login**  — exchange the provider ``code`` for a stable account id, resolve
    the owning user or INSERT a new one, and issue tokens on their ``rwid``.
  * **Link**   — while signed in, attach a provider's account id to the current
    user's row (rejected with 409 if that provider account belongs to someone
    else). Discord is now linkable like the others.
  * **Unlink** — clear a linked provider from the current user; refused if it is
    the last connected provider (a row must keep at least one sign-in method).

Tokens: v2 tokens carry ``sub = rwid`` and ``ver = 2`` with ``did`` as an
optional claim. Older **v1** tokens (``sub = did``) are still accepted during the
grace window and resolved to their ``rwid`` on the fly (PLAN §5).

The refresh token is set as an httpOnly cookie by the router; JWTs are
self-contained (no ``sessions`` table).
"""

from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.models import User
from app.repositories.user_repository import UserRepository
from app.schemas.auth import (
    AuthenticatedUser,
    LinkedAccounts,
    Provider,
    ProviderLink,
    TokenResponse,
)

logger = get_logger(__name__)

# Current access/refresh token shape. v1 tokens (no ``ver``, ``sub = did``) issued
# by the previous backend are still accepted during the grace window.
TOKEN_VERSION = 2


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

    def _resolve_user(self, identity: ProviderIdentity) -> User | None:
        if identity.provider == "discord":
            return self.users.get_by_did(int(identity.account_id))
        if identity.provider == "google":
            return self.users.get_by_google_sub(identity.account_id)
        return self.users.get_by_twitch_uid(identity.account_id)

    # ── Login (resolve-or-create) ────────────────────────────────────────────
    async def login_with_provider(
        self, provider: Provider, code: str
    ) -> tuple[TokenResponse, str]:
        """Exchange the code and return (access token response, refresh token).

        All three providers get the same treatment: resolve the owning row, or
        create one on first sign-in (INSERT only — never rewrites an existing row).
        """
        identity = await self._fetch_identity(provider, code)
        user = self._resolve_user(identity)
        if user is None:
            user = self.users.create_from_identity(
                identity.provider, identity.account_id, identity.display
            )
            logger.info("created users row rwid=%s via %s", user.rwid, provider)
        return self._issue_tokens_for(user)

    # ── Token minting ────────────────────────────────────────────────────────
    @staticmethod
    def _provider_list(user: User) -> list[str]:
        """The providers currently connected to a row (order: discord, google, twitch)."""
        providers: list[str] = []
        if user.did is not None:
            providers.append("discord")
        if user.google_sub:
            providers.append("google")
        if user.twitch_uid:
            providers.append("twitch")
        return providers

    def _access_claims(self, user: User) -> dict[str, object]:
        claims: dict[str, object] = {"ver": TOKEN_VERSION}
        if user.name is not None:
            claims["name"] = user.name
        if user.did is not None:
            claims["did"] = str(user.did)
        providers = self._provider_list(user)
        if providers:
            claims["providers"] = providers
        return claims

    def _issue_tokens_for(self, user: User) -> tuple[TokenResponse, str]:
        sub = str(user.rwid)
        access = create_access_token(subject=sub, extra_claims=self._access_claims(user))
        refresh = create_refresh_token(subject=sub, extra_claims={"ver": TOKEN_VERSION})
        response = TokenResponse(
            access_token=access,
            expires_in=settings.access_token_expire_minutes * 60,
        )
        return response, refresh

    # ── Link / unlink (keyed on rwid) ────────────────────────────────────────
    def _conflict_message(self, provider: Provider) -> str:
        if provider == "discord":
            return (
                "That Discord account already has a Satchemon profile. Sign in with "
                "Discord instead, then link Twitch/Google from there — or contact an "
                "admin to merge the accounts."
            )
        return (
            f"That {provider.title()} account is already linked to another MooreDnD "
            "profile. Sign in with it directly, or contact an admin to merge the accounts."
        )

    async def link_provider(
        self, provider: Provider, code: str, current_rwid: int
    ) -> LinkedAccounts:
        me = self.users.get_by_rwid(current_rwid)
        if me is None:
            raise AuthError("Your account is not registered.")

        identity = await self._fetch_identity(provider, code)
        existing = self._resolve_user(identity)
        if existing is not None and existing.rwid != me.rwid:
            raise AuthConflict(self._conflict_message(provider))

        if provider == "discord":
            self.users.set_discord_link(me.rwid, int(identity.account_id))
            # Give a name-less (web-first) row a display name from Discord.
            if me.name is None and identity.display:
                self.users.set_name(me.rwid, identity.display)
        elif provider == "google":
            self.users.set_google_link(me.rwid, identity.account_id, identity.display)
        else:
            self.users.set_twitch_link(me.rwid, identity.account_id, identity.display)
        return self.linked_accounts(current_rwid)

    def unlink_provider(self, provider: Provider, current_rwid: int) -> LinkedAccounts:
        me = self.users.get_by_rwid(current_rwid)
        if me is None:
            raise AuthError("Your account is not registered.")

        connected = set(self._provider_list(me))
        if provider in connected and len(connected) == 1:
            raise AuthError(
                "You must keep at least one sign-in method connected. Link another "
                "provider before removing this one."
            )

        if provider == "discord":
            self.users.set_discord_link(me.rwid, None)
        elif provider == "google":
            self.users.set_google_link(me.rwid, None, None)
        else:
            self.users.set_twitch_link(me.rwid, None, None)
        return self.linked_accounts(current_rwid)

    def linked_accounts(self, current_rwid: int) -> LinkedAccounts:
        me = self.users.get_by_rwid(current_rwid)
        discord_linked = bool(me and me.did is not None)
        return LinkedAccounts(
            discord=ProviderLink(
                linked=discord_linked,
                handle=me.name if (me and discord_linked) else None,
            ),
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
    def _user_from_refresh(self, payload: dict) -> User | None:
        if payload.get("ver") == TOKEN_VERSION:
            return self.users.get_by_rwid(int(payload["sub"]))
        # v1 refresh cookie: sub is the Discord id — resolve its rwid on the fly.
        try:
            did = int(payload["sub"])
        except (TypeError, ValueError):
            return None
        return self.users.get_by_did(did)

    def refresh(self, refresh_token: str) -> TokenResponse:
        payload = decode_token(refresh_token, expected_type="refresh")
        user = self._user_from_refresh(payload)
        if user is None:
            raise AuthError("Your session could not be refreshed; please sign in again.")
        access = create_access_token(
            subject=str(user.rwid), extra_claims=self._access_claims(user)
        )
        return TokenResponse(
            access_token=access,
            expires_in=settings.access_token_expire_minutes * 60,
        )

    # ── Identity resolution (used by the auth dependency) ────────────────────
    @staticmethod
    def principal_from_access(token: str) -> AuthenticatedUser:
        payload = decode_token(token, expected_type="access")
        if payload.get("ver") == TOKEN_VERSION:
            # v2: subject is the canonical rwid; did rides as an optional claim.
            return AuthenticatedUser(
                rwid=int(payload["sub"]),
                did=payload.get("did"),
                name=payload.get("name"),
            )
        # v1 grace: subject is the Discord id; rwid (if present) rides as a claim.
        return AuthenticatedUser(
            rwid=payload.get("rwid"),
            did=str(payload["sub"]),
            name=payload.get("name"),
        )
