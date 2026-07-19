"""Twitch chat adapter (PLAN.md §6.2) — the v1 platform adapter.

Thin translation layer only: it normalizes twitchio chat messages into
:class:`~server.adapters.InboundMessage` (the ONLY type that crosses into game
logic — hard rule #3), hands them to the injected dispatch callback
(:meth:`~server.adapters.MessageRouter.dispatch`), and ships the returned chat
mirror lines back to the channel. It also exposes :meth:`send` so the round
announcer can post lineups/winners. No game logic and no twitchio types leave
this module.

    !!! INTEGRATION NOTE !!!
    twitchio 3.x is a major rewrite and its exact surface (Bot constructor,
    message event hook, chatter/mod accessors) can shift between releases. All
    such version-specific access is isolated in ``_normalize`` and
    ``_bootstrap`` below — verify those two against the twitchio you install
    (`pip show twitchio`). Everything else is version-agnostic.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from .adapters import DispatchFn, InboundMessage

log = logging.getLogger("dndarena.twitch")


class TwitchAdapter:
    """A :class:`~server.adapters.ChatAdapter` wrapping a twitchio client.
    Constructed by ``app.py`` when Twitch creds exist."""

    platform = "twitch"
    can_send = True  # Twitch supports bot replies; later platforms may not.

    def __init__(
        self,
        dispatch: DispatchFn,
        *,
        channel: str,
        bot_id: str,
        client_id: str,
        client_secret: str,
        token: str,
        refresh_token: str,
    ) -> None:
        self._dispatch = dispatch
        self._channel = channel
        self._creds = {
            "bot_id": bot_id,
            "client_id": client_id,
            "client_secret": client_secret,
            "token": token,
            "refresh_token": refresh_token,
        }
        self._client = None  # set in run()

    # -- lifecycle ---------------------------------------------------------
    async def run(self) -> None:
        self._client = self._bootstrap()
        await self._client.start()

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()

    # -- outbound (used by the round announcer) ----------------------------
    async def send(self, message: str) -> None:
        """Post a single line to the channel. Never raises into the caller."""
        try:
            await self._send_raw(message[:480])  # keep well under Twitch's line limit
        except Exception:
            log.exception("failed to send chat message")

    # -- inbound -----------------------------------------------------------
    async def on_chat_message(self, raw_message: object) -> None:
        """Hook the twitchio message event to this. Wrapped so a bad message can
        never crash the adapter or the round loop."""
        try:
            msg = self._normalize(raw_message)
        except Exception:
            log.exception("could not parse chat message")
            return
        if msg is None or not msg.text:
            return
        replies = await self._dispatch(msg)
        for reply in replies:
            await self.send(reply)

    # ================= version-specific twitchio surface =================
    def _bootstrap(self):
        """Build the twitchio client and register the message hook. ADJUST to the
        installed twitchio version if needed (see the module note)."""
        from twitchio.ext import commands as tio_commands  # imported lazily

        adapter = self

        class _Bot(tio_commands.Bot):
            def __init__(self) -> None:
                super().__init__(
                    client_id=adapter._creds["client_id"],
                    client_secret=adapter._creds["client_secret"],
                    bot_id=adapter._creds["bot_id"],
                    owner_id=adapter._creds["bot_id"],
                    prefix="!",
                )

            async def event_ready(self) -> None:
                log.info("twitch adapter ready in #%s", adapter._channel)

            async def event_message(self, message) -> None:  # noqa: ANN001
                await adapter.on_chat_message(message)

        return _Bot()

    def _normalize(self, message: object) -> InboundMessage | None:
        """Pull a normalized :class:`InboundMessage` out of a twitchio message —
        the adapter boundary. ADJUST accessors to the installed twitchio version
        if needed (see the module note)."""
        chatter = getattr(message, "chatter", None) or getattr(message, "author", None)
        if chatter is None or getattr(message, "echo", False):
            return None  # ignore system/self messages
        text = (getattr(message, "text", "") or getattr(message, "content", "") or "").strip()
        login = str(getattr(chatter, "name", "") or getattr(chatter, "login", ""))
        is_mod = bool(getattr(chatter, "moderator", False) or getattr(chatter, "is_mod", False))
        return InboundMessage(
            platform="twitch",
            platform_user_id=str(getattr(chatter, "id", "")),
            display_name=str(getattr(chatter, "display_name", "") or login),
            text=text,
            timestamp=datetime.now(tz=UTC),
            login=login,
            is_mod=is_mod,
        )

    async def _send_raw(self, message: str) -> None:
        """Send a line to the configured channel via twitchio. ADJUST to the
        installed twitchio version if needed."""
        if self._client is None:
            return
        channel = self._client.get_channel(self._channel)
        await channel.send(message)
