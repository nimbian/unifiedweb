"""Tests for character-name validation and profanity filtering (PLAN.md §6.3)."""

from __future__ import annotations

import pytest

from server.names import MAX_NAME_LEN, InvalidName, validate_name

# Deterministic profanity checker for tests (doesn't depend on better-profanity).
BADWORDS = {"badword", "slur"}


def _checker(name: str) -> bool:
    lowered = name.casefold()
    return any(w in lowered for w in BADWORDS)


def test_accepts_plain_name():
    assert validate_name("Thorak", profanity_check=_checker) == "Thorak"


def test_trims_and_collapses_spaces():
    assert validate_name("  Sir   Reginald  ", profanity_check=_checker) == "Sir Reginald"


def test_rejects_empty():
    with pytest.raises(InvalidName):
        validate_name("   ", profanity_check=_checker)


def test_rejects_too_long():
    with pytest.raises(InvalidName):
        validate_name("x" * (MAX_NAME_LEN + 1), profanity_check=_checker)


@pytest.mark.parametrize("bad", ["Thor@k", "naïve", "emoji😀", "semi;colon", "under_score"])
def test_rejects_disallowed_characters(bad):
    with pytest.raises(InvalidName):
        validate_name(bad, profanity_check=_checker)


def test_rejects_profanity_not_sanitizes():
    with pytest.raises(InvalidName):
        validate_name("badword", profanity_check=_checker)
    with pytest.raises(InvalidName):
        validate_name("a badword here", profanity_check=_checker)


def test_alphanumeric_and_spaces_ok():
    assert validate_name("Level 9 Bob", profanity_check=_checker) == "Level 9 Bob"
