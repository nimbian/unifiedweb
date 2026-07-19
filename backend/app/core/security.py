"""JWT creation/verification.

Stateless JWTs (no server-side session store):
  * a short-lived **access** token (sent in the ``Authorization: Bearer`` header)
  * a longer-lived **refresh** token (stored in an httpOnly cookie)

Signing uses **RS256** by default (PLAN §5): the portal signs with the RSA
private key and verifies with the public key, so in Phase 2 the arena server can
verify with the public key alone. An HS* algorithm is still supported (symmetric
``jwt_secret``) for simple dev setups.

Token subject: v2 tokens carry ``sub = users.rwid``; the ``did`` travels as an
optional claim. Older **v1** tokens (``sub = did``) issued by the previous
backend still *verify* during the grace window when ``jwt_legacy_secret`` is set
— the subject-shape difference is interpreted by the auth service, not here.
"""

from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from jose import JWTError, jwt

from app.core.config import settings

TokenType = Literal["access", "refresh"]


class TokenError(Exception):
    """Raised when a token is missing, malformed, expired, or of the wrong type."""


@lru_cache(maxsize=8)
def _read_pem(path: str, inline: str, kind: str) -> str:
    """Resolve a PEM key from a file path (preferred) or an inline value.

    Cached on the (path, inline) pair — settings are stable for the process, so a
    prod backend reads each key file once rather than on every token operation.
    ``\\n`` escapes in an inline value are unescaped so a single-line ``.env``
    entry works.
    """
    if path:
        try:
            return Path(path).expanduser().read_text()
        except OSError as exc:
            raise TokenError(f"cannot read JWT {kind} key at {path!r}: {exc}") from exc
    if inline:
        return inline.replace("\\n", "\n")
    raise TokenError(
        f"no JWT {kind} key configured — set JWT_{kind.upper()}_KEY_PATH "
        f"(or JWT_{kind.upper()}_KEY) in the environment"
    )


def _signing_key_alg() -> tuple[str, str]:
    """(key, algorithm) used to SIGN new tokens."""
    alg = settings.jwt_algorithm
    if alg.startswith("HS"):
        if not settings.jwt_secret:
            raise TokenError("jwt_algorithm is HS* but JWT_SECRET is empty")
        return settings.jwt_secret, alg
    return _read_pem(settings.jwt_private_key_path, settings.jwt_private_key, "private"), alg


def _verification_candidates() -> list[tuple[str, str]]:
    """(key, algorithm) pairs to try when verifying — primary first, then the
    optional v1 legacy-grace secret. Each attempt pins a single algorithm to a
    matching key type, so there is no alg-confusion surface."""
    alg = settings.jwt_algorithm
    if alg.startswith("HS"):
        primary = (settings.jwt_secret, alg)
    else:
        primary = (_read_pem(settings.jwt_public_key_path, settings.jwt_public_key, "public"), alg)
    candidates = [primary]
    if settings.jwt_legacy_secret:
        candidates.append((settings.jwt_legacy_secret, settings.jwt_legacy_algorithm))
    return candidates


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
    key, alg = _signing_key_alg()
    return jwt.encode(payload, key, algorithm=alg)


def create_access_token(subject: str, extra_claims: dict[str, Any] | None = None) -> str:
    return _create_token(
        subject,
        "access",
        timedelta(minutes=settings.access_token_expire_minutes),
        extra_claims,
    )


def create_refresh_token(subject: str, extra_claims: dict[str, Any] | None = None) -> str:
    return _create_token(
        subject,
        "refresh",
        timedelta(days=settings.refresh_token_expire_days),
        extra_claims,
    )


def decode_token(token: str, expected_type: TokenType) -> dict[str, Any]:
    """Decode and validate a token, enforcing its declared type. Raises ``TokenError``.

    Tries the primary verification key first, then the legacy-grace secret (if
    configured), so tokens minted by the previous backend keep working until the
    refresh window drains.
    """
    payload: dict[str, Any] | None = None
    last_error: Exception | None = None
    for key, alg in _verification_candidates():
        try:
            payload = jwt.decode(token, key, algorithms=[alg])
            break
        except JWTError as exc:  # expired, bad signature, malformed
            last_error = exc
    if payload is None:
        raise TokenError(str(last_error) if last_error else "token verification failed")

    if payload.get("type") != expected_type:
        raise TokenError(f"expected {expected_type} token, got {payload.get('type')!r}")
    if "sub" not in payload:
        raise TokenError("token missing subject")
    return payload
