"""Platform adapter boundary (PLAN.md §2 rule 4, §6.0) and command dispatch.

Chat ingress is quarantined behind adapters. Each platform (Twitch in v1) has an
adapter that normalizes inbound chat into an :class:`InboundMessage` — the ONLY
type that crosses into game logic. No twitchio (or other platform-library) types
may pass this boundary. Adapters run as isolated tasks: one crashing must never
affect the round loop or the other adapters (wired in ``app.py``).

The :class:`MessageRouter` is the shared bridge every adapter calls: it runs a
normalized message through the (platform-agnostic) command layer, emits a
``ticker`` event for every outcome — the *primary* feedback channel (PLAN.md
§6.1) — and returns the ≤1-line chat mirror strings for adapters that can send.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from . import events

if TYPE_CHECKING:
    from .commands import GameCommands


@dataclass(frozen=True)
class InboundMessage:
    """A chat line normalized by a platform adapter — the adapter boundary
    contract (CLAUDE.md hard rule #3). The core identity tuple is
    ``{platform, platform_user_id, display_name, text, timestamp}``; ``login`` and
    ``is_mod`` are additional *normalized primitives* (plain str/bool, never
    library types) that the command layer needs: ``login`` for @mentions and
    mod-target lookups, ``is_mod`` for mod-only command gating."""

    platform: str
    platform_user_id: str
    display_name: str
    text: str
    timestamp: datetime
    login: str = ""
    is_mod: bool = False


# The dispatch callback an adapter is handed at construction (MessageRouter.dispatch).
DispatchFn = Callable[[InboundMessage], Awaitable[list[str]]]


@runtime_checkable
class ChatAdapter(Protocol):
    """A platform chat adapter. Constructed with a :data:`DispatchFn`; its
    long-lived :meth:`run` connects, normalizes inbound chat to
    :class:`InboundMessage`, and dispatches. ``can_send`` advertises whether the
    platform supports bot replies (Twitch: yes; YouTube: limited; TikTok: no) —
    the overlay ticker is the feedback channel regardless (PLAN.md §6.1)."""

    platform: str
    can_send: bool

    async def run(self) -> None: ...

    async def send(self, text: str) -> None: ...

    async def close(self) -> None: ...


class MessageRouter:
    """Bridges an :class:`InboundMessage` to the command layer, the overlay
    ticker, and the chat mirror. Shared by every adapter so all platforms get
    identical command behavior and identical ticker feedback."""

    def __init__(
        self,
        commands: GameCommands,
        sink: events.EventSink,
        *,
        presence: object | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._commands = commands
        self._sink = sink
        self._presence = presence  # economy.Presence | None (per-round gold accrual)
        self._logger = logger or logging.getLogger("dndarena.router")

    async def dispatch(self, msg: InboundMessage) -> list[str]:
        """Run the command, emit a ticker per outcome (primary feedback), and
        return the ≤1-line chat mirror strings (secondary; sent only where the
        platform supports it). Never raises into the adapter."""
        # Any inbound line counts as "present in chat" for the gold stipend.
        if self._presence is not None:
            self._presence.seen(msg.platform, msg.platform_user_id, msg.login, msg.display_name)
        try:
            outcomes = await self._commands.handle(msg)
        except Exception:  # a bad command must never reach the adapter/loop
            self._logger.exception("command dispatch failed for %r", msg.text)
            return []

        mention = msg.login or msg.display_name
        replies: list[str] = []
        for o in outcomes:
            decorate = o.addressed and bool(mention)
            ticker_text = f"{o.text} (@{mention})" if decorate else o.text
            await self._emit(events.ticker(o.kind, ticker_text, msg.platform))
            replies.append(f"@{mention} {o.text}" if decorate else o.text)
        return replies

    async def _emit(self, event: dict) -> None:
        # The overlay is the primary channel, but a dead renderer must never
        # break command handling — swallow sink failures (PLAN.md §10).
        try:
            await self._sink.emit(event)
        except Exception:
            self._logger.exception("ticker sink raised; dropping event")
