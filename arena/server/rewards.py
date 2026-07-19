"""Twitch EventSub reward logic (PLAN.md §6.2), decoupled from twitchio.

Channel-point redemptions and support events (subs/bits) are normalized to the
:class:`RedemptionEvent` / :class:`SupportEvent` boundary types (no
platform-library types past here — hard rule #3) and handed to
:class:`RewardRouter`, which is idempotent (hard rule #9: every event is guarded
by ``processed_events`` so Twitch redeliveries are no-ops) and holds all the
game-side effects, so it's unit-tested without any live Twitch.

Redemption effects (PLAN.md §7 roadmap): extra character slot, stat-reroll
token, priority-queue token. Support events grant gold (ties subs/bits into the
betting economy) — an Opus design choice where the spec left the effect open.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from . import events
from .config import Config
from .store import TOKEN_BONUS_SLOTS, TOKEN_PRIORITY, TOKEN_REROLL, Store


@dataclass(frozen=True)
class RedemptionEvent:
    """A normalized channel-point redemption."""

    platform: str
    platform_user_id: str
    display_name: str
    login: str
    reward_title: str
    event_id: str  # Twitch's unique redemption id, for idempotency
    user_input: str = ""


@dataclass(frozen=True)
class SupportEvent:
    """A normalized support event (sub, resub, gift, bits). ``tier_value`` is the
    normalized magnitude used for the gold grant (PLAN.md §6.5)."""

    platform: str
    platform_user_id: str
    display_name: str
    login: str
    tier_value: int
    event_id: str
    kind: str = "support"  # sub | resub | bits | ...


class RewardRouter:
    """Applies normalized EventSub events to game state, once each."""

    def __init__(
        self, cfg: Config, store: Store, sink: events.EventSink,
        *, logger: logging.Logger | None = None,
    ) -> None:
        self._cfg = cfg
        self._store = store
        self._sink = sink
        self._log = logger or logging.getLogger("dndarena.rewards")

    async def handle_redemption(self, e: RedemptionEvent) -> None:
        if not await self._store.mark_processed(e.event_id):
            return  # Twitch redelivery — already applied
        action = self._cfg.rewards.action_for(e.reward_title)
        if action is None:
            self._log.info("channel-point reward %r is not mapped; ignoring", e.reward_title)
            return
        uid = await self._store.register_user(
            e.platform, e.platform_user_id, e.login, e.display_name
        )
        if action == "extra_slot":
            await self._store.grant_tokens(uid, TOKEN_BONUS_SLOTS, 1)
            text = "unlocked an extra character slot"
        elif action == "stat_reroll":
            await self._store.grant_tokens(uid, TOKEN_REROLL, 1)
            text = "earned a stat reroll — !reroll <name> before entering"
        elif action == "priority_queue":
            await self._store.grant_tokens(uid, TOKEN_PRIORITY, 1)
            text = "earned a priority token — the next !enter jumps the queue"
        else:  # pragma: no cover - action set is validated in config
            return
        await self._emit(e.platform, text, e.login or e.display_name)

    async def handle_support(self, e: SupportEvent) -> None:
        if not await self._store.mark_processed(e.event_id):
            return
        gold = max(0, e.tier_value) * self._cfg.rewards.gold_per_tier
        if gold <= 0:
            return
        uid = await self._store.register_user(
            e.platform, e.platform_user_id, e.login, e.display_name
        )
        await self._store.award_gold([uid], gold)
        await self._emit(
            e.platform, f"thanks for the support! +{gold:,} gold", e.login or e.display_name
        )

    async def _emit(self, platform: str, text: str, mention: str) -> None:
        line = f"{text} (@{mention})" if mention else text
        try:
            await self._sink.emit(events.ticker("reward", line, platform))
        except Exception:
            self._log.exception("reward ticker sink raised; dropping")
