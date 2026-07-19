"""Turns the arena's event stream into compact chat announcements.

This is the game *announcing itself* in chat (round open / lineup / winner) —
the counterpart to players' commands. It's an ``EventSink`` so it plugs into the
arena's fan-out alongside the Godot WebSocket, and it's pure (a ``send``
callback is injected) so it's unit-tested without Twitch.

Every message is <= 1 line (hard rule #5).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

SendFn = Callable[[str], Awaitable[None]]
_MAX_NAMED = 5  # cap how many players we name in one line


class ChatAnnouncer:
    def __init__(self, send: SendFn) -> None:
        self._send = send

    async def emit(self, event: dict[str, Any]) -> None:
        kind = event.get("type")
        if kind == "countdown":
            await self._on_countdown(event)
        elif kind == "round_start":
            await self._on_round_start(event)
        elif kind == "round_end":
            await self._on_round_end(event)

    async def _on_countdown(self, event: dict[str, Any]) -> None:
        # Announce once, at the top of intermission, that the queue is open.
        if event.get("phase") == "intermission" and event.get("seconds_left") == 1:
            await self._send(
                "Arena is open! Type !enter to send your character into the next round."
            )

    async def _on_round_start(self, event: dict[str, Any]) -> None:
        players = [f["name"] for f in event.get("fighters", []) if not f.get("is_npc")]
        if players:
            shown = ", ".join(players[:_MAX_NAMED])
            extra = f" +{len(players) - _MAX_NAMED} more" if len(players) > _MAX_NAMED else ""
            roster = f"{shown}{extra}"
        else:
            roster = "a field of house challengers"
        await self._send(
            f"Round {event.get('round_id')} begins! In the arena: {roster}. Fight!"
        )

    async def _on_round_end(self, event: dict[str, Any]) -> None:
        standings = sorted(event.get("standings", []), key=lambda s: s.get("placement", 99))
        if not standings:
            return
        top = standings[:3]
        podium = " ".join(
            f"{s['placement']}) {s['name']} ({s['total']:,})" for s in top
        )
        winner = standings[0]
        await self._send(
            f"Winner: {winner['name']} with {winner['total']:,} damage! Top 3: {podium}"
        )
