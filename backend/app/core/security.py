"""JWT creation/verification.

Replaces Flask-Login's server-side session cookie with stateless JWTs:
  * a short-lived **access** token (sent in the ``Authorization: Bearer`` header)
  * a longer-lived **refresh** token (stored in an httpOnly cookie)

The token ``sub`` claim carries the Discord id (``did``), exactly the value the
old app stored in ``session['user']`` / Flask-Login's ``current_user.id``.
"""

from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from jose import JWTError, jwt

from app.core.config import settings

TokenType = Literal["access", "refresh"]


class TokenError(Exception):
    """Raised when a token is missing, malformed, expired, or of the wrong type."""


def _create_token(
    subject: str,
    token_type: TokenType,
    expires_delta: timedelta,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(subject: str, extra_claims: dict[str, Any] | None = None) -> str:
    return _create_token(
        subject,
        "access",
        timedelta(minutes=settings.access_token_expire_minutes),
        extra_claims,
    )


def create_refresh_token(subject: str) -> str:
    return _create_token(
        subject,
        "refresh",
        timedelta(days=settings.refresh_token_expire_days),
    )


def decode_token(token: str, expected_type: TokenType) -> dict[str, Any]:
    """Decode and validate a token, enforcing its declared type. Raises ``TokenError``."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:  # expired, bad signature, malformed
        raise TokenError(str(exc)) from exc

    if payload.get("type") != expected_type:
        raise TokenError(f"expected {expected_type} token, got {payload.get('type')!r}")
    if "sub" not in payload:
        raise TokenError("token missing subject")
    return payload
