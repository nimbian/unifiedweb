"""Twitch EventSub adapter (PLAN.md §6.2) — the reward I/O edge.

Subscribes to channel-point redemptions and support events (subs/bits) over
twitchio's EventSub, normalizes each notification to a
:class:`~server.rewards.RedemptionEvent` / :class:`~server.rewards.SupportEvent`
(the ONLY types that cross into game logic — hard rule #3), and hands them to the
tested, idempotent :class:`~server.rewards.RewardRouter`. Runs as an isolated
task (hard rule: a dead adapter never stops the round loop).

    !!! INTEGRATION NOTE !!!
    twitchio 3.x EventSub (transport, subscription payloads, event-callback
    names) is version-specific and CANNOT be exercised by the unit tests — the
    reward *logic* is tested via RewardRouter; only this thin edge needs live
    verification. All version-specific access is isolated in ``_bootstrap`` and
    the ``_normalize_*`` methods below — verify them against your installed
    twitchio (`pip show twitchio`) and your channel's reward titles. If EventSub
    can't be set up, ``run`` logs and returns; the app keeps running without it.
"""

from __future__ import annotations

import logging

from .rewards import RedemptionEvent, RewardRouter, SupportEvent

log = logging.getLogger("dndarena.eventsub")

PLATFORM = "twitch"


class TwitchEventSubAdapter:
    """Wraps a twitchio EventSub client. Constructed by ``app.py`` when Twitch
    creds + a broadcaster id are present."""

    platform = PLATFORM

    def __init__(
        self,
        rewards: RewardRouter,
        *,
        broadcaster_id: str,
        bot_id: str,
        client_id: str,
        client_secret: str,
        token: str,
        refresh_token: str,
    ) -> None:
        self._rewards = rewards
        self._broadcaster_id = broadcaster_id
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
        try:
            self._client = self._bootstrap()
        except Exception:
            log.exception("EventSub bootstrap failed; rewards disabled (verify twitchio surface)")
            return
        await self._client.start()

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()

    # -- inbound (call these from the twitchio EventSub callbacks) ----------
    async def on_redemption(self, payload: object) -> None:
        """Hook a channel-point redemption. Wrapped so a bad payload can't crash
        the task or the round loop."""
        try:
            event = self._normalize_redemption(payload)
        except Exception:
            log.exception("could not parse channel-point redemption")
            return
        if event is not None:
            await self._rewards.handle_redemption(event)

    async def on_support(self, payload: object, kind: str, tier_value: int) -> None:
        """Hook a sub/resub/gift/cheer. ``tier_value`` is computed by the caller
        from the platform payload (e.g. bits/100, sub tier, months)."""
        try:
            event = self._normalize_support(payload, kind, tier_value)
        except Exception:
            log.exception("could not parse support event")
            return
        if event is not None:
            await self._rewards.handle_support(event)

    # ================= version-specific twitchio surface =================
    def _bootstrap(self):
        """Build the twitchio client, register EventSub subscriptions for
        channel-point redemptions + subs/bits on ``broadcaster_id``, and route
        their callbacks to :meth:`on_redemption` / :meth:`on_support`. ADJUST to
        the installed twitchio version (see the module note)."""
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
                # Subscribe here (channel.channel_points_custom_reward_redemption.add,
                # channel.subscribe, channel.cheer) for adapter._broadcaster_id.
                log.info("eventsub bot ready; wire subscriptions for %s", adapter._broadcaster_id)

            async def event_custom_redemption_add(self, payload) -> None:  # noqa: ANN001
                await adapter.on_redemption(payload)

            async def event_subscription(self, payload) -> None:  # noqa: ANN001
                await adapter.on_support(payload, "sub", 1)

            async def event_cheer(self, payload) -> None:  # noqa: ANN001
                bits = int(getattr(payload, "bits", 0) or 0)
                await adapter.on_support(payload, "bits", bits // 100)

        return _Bot()

    def _normalize_redemption(self, payload: object) -> RedemptionEvent | None:
        """Pull a normalized :class:`RedemptionEvent` from a twitchio redemption.
        ADJUST accessors to the installed twitchio version."""
        user = getattr(payload, "user", None) or getattr(payload, "chatter", None)
        reward = getattr(payload, "reward", None)
        event_id = str(getattr(payload, "id", "") or getattr(payload, "redemption_id", ""))
        if user is None or reward is None or not event_id:
            return None
        login = str(getattr(user, "name", "") or getattr(user, "login", ""))
        return RedemptionEvent(
            platform=PLATFORM,
            platform_user_id=str(getattr(user, "id", "")),
            display_name=str(getattr(user, "display_name", "") or login),
            login=login,
            reward_title=str(getattr(reward, "title", "") or getattr(reward, "name", "")),
            event_id=event_id,
            user_input=str(getattr(payload, "user_input", "") or ""),
        )

    def _normalize_support(
        self, payload: object, kind: str, tier_value: int
    ) -> SupportEvent | None:
        """Pull a normalized :class:`SupportEvent`. ADJUST accessors to twitchio."""
        user = getattr(payload, "user", None) or getattr(payload, "chatter", None)
        event_id = str(getattr(payload, "id", "") or getattr(payload, "message_id", ""))
        if user is None or not event_id:
            return None
        login = str(getattr(user, "name", "") or getattr(user, "login", ""))
        return SupportEvent(
            platform=PLATFORM,
            platform_user_id=str(getattr(user, "id", "")),
            display_name=str(getattr(user, "display_name", "") or login),
            login=login,
            tier_value=int(tier_value),
            event_id=event_id,
            kind=kind,
        )
