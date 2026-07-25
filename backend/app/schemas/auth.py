"""Auth-related schemas."""

from typing import Literal

from pydantic import BaseModel, Field

# The identity providers a user can sign in with. Discord is the primary account
# (the token subject); Google (the "YouTube" login) and Twitch can be linked to it.
Provider = Literal["discord", "google", "twitch"]


class OAuthCallbackRequest(BaseModel):
    """Payload from the frontend after a provider redirects back with a code."""

    code: str = Field(..., description="OAuth2 authorization code from the provider.")


class LinkCodeRedeem(BaseModel):
    """Payload to redeem a one-time Discord link code from the bot's ``/link`` (PLAN §6).

    Unlike :class:`OAuthCallbackRequest`, this is a short human-typed code, not an
    OAuth authorization code — the service normalizes it (strip + uppercase).
    """

    code: str = Field(
        ..., min_length=1, max_length=16, description="Short code from the bot's /link command."
    )


class TokenResponse(BaseModel):
    """Access token returned to the SPA. The refresh token travels in an httpOnly cookie."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., description="Access-token lifetime in seconds.")


class AuthenticatedUser(BaseModel):
    """The identity resolved from a valid access token (the request principal).

    ``rwid`` is the canonical account id (the v2 token subject). ``did`` is now
    optional — a Twitch/Google-first user who has not linked Discord has no did.
    """

    rwid: int | None = Field(default=None, description="Canonical users.rwid (v2 token subject).")
    did: str | None = Field(default=None, description="Discord user id, if the account has one.")
    name: str | None = None
    is_admin: bool = Field(default=False, description="Whether this user may use admin tools.")


class ProviderLink(BaseModel):
    """Whether one provider is linked to the current account, and its display handle."""

    linked: bool
    handle: str | None = None


class LinkedAccounts(BaseModel):
    """The current user's connected sign-in providers."""

    discord: ProviderLink
    google: ProviderLink
    twitch: ProviderLink
