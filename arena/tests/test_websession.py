"""Session signer tests (server/websession.py): HMAC roundtrip, tamper
rejection, expiry."""

from __future__ import annotations

import time

import pytest

from server.websession import SessionSigner


def test_sign_verify_roundtrip():
    s = SessionSigner("secret-key")
    token = s.sign({"uid": 7, "login": "brian"})
    payload = s.verify(token)
    assert payload is not None
    assert payload["uid"] == 7 and payload["login"] == "brian"
    assert payload["exp"] > int(time.time())


def test_tampered_token_rejected():
    s = SessionSigner("secret-key")
    token = s.sign({"uid": 7})
    body, _, mac = token.rpartition(".")
    # Flip the payload (uid 7 -> forged body) but keep the old mac.
    forged = s.sign({"uid": 8}).rpartition(".")[0] + "." + mac
    assert s.verify(forged) is None
    assert s.verify(body + ".AAAA") is None
    assert s.verify("garbage") is None
    assert s.verify("") is None


def test_wrong_secret_rejected():
    token = SessionSigner("secret-a").sign({"uid": 1})
    assert SessionSigner("secret-b").verify(token) is None


def test_expired_token_rejected():
    s = SessionSigner("secret-key")
    token = s.sign({"uid": 1}, max_age_s=-5)  # already expired
    assert s.verify(token) is None


def test_empty_secret_rejected():
    with pytest.raises(ValueError):
        SessionSigner("")
