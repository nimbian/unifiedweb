"""Unit tests for JWT creation/verification and the legacy slug encoding."""

import pytest

from app.core.security import (
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.services.encoding import name_to_slug, slug_to_name


def test_access_token_roundtrip():
    token = create_access_token("12345", extra_claims={"name": "Bob"})
    payload = decode_token(token, expected_type="access")
    assert payload["sub"] == "12345"
    assert payload["name"] == "Bob"


def test_wrong_token_type_rejected():
    refresh = create_refresh_token("12345")
    with pytest.raises(TokenError):
        decode_token(refresh, expected_type="access")


def test_garbage_token_rejected():
    with pytest.raises(TokenError):
        decode_token("not-a-jwt", expected_type="access")


@pytest.mark.parametrize(
    "name,slug",
    [
        ("Full Collection", "Full_Collection"),
        ("Wizard's Tower", "Wizard8s_Tower"),
        ("Who?", "Who9"),
    ],
)
def test_slug_encoding_roundtrip(name, slug):
    assert name_to_slug(name) == slug
    assert slug_to_name(slug) == name
