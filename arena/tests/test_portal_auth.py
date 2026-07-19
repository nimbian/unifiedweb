"""Unit tests for the MooreDnD portal-JWT bridge (server/portal_auth.py).

Signs test tokens with an ephemeral RSA key pair (PyJWT[crypto]) and verifies
them with the public half — the same shape the portal produces.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

import pytest

jwt = pytest.importorskip("jwt")
pytest.importorskip("cryptography")

from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402

from server.portal_auth import PortalAuth  # noqa: E402


def _keypair() -> tuple[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    pub = key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return priv, pub


PRIV, PUB = _keypair()


def _access(**overrides: object) -> dict[str, object]:
    claims: dict[str, object] = {
        "sub": "7",
        "type": "access",
        "ver": 2,
        "twitch_uid": "tw-123",
        "twitch_login": "brian",
        "name": "Brian",
    }
    claims.update(overrides)
    return claims


def _token(priv: str, claims: dict[str, object], *, alg: str = "RS256", ttl: int = 900) -> str:
    now = int(time.time())
    return jwt.encode({"iat": now, "exp": now + ttl, **claims}, priv, algorithm=alg)


def test_valid_token_resolves():
    ident = PortalAuth(PUB).verify(_token(PRIV, _access()))
    assert ident is not None
    assert ident.rwid == 7
    assert ident.twitch_uid == "tw-123"
    assert ident.twitch_login == "brian"
    assert ident.name == "Brian"


def test_missing_twitch_uid_rejected():
    claims = _access()
    del claims["twitch_uid"]
    assert PortalAuth(PUB).verify(_token(PRIV, claims)) is None


def test_refresh_type_rejected():
    assert PortalAuth(PUB).verify(_token(PRIV, _access(type="refresh"))) is None


def test_expired_token_rejected():
    assert PortalAuth(PUB).verify(_token(PRIV, _access(), ttl=-10)) is None


def test_wrong_key_rejected():
    _, other_pub = _keypair()
    assert PortalAuth(other_pub).verify(_token(PRIV, _access())) is None


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def test_hs256_forgery_rejected():
    # The classic alg-confusion attack: an attacker who has the PUBLIC key forges
    # an HS256 token using that PEM as the HMAC secret. (PyJWT refuses to *sign*
    # this, so we craft the token by hand as a hostile client would.) PortalAuth
    # pins algorithms=["RS256"], so the HS256 header is rejected outright.
    now = int(time.time())
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body = _b64url(json.dumps({**_access(), "iat": now, "exp": now + 900}).encode())
    signing_input = f"{header}.{body}".encode("ascii")
    sig = _b64url(hmac.new(PUB.encode(), signing_input, hashlib.sha256).digest())
    forged = f"{header}.{body}.{sig}"
    assert PortalAuth(PUB).verify(forged) is None


def test_non_integer_sub_rejected():
    assert PortalAuth(PUB).verify(_token(PRIV, _access(sub="not-a-number"))) is None


def test_garbage_and_empty_rejected():
    auth = PortalAuth(PUB)
    assert auth.verify("") is None
    assert auth.verify("not-a-jwt") is None


def test_unconfigured_is_off():
    auth = PortalAuth("")
    assert not auth.configured
    assert auth.verify(_token(PRIV, _access())) is None
