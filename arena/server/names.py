"""Character-name validation and profanity filtering (PLAN.md §6.3).

Names render on stream, so this is a Twitch-TOS concern: names must be <= 20
chars, alphanumeric + spaces only, and pass a profanity filter. **Reject, don't
sanitize** — a name that fails is refused, never silently cleaned.

The profanity check prefers the maintained ``better-profanity`` wordlist if it
is installed; otherwise it falls back to a small built-in blocklist so the game
(and its tests) still run without the optional dependency. A checker can also be
injected (used by tests for determinism).
"""

from __future__ import annotations

import re
from collections.abc import Callable

_ALLOWED = re.compile(r"^[A-Za-z0-9 ]+$")
_MULTISPACE = re.compile(r"\s{2,}")
MAX_NAME_LEN = 20

# Minimal fallback list for when better-profanity isn't installed. Not
# exhaustive — the real filter is the wordlist library; this just avoids the
# most obvious cases in a dependency-free environment.
_FALLBACK_WORDS = frozenset(
    {"fuck", "shit", "bitch", "cunt", "nigger", "nigga", "faggot", "retard", "rape", "nazi"}
)


class InvalidName(ValueError):
    """Raised (with a chat-ready message) when a proposed name is rejected."""


def _fallback_checker(name: str) -> bool:
    lowered = re.sub(r"[^a-z]", "", name.casefold())
    return any(word in lowered for word in _FALLBACK_WORDS)


def _build_default_checker() -> Callable[[str], bool]:
    try:
        from better_profanity import profanity

        profanity.load_censor_words()
        return lambda s: profanity.contains_profanity(s) or _fallback_checker(s)
    except Exception:
        return _fallback_checker


_default_checker: Callable[[str], bool] = _build_default_checker()


def validate_name(raw: str, *, profanity_check: Callable[[str], bool] | None = None) -> str:
    """Return the accepted name or raise :class:`InvalidName`.

    Trims surrounding whitespace and collapses internal runs of spaces, but
    otherwise does not alter the name (no censoring).
    """
    name = _MULTISPACE.sub(" ", raw.strip())
    if not name:
        raise InvalidName("name can't be empty")
    if len(name) > MAX_NAME_LEN:
        raise InvalidName(f"name must be {MAX_NAME_LEN} characters or fewer")
    if not _ALLOWED.match(name):
        raise InvalidName("names may use letters, numbers and spaces only")
    checker = profanity_check or _default_checker
    if checker(name):
        raise InvalidName("that name isn't allowed")
    return name
