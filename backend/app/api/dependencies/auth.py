"""Authentication & authorization dependencies.

``get_current_user`` enforces a valid access token (replaces ``@login_required``)
and yields the request principal. Two narrowing dependencies build on it:

  * ``CurrentRwid`` — the caller's canonical account id (``users.rwid``). Every
    signed-in user has one; used by the account/link routes, which now key on
    rwid (PLAN §5).
  * ``CurrentDid`` — the caller's Discord id, for the Satchemon ``/me`` routes.
    A Twitch/Google-first user without a linked Discord gets a clean 409 (their
    Satchemon data is empty until they link Discord) instead of a 500.

Authorization is ownership-based (no role column); ``require_self`` compares
``rwid``.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.security import TokenError
from app.schemas.auth import AuthenticatedUser
from app.services.auth_service import AuthService

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> AuthenticatedUser:
    if credentials is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return AuthService.principal_from_access(credentials.credentials)
    except TokenError as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]


def require_account(user: CurrentUser) -> int:
    """The caller's canonical ``users.rwid`` (401/400 if the token has none)."""
    if user.rwid is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Your account is not registered.",
        )
    return user.rwid


CurrentRwid = Annotated[int, Depends(require_account)]


def require_discord_did(user: CurrentUser) -> int:
    """The caller's Discord id for Satchemon routes.

    Satchemon is played through the Discord bot, so a did-less (Twitch/Google-
    first) account has no Satchemon data. Return a clear 409 rather than letting
    ``int(None)`` blow up downstream.
    """
    if user.did is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Link your Discord account to use Satchemon features.",
        )
    return int(user.did)


CurrentDid = Annotated[int, Depends(require_discord_did)]


def require_self(rwid: int, user: CurrentUser) -> AuthenticatedUser:
    """Authorize an action on ``rwid`` only if it belongs to the caller."""
    if user.rwid != rwid:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="You can only modify your own account",
        )
    return user
