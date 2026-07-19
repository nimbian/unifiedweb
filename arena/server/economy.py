"""Chat-economy helpers (PLAN.md §6.6).

:class:`Presence` records which chat identities were active during the current
round so the arena can pay each of them the per-round gold stipend. It's fed by
the message router on every inbound line (any message counts as "present in
chat") and drained by the arena at round end. Plain identity tuples cross here —
no platform-library types (hard rule #3)."""

from __future__ import annotations


class Presence:
    """Active-chatter set for the current round. Idempotent per identity (a
    chatter who sends ten messages is still one gold payout)."""

    def __init__(self) -> None:
        # (platform, platform_user_id) -> (login, display_name)
        self._seen: dict[tuple[str, str], tuple[str, str]] = {}

    def seen(self, platform: str, platform_user_id: str, login: str, display_name: str) -> None:
        self._seen[(platform, platform_user_id)] = (login, display_name)

    def drain(self) -> list[tuple[tuple[str, str], tuple[str, str]]]:
        """Return the active identities and reset for the next round."""
        out = list(self._seen.items())
        self._seen.clear()
        return out

    @property
    def active_count(self) -> int:
        return len(self._seen)
