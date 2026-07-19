"""Auth-related schemas."""

from typing import Literal

from pydantic import BaseModel, Field

# The identity providers a user can sign in with. Discord is the primary account
# (the token subject); Google (the "YouTube" login) and Twitch can be linked to it.
Provider = Literal["discord", "google", "twitch"]


class OAuthCallbackRequest(BaseModel):
    """Payload from the frontend after a provider redirects back with a code."""

    code: str = Field(..., description="OAuth2 authorization code from the provider.")


class TokenResponse(BaseModel):
    """Access token returned to the SPA. The refresh token travels in an httpOnly cookie."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., description="Access-token lifetime in seconds.")


class AuthenticatedUser(BaseModel):
    """The identity resolved from a valid access token (the request principal)."""

    did: str = Field(..., description="Discord user id (token subject).")
    name: str | None = None
    rwid: int | None = Field(default=None, description="Internal users.rwid, if registered.")


class ProviderLink(BaseModel):
    """Whether one provider is linked to the current account, and its display handle."""

    linked: bool
    handle: str | None = None


class LinkedAccounts(BaseModel):
    """The current user's connected sign-in providers."""

    discord: ProviderLink
    google: ProviderLink
    twitch: ProviderLink
