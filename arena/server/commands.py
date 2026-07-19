"""Chat command layer (PLAN.md §6.2), decoupled from any chat platform.

``GameCommands.handle(msg)`` takes a normalized :class:`~server.adapters.InboundMessage`
and returns a list of :class:`Outcome`s — structured command results carrying a
ticker ``kind`` and a platform-agnostic ``text`` (no @mention decoration). The
:class:`~server.adapters.MessageRouter` turns each outcome into a ``ticker``
overlay event (the primary feedback channel, PLAN.md §6.1) and a ≤1-line chat
mirror string. This layer holds no network code and no @mention/platform
formatting, so the whole command surface is unit-tested without any platform.

Safety (PLAN.md §6.4): every command is wrapped so a malformed one can never
crash the round loop; per-user cooldowns throttle spam; names are validated and
profanity-filtered (reject, don't sanitize). Users are keyed on
``(platform, platform_user_id)`` (hard rule #4).
"""

from __future__ import annotations

import logging
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime

from . import content, names, rules
from .adapters import InboundMessage
from .arena import Arena
from .config import STAT_NAMES, Config
from .models import Character
from .store import (
    BET_EXISTS,
    BET_INSUFFICIENT,
    SHOP_INSUFFICIENT,
    SHOP_OWNED,
    TOKEN_BONUS_SLOTS,
    TOKEN_PRIORITY,
    TOKEN_REROLL,
    Store,
    utcnow,
)

README_URL = "https://github.com/your/dnd-arena#readme"  # update to the real repo

GLOBAL_COOLDOWN_S = 3.0
CREATE_COOLDOWN_S = 30.0
# Commands exempt from the global cooldown: the retire confirmation step and mod
# controls must stay responsive.
_COOLDOWN_EXEMPT = {"confirm", "pause", "resume", "start", "close", "banplayer", "renamechar"}
_MOD_ONLY = {"pause", "resume", "start", "close", "banplayer", "renamechar"}


@dataclass(frozen=True)
class Outcome:
    """A single command result. ``kind`` drives the overlay ticker styling
    (create|enter|error|retire|info|mod); ``text`` is the human-readable message
    with NO @mention or platform decoration — the router adds those per platform.
    ``addressed`` is True when the outcome speaks to the invoking user (the router
    then @mentions them / appends ``(@user)`` on the ticker); False for public
    lines like leaderboards and mod broadcasts."""

    kind: str
    text: str
    addressed: bool = True


class CommandError(ValueError):
    """User-facing command failure; surfaced as an ``error`` outcome."""


Handler = Callable[["GameCommands", InboundMessage, list[str]], Awaitable[list[Outcome]]]


def _identity_key(msg: InboundMessage) -> str:
    """Per-user throttle/state key. Same human on two platforms = two keys."""
    return f"{msg.platform}:{msg.platform_user_id}"


@dataclass
class _TrainReq:
    """A pending co-training invitation (R6), keyed by the target owner's user id."""

    initiator_user_id: int
    mentor_a_id: int
    mentor_b_id: int
    parent_a_stats: dict[str, int]
    parent_b_stats: dict[str, int]
    mentor_a_name: str
    mentor_b_name: str
    generation: int
    class_name: str
    race: str
    child_name: str
    cost: int
    expires_at: float


class GameCommands:
    def __init__(
        self,
        cfg: Config,
        store: Store,
        arena: Arena,
        *,
        rng: random.Random | None = None,
        now: Callable[[], datetime] | None = None,
        profanity_check: Callable[[str], bool] | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.cfg = cfg
        self.store = store
        self.arena = arena
        self._rng = rng or random.Random()
        self._now = now or utcnow
        self._profanity = profanity_check
        self._logger = logger or logging.getLogger("dndarena.commands")

        self._last_cmd: dict[str, float] = {}
        self._last_create: dict[str, float] = {}
        self._pending_retire: dict[str, int] = {}
        self._pending_training: dict[int, _TrainReq] = {}  # keyed by target user_id (R6)
        self._stat_expectations: list[float] | None = None  # cached (R6 training)
        self._hof_index = 0  # rotates !hof through the records, one per call

    # -- entry point -------------------------------------------------------
    async def handle(self, msg: InboundMessage) -> list[Outcome]:
        text = msg.text.strip()
        if not text.startswith("!"):
            return []
        parts = text[1:].split()
        if not parts:
            return []
        cmd = parts[0].lower()
        args = parts[1:]

        handler = _DISPATCH.get(cmd)
        if handler is None:
            return []
        if cmd in _MOD_ONLY and not msg.is_mod:
            return []
        key = _identity_key(msg)
        try:
            if await self.store.is_banned(msg.platform, msg.platform_user_id):
                return []
            if cmd not in _COOLDOWN_EXEMPT and self._on_cooldown(key):
                return []
            outcomes = await handler(self, msg, args)
            if cmd not in _COOLDOWN_EXEMPT:
                self._last_cmd[key] = self._now().timestamp()
            return outcomes
        except (CommandError, names.InvalidName) as e:
            return [Outcome("error", str(e))]
        except Exception:  # a bad command must never take down the loop
            self._logger.exception("command %r from %s failed", text, msg.login)
            return []

    # -- cooldowns ---------------------------------------------------------
    def _on_cooldown(self, key: str) -> bool:
        last = self._last_cmd.get(key)
        return last is not None and (self._now().timestamp() - last) < GLOBAL_COOLDOWN_S

    # -- commands ----------------------------------------------------------
    async def cmd_create(self, msg: InboundMessage, args: list[str]) -> list[Outcome]:
        key = _identity_key(msg)
        now = self._now().timestamp()
        last = self._last_create.get(key)
        if last is not None and now - last < CREATE_COOLDOWN_S:
            wait = int(CREATE_COOLDOWN_S - (now - last)) + 1
            raise CommandError(f"wait {wait}s before creating another character")
        if len(args) < 3:
            raise CommandError("usage: !create <class> <race> <name>")
        class_name = args[0].lower()
        race = args[1].lower()
        if class_name not in self.cfg.classes:
            raise CommandError(f"unknown class '{args[0]}'. classes: {', '.join(self.cfg.classes)}")
        if race not in content.VALID_RACES:
            raise CommandError(f"unknown race '{args[1]}'. races: {', '.join(content.VALID_RACES)}")
        name = names.validate_name(" ".join(args[2:]), profanity_check=self._profanity)

        user_id = await self._register(msg)
        roster = await self.store.living_roster(user_id)
        # Base roster limit plus any rented extra slots (channel-point reward).
        bonus = await self.store.get_tokens(user_id, TOKEN_BONUS_SLOTS)
        limit = self.cfg.round.roster_limit + bonus
        if len(roster) >= limit:
            raise CommandError(
                f"you already have {limit} living characters (!retire one first)"
            )

        stats = self._roll_stats(class_name)
        # Race creation-time passive: Human +1 all, Dwarf +2 CON (PLAN.md §4.3).
        stats = rules.apply_creation_bonus(stats, self.cfg.race_passives(race))
        sprite = self._pick_sprite(class_name)
        personality = self._rng.choice(content.PERSONALITIES)
        ch = await self.store.add_character(
            user_id=user_id,
            name=name,
            class_name=class_name,
            race=race,
            stats=stats,
            sprite_set=sprite,
            personality=personality,
        )
        self._last_create[key] = now
        statline = " ".join(f"{s} {ch.stats[s]}" for s in STAT_NAMES)
        return [
            Outcome(
                "create",
                f"{ch.name} the {personality} {content.title(race)} "
                f"{content.title(class_name)} is born! {statline} - !enter to fight",
            )
        ]

    async def cmd_enter(self, msg: InboundMessage, args: list[str]) -> list[Outcome]:
        ch = await self._resolve_own(msg, args)
        # Spend a priority token (channel-point reward) to jump the queue, but only
        # if this character isn't already queued (don't waste the token).
        priority = False
        if not self.arena.is_queued(ch.id) and await self.store.get_tokens(
            ch.user_id, TOKEN_PRIORITY
        ):
            priority = await self.store.consume_token(ch.user_id, TOKEN_PRIORITY)
        pos = await self.arena.enqueue(ch.id, ch.user_id, priority=priority)
        tag = " - priority!" if priority else ""
        closed = (
            "" if self.arena.is_open
            else " — arena is closed; you'll fight when a mod opens it"
        )
        return [Outcome("enter", f"{ch.name} entered the queue (position {pos}){tag}{closed}")]

    async def cmd_reroll(self, msg: InboundMessage, args: list[str]) -> list[Outcome]:
        ch = await self._resolve_own(msg, args)
        if ch.battles_fought > 0:
            raise CommandError(f"{ch.name} has already fought - rerolls are for fresh characters")
        if not await self.store.consume_token(ch.user_id, TOKEN_REROLL):
            raise CommandError("no stat-reroll tokens - redeem the channel-point reward first")
        stats = rules.apply_creation_bonus(
            self._roll_stats(ch.class_name), self.cfg.race_passives(ch.race)
        )
        await self.store.set_character_stats(ch.id, stats)
        statline = " ".join(f"{s} {stats[s]}" for s in STAT_NAMES)
        return [Outcome("create", f"{ch.name} rerolled their stats! {statline}")]

    async def cmd_stats(self, msg: InboundMessage, args: list[str]) -> list[Outcome]:
        ch = await self._resolve_own(msg, args)
        return [Outcome("info", self._format_stats(ch), addressed=False)]

    async def cmd_inspect(self, msg: InboundMessage, args: list[str]) -> list[Outcome]:
        if not args:
            raise CommandError("usage: !inspect <name>")
        ch = await self.store.find_living_any(" ".join(args))
        if ch is None:
            raise CommandError(f"no living character named '{' '.join(args)}'")
        return [Outcome("info", self._format_stats(ch), addressed=False)]

    async def cmd_roster(self, msg: InboundMessage, args: list[str]) -> list[Outcome]:
        user_id = await self._register(msg)
        roster = await self.store.living_roster(user_id)
        if not roster:
            return [Outcome("info", "no living characters — !create <class> <race> <name>")]
        left = self.cfg.round.lifespan_battles
        parts = [
            f"{i}) {c.name} Lv{c.level} {content.CLASS_ABBREV.get(c.class_name, c.class_name)} "
            f"({left - c.battles_fought} left)"
            for i, c in enumerate(roster, start=1)
        ]
        return [Outcome("info", " ".join(parts))]

    def _retire_busy(self, character_id: int) -> bool:
        """A queued or currently-fighting character can't retire (a retired char
        drawn from the queue would burn a lineup slot). Same guard as the web."""
        return self.arena.is_queued(character_id) or self.arena.is_fighting(character_id)

    async def cmd_retire(self, msg: InboundMessage, args: list[str]) -> list[Outcome]:
        ch = await self._resolve_own(msg, args)
        if self._retire_busy(ch.id):
            raise CommandError(f"{ch.name} is queued or fighting — finish the round first")
        self._pending_retire[_identity_key(msg)] = ch.id
        return [Outcome("retire", f"retire {ch.name}? Type !confirm within the next command.")]

    async def cmd_confirm(self, msg: InboundMessage, args: list[str]) -> list[Outcome]:
        char_id = self._pending_retire.pop(_identity_key(msg), None)
        if char_id is None:
            return [Outcome("retire", "nothing to confirm")]
        ch = await self.store.get_living_character(char_id)
        if ch is None:
            return [Outcome("retire", "that character is no longer available")]
        if self._retire_busy(char_id):
            return [Outcome("retire", f"{ch.name} is queued or fighting — finish the round first")]
        await self.store.retire_character(char_id)
        return [Outcome("retire", f"{ch.name} has retired. Thanks for the memories!")]

    async def cmd_leaderboard(self, msg: InboundMessage, args: list[str]) -> list[Outcome]:
        board = args[0].lower() if args else "dps"
        # All-time board persists across seasons; the other two reset monthly.
        if board == "alltime":
            top = await self.store.top_by_damage(3)
            if not top:
                return [Outcome("info", "No damage recorded yet.", addressed=False)]
            body = " ".join(f"{i}) {c.name} {c.lifetime_damage:,}" for i, c in enumerate(top, 1))
            return [Outcome("info", f"All-time damage: {body}", addressed=False)]
        season_id = await self.store.ensure_current_season(self._now())
        by = "wins" if board == "wins" else "damage"
        rows = await self.store.season_leaderboard(season_id, by, 3)
        if not rows:
            noun = "wins" if by == "wins" else "damage"
            return [Outcome("info", f"No season {noun} recorded yet.", addressed=False)]
        if by == "wins":
            body = " ".join(f"{i}) {r.name} {r.value}W" for i, r in enumerate(rows, 1))
            return [Outcome("info", f"Season wins: {body}", addressed=False)]
        body = " ".join(f"{i}) {r.name} {r.value:,}" for i, r in enumerate(rows, 1))
        return [Outcome("info", f"Season damage: {body}", addressed=False)]

    async def cmd_hof(self, msg: InboundMessage, args: list[str]) -> list[Outcome]:
        records = await self.store.hall_of_fame()
        if not records:
            return [
                Outcome("info", "No Hall of Fame records yet - go make history!", addressed=False)
            ]
        rec = records[self._hof_index % len(records)]
        self._hof_index += 1
        label = content.HOF_LABELS.get(rec.record_key, rec.record_key)
        return [
            Outcome("info", f"HoF - {label}: {int(rec.value):,} by {rec.character_name}",
                    addressed=False)
        ]

    async def cmd_help(self, msg: InboundMessage, args: list[str]) -> list[Outcome]:
        return [
            Outcome(
                "info",
                "Commands: !create <class> <race> <name>, !enter, !stats, !roster, "
                "!retire, !leaderboard, !hof, !bet <fighter> <gold>, !gold, !inspect <name>, "
                f"!help — full guide: {README_URL}",
                addressed=False,
            )
        ]

    async def cmd_bet(self, msg: InboundMessage, args: list[str]) -> list[Outcome]:
        if len(args) < 2:
            raise CommandError("usage: !bet <fighter|slot> <amount>")
        if not self.arena.betting_open:
            raise CommandError("betting is closed - bets open when the next lineup locks")
        try:
            amount = int(args[-1])
        except ValueError:
            raise CommandError("bet amount must be a whole number of gold") from None
        if amount < self.cfg.economy.min_bet:
            raise CommandError(f"minimum bet is {self.cfg.economy.min_bet} gold")
        target = self.arena.resolve_bet_target(" ".join(args[:-1]))
        if target is None:
            raise CommandError(f"no fighter '{' '.join(args[:-1])}' in this round")
        slot, name = target
        round_id = self.arena.current_round_id
        if round_id is None:  # window closed between the checks
            raise CommandError("betting just closed for this round")
        user_id = await self._register(msg)
        result = await self.store.place_bet(round_id, user_id, slot, amount)
        if result == BET_EXISTS:
            raise CommandError("you already have a bet on this round")
        if result == BET_INSUFFICIENT:
            raise CommandError(f"not enough gold - you have {await self.store.get_gold(user_id):,}")
        return [Outcome("bet", f"bet {amount:,} gold on {name}")]

    async def cmd_gold(self, msg: InboundMessage, args: list[str]) -> list[Outcome]:
        gold = await self.store.get_gold(await self._register(msg))
        return [Outcome("info", f"you have {gold:,} gold")]

    # -- R5 shop (docs/R4_R6_plan.md) --------------------------------------
    async def cmd_shop(self, msg: InboundMessage, args: list[str]) -> list[Outcome]:
        if not self.cfg.shop.enabled:
            raise CommandError("the shop isn't open yet")
        parts = []
        for slot in ("weapon", "armor", "trinket"):
            items = sorted(self.cfg.shop.items_for_slot(slot), key=lambda i: i.price)
            if items:
                listing = ", ".join(f"{it.name} ({it.price:,}g)" for it in items)
                parts.append(f"{slot}s — {listing}")
        return [Outcome("info", "Shop | " + " | ".join(parts), addressed=False)]

    def _shop_item(self, args: list[str]):
        """Resolve a catalog item by display name or item_id, or raise."""
        query = " ".join(args).strip().casefold()
        item = next(
            (it for it in self.cfg.shop.items.values()
             if it.name.casefold() == query or it.item_id.casefold() == query),
            None,
        )
        if item is None:
            raise CommandError(f"no shop item '{' '.join(args)}' — see !shop")
        return item

    async def cmd_buy(self, msg: InboundMessage, args: list[str]) -> list[Outcome]:
        if not self.cfg.shop.enabled:
            raise CommandError("the shop isn't open yet")
        if not args:
            raise CommandError("usage: !buy <item> (see !shop)")
        item = self._shop_item(args)
        ch = await self._resolve_own(msg, [])  # most-recent living character
        result = await self.store.buy_item(
            ch.user_id, ch.id, item.slot, item.item_id, item.price
        )
        if result == SHOP_INSUFFICIENT:
            gold = await self.store.get_gold(ch.user_id)
            raise CommandError(
                f"not enough gold for {item.name} ({item.price:,}g) — you have {gold:,}"
            )
        if result == SHOP_OWNED:
            # Already in the bag — re-equip for free instead of erroring.
            await self.store.equip_item(ch.id, item.slot, item.item_id)
            return [Outcome("info", f"{ch.name} already owned {item.name} — equipped it")]
        return [Outcome("info", f"{ch.name} equipped {item.name}! (replaced gear is kept)")]

    async def cmd_gear(self, msg: InboundMessage, args: list[str]) -> list[Outcome]:
        ch = await self._resolve_own(msg, args)
        equip = await self.store.get_equipment(ch.id)
        worn = [
            f"{slot}: {self.cfg.shop.items[iid].name}"
            for slot in ("weapon", "armor", "trinket")
            if (iid := equip.get(slot)) and iid in self.cfg.shop.items
        ]
        bag = [i for i in await self.store.get_inventory(ch.id) if i not in equip.values()]
        bag_note = f" | bag: {len(bag)} more" if bag else ""
        if not worn:
            if bag:
                return [Outcome(
                    "info",
                    f"{ch.name} has nothing equipped{bag_note} — !equip <item>",
                    addressed=False,
                )]
            return [Outcome("info", f"{ch.name} has no gear — !shop to browse", addressed=False)]
        return [Outcome(
            "info", f"{ch.name}'s gear | " + ", ".join(worn) + bag_note, addressed=False
        )]

    async def cmd_equip(self, msg: InboundMessage, args: list[str]) -> list[Outcome]:
        if not self.cfg.shop.enabled:
            raise CommandError("the shop isn't open yet")
        if not args:
            raise CommandError("usage: !equip <item> [character]")
        item = self._shop_item(args)
        ch = await self._resolve_own(msg, [])
        if not await self.store.equip_item(ch.id, item.slot, item.item_id):
            raise CommandError(f"{ch.name} doesn't own {item.name} — !buy it first")
        return [Outcome("info", f"{ch.name} equipped {item.name}")]

    async def cmd_unequip(self, msg: InboundMessage, args: list[str]) -> list[Outcome]:
        if not self.cfg.shop.enabled:
            raise CommandError("the shop isn't open yet")
        slot = args[0].casefold() if args else ""
        if slot not in ("weapon", "armor", "trinket"):
            raise CommandError("usage: !unequip <weapon|armor|trinket>")
        ch = await self._resolve_own(msg, [])
        if not await self.store.unequip_item(ch.id, slot):
            raise CommandError(f"{ch.name} has nothing equipped in {slot}")
        return [Outcome("info", f"{ch.name} unequipped their {slot} (kept in the bag)")]

    # -- R6 co-training (docs/R4_R6_plan.md) -------------------------------
    def _expectations(self) -> list[float]:
        if self._stat_expectations is None:
            self._stat_expectations = rules.sorted_stat_expectations(self.cfg.stats)
        return self._stat_expectations

    async def cmd_train(self, msg: InboundMessage, args: list[str]) -> list[Outcome]:
        tc = self.cfg.training
        if not tc.enabled:
            raise CommandError("co-training isn't available yet")
        if len(args) < 5:
            raise CommandError(
                "usage: !train <myRetired> <theirRetired> <class> <race> <childName>"
            )
        my_name, their_name = args[0], args[1]
        class_name, race = args[2].lower(), args[3].lower()
        if class_name not in self.cfg.classes:
            raise CommandError(f"unknown class '{args[2]}'")
        if race not in content.VALID_RACES:
            raise CommandError(f"unknown race '{args[3]}'")
        child_name = names.validate_name(" ".join(args[4:]), profanity_check=self._profanity)

        uid = await self._register(msg)
        mine = await self.store.find_retired(uid, my_name)
        if mine is None:
            raise CommandError(f"you have no RETIRED character named '{my_name}'")
        if mine.mentor_uses >= tc.max_uses:
            raise CommandError(f"{mine.name} has already mentored {tc.max_uses} times")
        theirs = await self.store.find_retired_any(their_name)
        if theirs is None:
            raise CommandError(f"no retired character named '{their_name}' to co-train with")
        if theirs.user_id == uid:
            raise CommandError("both parents can't be yours — invite another player's retiree")
        if theirs.mentor_uses >= tc.max_uses:
            raise CommandError(f"{theirs.name} has already mentored the maximum times")

        cost = rules.training_cost(tc.base_cost, mine.mentor_uses + theirs.mentor_uses)
        gold = await self.store.get_gold(uid)
        if gold < cost:
            raise CommandError(f"co-training {child_name} costs {cost:,}g — you have {gold:,}")

        self._pending_training[theirs.user_id] = _TrainReq(
            initiator_user_id=uid, mentor_a_id=mine.id, mentor_b_id=theirs.id,
            parent_a_stats=dict(mine.stats), parent_b_stats=dict(theirs.stats),
            mentor_a_name=mine.name, mentor_b_name=theirs.name,
            generation=max(mine.generation, theirs.generation) + 1,
            class_name=class_name, race=race, child_name=child_name, cost=cost,
            expires_at=self._now().timestamp() + 300,
        )
        owner = theirs.owner_login or "the other owner"
        return [Outcome(
            "info",
            f"{mine.name} + {theirs.name} to co-train {child_name} ({cost:,}g). "
            f"@{owner}: !accept or !decline",
            addressed=False,
        )]

    async def cmd_accept(self, msg: InboundMessage, args: list[str]) -> list[Outcome]:
        uid = await self._register(msg)
        req = self._pending_training.pop(uid, None)
        if req is None:
            raise CommandError("no training invitation to accept")
        if self._now().timestamp() > req.expires_at:
            raise CommandError("that training invitation expired")
        cd = self.cfg.classes[req.class_name]
        stats = rules.blend_training_stats(
            req.parent_a_stats, req.parent_b_stats, cd,
            self._expectations(), self.cfg.training, self._rng,
        )
        child = await self.store.train_character(
            initiator_user_id=req.initiator_user_id, mentor_a_id=req.mentor_a_id,
            mentor_b_id=req.mentor_b_id, cost=req.cost, name=req.child_name,
            class_name=req.class_name, race=req.race, stats=stats,
            sprite_set=self._pick_sprite(req.class_name), generation=req.generation,
            personality=self._rng.choice(content.PERSONALITIES),
        )
        if child is None:
            raise CommandError("the initiator can no longer afford the training")
        statline = " ".join(f"{s} {child.stats[s]}" for s in STAT_NAMES)
        return [Outcome(
            "create",
            f"{child.name} is born, trained by {req.mentor_a_name} & {req.mentor_b_name} "
            f"(gen {child.generation})! {statline} — !enter to fight",
            addressed=False,
        )]

    async def cmd_decline(self, msg: InboundMessage, args: list[str]) -> list[Outcome]:
        uid = await self._register(msg)
        req = self._pending_training.pop(uid, None)
        if req is None:
            raise CommandError("no training invitation to decline")
        return [Outcome("info", f"declined the invitation to train {req.child_name}",
                        addressed=False)]

    # -- mod commands ------------------------------------------------------
    async def cmd_pause(self, msg: InboundMessage, args: list[str]) -> list[Outcome]:
        self.arena.pause()
        return [Outcome("mod", "Arena will pause after the current round.", addressed=False)]

    async def cmd_resume(self, msg: InboundMessage, args: list[str]) -> list[Outcome]:
        self.arena.resume()
        return [Outcome("mod", "Arena resumed.", addressed=False)]

    async def cmd_start(self, msg: InboundMessage, args: list[str]) -> list[Outcome]:
        if self.arena.is_open:
            return [Outcome("mod", "Arena is already open.", addressed=False)]
        self.arena.open()
        text = "Arena is OPEN — !enter to join the next round!"
        if self.arena.paused:
            text += " (still paused — !resume to run)"
        return [Outcome("mod", text, addressed=False)]

    async def cmd_close(self, msg: InboundMessage, args: list[str]) -> list[Outcome]:
        if not self.arena.is_open:
            return [Outcome("mod", "Arena is already closed.", addressed=False)]
        self.arena.close()
        return [Outcome("mod",
                        "Arena will close after the current round — the queue is kept. "
                        "!start reopens.", addressed=False)]

    async def cmd_banplayer(self, msg: InboundMessage, args: list[str]) -> list[Outcome]:
        if not args:
            raise CommandError("usage: !banplayer <login>")
        target = args[0].lstrip("@").lower()
        ok = await self.store.set_banned(msg.platform, target, True)
        state = "now banned" if ok else "not a known player"
        return [Outcome("mod", f"{target} is {state}.", addressed=False)]

    async def cmd_renamechar(self, msg: InboundMessage, args: list[str]) -> list[Outcome]:
        if len(args) < 2:
            raise CommandError("usage: !renamechar <old> <new>")
        target = await self.store.find_living_any(args[0])
        if target is None:
            raise CommandError(f"no living character named '{args[0]}'")
        new_name = names.validate_name(" ".join(args[1:]), profanity_check=self._profanity)
        await self.store.rename_character(target.id, new_name)
        return [Outcome("mod", f"{target.name} is now known as {new_name}.", addressed=False)]

    # -- helpers -----------------------------------------------------------
    async def _register(self, msg: InboundMessage) -> int:
        return await self.store.register_user(
            msg.platform, msg.platform_user_id, msg.login, msg.display_name
        )

    async def _resolve_own(self, msg: InboundMessage, args: list[str]) -> Character:
        user_id = await self._register(msg)
        if args:
            ch = await self.store.find_living(user_id, " ".join(args))
            if ch is None:
                raise CommandError(f"you have no living character named '{' '.join(args)}'")
            return ch
        ch = await self.store.most_recent_living(user_id)
        if ch is None:
            raise CommandError("no living character — !create <class> <race> <name>")
        return ch

    def _format_stats(self, ch: Character) -> str:
        left = self.cfg.round.lifespan_battles - ch.battles_fought
        trait = f" the {ch.personality}" if ch.personality else ""
        return (
            f"{ch.name}{trait} - Lv{ch.level} {content.title(ch.class_name)} "
            f"({content.title(ch.race)}) | {ch.wins}W/{ch.losses}L | "
            f"{ch.lifetime_damage:,} dmg | best hit {ch.highest_hit} | {left} battles left"
        )

    def _roll_stats(self, class_name: str) -> dict[str, int]:
        """A fresh ability block. Under the moore engine (R1) the rolls are assigned
        by the class's stat-priority order (sorted-4d6, highest roll -> primary);
        the classic engine keeps the independent per-stat roll its balance gate was
        tuned on. Gated so live behavior only changes when the owner flips the
        engine (docs/PLAN.md §13.2)."""
        if self.cfg.combat.engine == "moore":
            return rules.roll_sorted_stat_block(
                self._rng, self.cfg.stats, self.cfg.classes[class_name]
            )
        return rules.roll_stat_block(self._rng, self.cfg.stats)

    def _pick_sprite(self, class_name: str) -> str:
        sprites = self.cfg.assets.get("sprite_sets", {}).get(class_name)
        return self._rng.choice(sprites) if sprites else f"{class_name}_01"


_DISPATCH: dict[str, Handler] = {
    "create": GameCommands.cmd_create,
    "enter": GameCommands.cmd_enter,
    "reroll": GameCommands.cmd_reroll,
    "stats": GameCommands.cmd_stats,
    "inspect": GameCommands.cmd_inspect,
    "roster": GameCommands.cmd_roster,
    "retire": GameCommands.cmd_retire,
    "confirm": GameCommands.cmd_confirm,
    "leaderboard": GameCommands.cmd_leaderboard,
    "top": GameCommands.cmd_leaderboard,
    "help": GameCommands.cmd_help,
    "pause": GameCommands.cmd_pause,
    "resume": GameCommands.cmd_resume,
    "start": GameCommands.cmd_start,
    "close": GameCommands.cmd_close,
    "banplayer": GameCommands.cmd_banplayer,
    "renamechar": GameCommands.cmd_renamechar,
    "hof": GameCommands.cmd_hof,
    "bet": GameCommands.cmd_bet,
    "gold": GameCommands.cmd_gold,
    # R5 shop (active only when [shop].enabled; otherwise they reply "not open yet"):
    "shop": GameCommands.cmd_shop,
    "buy": GameCommands.cmd_buy,
    "gear": GameCommands.cmd_gear,
    "equip": GameCommands.cmd_equip,
    "unequip": GameCommands.cmd_unequip,
    # R6 co-training (active only when [training].enabled):
    "train": GameCommands.cmd_train,
    "accept": GameCommands.cmd_accept,
    "decline": GameCommands.cmd_decline,
}
