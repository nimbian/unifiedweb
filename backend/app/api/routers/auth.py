"""Auth router — multi-provider OAuth + JWT issuance / refresh / logout / linking.

Discord is the primary account (the token subject). Google (the "YouTube" login)
and Twitch can be linked to it and then used to sign in. The refresh token lives
in an httpOnly cookie; the SPA keeps only the short-lived access token (in memory).

Literal paths (``/refresh``, ``/logout``, ``/me``, ``/links``) are declared before
the parameterized ``/{provider}`` routes so they are not shadowed by them.
"""

import secrets
from typing import Annotated

from fastapi import APIRouter, Cookie, HTTPException, Path, Response, status

from app.api.dependencies.auth import CurrentRwid, CurrentUser
from app.api.dependencies.services import AuthServiceDep
from app.core.config import settings
from app.core.security import TokenError
from app.schemas.auth import (
    AuthenticatedUser,
    LinkCodeRedeem,
    LinkedAccounts,
    OAuthCallbackRequest,
    Provider,
    TokenResponse,
)
from app.services.auth_service import AuthConflict, AuthError

router = APIRouter(prefix="/auth", tags=["auth"])

_PROVIDERS: set[str] = {"discord", "google", "twitch"}
ProviderPath = Annotated[str, Path(description="discord | google | twitch")]


def _provider(provider: str) -> Provider:
    if provider not in _PROVIDERS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Unknown provider: {provider}")
    return provider  # type: ignore[return-value]


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=refresh_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.refresh_token_expire_days * 24 * 3600,
        path=settings.api_prefix + "/auth",
    )


# ── Literal routes (declared first) ──────────────────────────────────────────
@router.post("/refresh", response_model=TokenResponse, summary="Refresh access token")
def refresh(
    service: AuthServiceDep,
    refresh_token: str | None = Cookie(default=None, alias=settings.refresh_cookie_name),
) -> TokenResponse:
    if refresh_token is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Missing refresh token")
    try:
        return service.refresh(refresh_token)
    except TokenError as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, detail=f"Invalid refresh token: {exc}"
        ) from exc
    except AuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


@router.post("/logout", summary="Clear the refresh cookie")
def logout(response: Response) -> dict[str, str]:
    response.delete_cookie(settings.refresh_cookie_name, path=settings.api_prefix + "/auth")
    return {"detail": "logged out"}


@router.get("/me", response_model=AuthenticatedUser, summary="Current principal")
def me(user: CurrentUser) -> AuthenticatedUser:
    return user


@router.get("/links", response_model=LinkedAccounts, summary="Current user's linked providers")
def links(service: AuthServiceDep, rwid: CurrentRwid) -> LinkedAccounts:
    return service.linked_accounts(rwid)


@router.post(
    "/link/redeem", response_model=LinkedAccounts, summary="Redeem a bot /link code"
)
def link_redeem(
    payload: LinkCodeRedeem,
    service: AuthServiceDep,
    rwid: CurrentRwid,
) -> LinkedAccounts:
    """Attach a Discord account to the caller via a one-time code from the bot's
    ``/link`` — the OAuth-free linking path (PLAN §6)."""
    try:
        return service.redeem_link_code(payload.code, rwid)
    except AuthConflict as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except AuthError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


# ── Provider routes ──────────────────────────────────────────────────────────
@router.get("/{provider}/url", summary="Get a provider's authorize URL")
def provider_url(provider: ProviderPath, service: AuthServiceDep) -> dict[str, str]:
    """Return the URL the SPA should redirect the browser to, plus a CSRF state."""
    prov = _provider(provider)
    state = secrets.token_urlsafe(16)
    return {"url": service.authorize_url(prov, state), "state": state}


@router.post("/{provider}", response_model=TokenResponse, summary="Sign in with a provider")
async def provider_login(
    provider: ProviderPath,
    payload: OAuthCallbackRequest,
    response: Response,
    service: AuthServiceDep,
) -> TokenResponse:
    prov = _provider(provider)
    try:
        token_response, refresh_token = await service.login_with_provider(prov, payload.code)
    except AuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    _set_refresh_cookie(response, refresh_token)
    return token_response


@router.post("/{provider}/link", response_model=LinkedAccounts, summary="Link a provider")
async def provider_link(
    provider: ProviderPath,
    payload: OAuthCallbackRequest,
    service: AuthServiceDep,
    rwid: CurrentRwid,
) -> LinkedAccounts:
    prov = _provider(provider)
    try:
        return await service.link_provider(prov, payload.code, rwid)
    except AuthConflict as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except AuthError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.delete("/{provider}/link", response_model=LinkedAccounts, summary="Unlink a provider")
def provider_unlink(
    provider: ProviderPath,
    service: AuthServiceDep,
    rwid: CurrentRwid,
) -> LinkedAccounts:
    prov = _provider(provider)
    try:
        return service.unlink_provider(prov, rwid)
    except AuthError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
