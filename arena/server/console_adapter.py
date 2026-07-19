"""Console chat adapter — a stdin-driven :class:`~server.adapters.ChatAdapter`.

A second adapter beyond Twitch, for two reasons: it proves the adapter boundary
is real (any source can feed the game as long as it produces
:class:`~server.adapters.InboundMessage`), and it lets you drive the full
command -> ticker -> overlay path locally with no Twitch creds — type commands in
the terminal and watch them land on the Godot overlay's event ticker.

    python -m server.app --memory --no-twitch --console

Every stdin line is one message from a single dev user (moderator, so mod-only
commands work too). No platform-library types cross this module (hard rule #3).
"""

from __future__ import annotations

import asyncio
import logging
import sys
from collections.abc import Callable
from datetime import UTC, datetime

from .adapters import DispatchFn, InboundMessage

log = logging.getLogger("dndarena.console")


class ConsoleAdapter:
    """Reads commands from a text stream (stdin by default) and dispatches them.
    ``can_send`` is True so command replies and round announcements print to the
    terminal — the overlay ticker remains the primary channel regardless."""

    platform = "console"
    can_send = True

    def __init__(
        self,
        dispatch: DispatchFn,
        *,
        login: str = "dev",
        display_name: str = "Dev",
        is_mod: bool = True,
        out: Callable[[str], None] | None = None,
    ) -> None:
        self._dispatch = dispatch
        self._login = login
        self._display_name = display_name
        self._is_mod = is_mod
        self._out = out or (lambda line: print(line, flush=True))
        self._running = False

    # -- lifecycle ---------------------------------------------------------
    async def run(self) -> None:
        self._running = True
        loop = asyncio.get_running_loop()
        self._out("console adapter ready — type commands like: !create barbarian orc Thorak")
        while self._running:
            # Read stdin off-thread so the event loop keeps running.
            line = await loop.run_in_executor(None, sys.stdin.readline)
            if line == "":  # EOF (piped input exhausted / Ctrl-D)
                break
            await self.dispatch_line(line)

    async def close(self) -> None:
        self._running = False

    async def send(self, message: str) -> None:
        self._out(f"[chat] {message}")

    # -- inbound -----------------------------------------------------------
    async def dispatch_line(self, line: str) -> None:
        """Normalize one input line to an :class:`InboundMessage`, dispatch it,
        and echo any chat-mirror replies. Wrapped so a bad line can never crash
        the adapter or the round loop."""
        text = line.strip()
        if not text:
            return
        msg = InboundMessage(
            platform=self.platform,
            platform_user_id=self._login,
            display_name=self._display_name,
            text=text,
            timestamp=datetime.now(tz=UTC),
            login=self._login,
            is_mod=self._is_mod,
        )
        try:
            replies = await self._dispatch(msg)
        except Exception:
            log.exception("console dispatch failed for %r", text)
            return
        for reply in replies:
            await self.send(reply)
