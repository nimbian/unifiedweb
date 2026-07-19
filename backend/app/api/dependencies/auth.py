"""Authentication & authorization dependencies.

``get_current_user`` enforces a valid access token (replaces ``@login_required``).
``require_self`` is the role-based check: a user may only act on their own
records (replaces the implicit trust in the Flask routes). There is no role
column in the schema, so authorization is ownership-based.
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


def require_self(did: int, user: CurrentUser) -> AuthenticatedUser:
    """Authorize an action on ``did`` only if it belongs to the caller."""
    if str(did) != user.did:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="You can only modify your own collection",
        )
    return user
