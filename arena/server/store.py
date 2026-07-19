"""Persistence abstraction.

The round loop and the chat command layer talk to a ``Store``; only the store
writes to the database (hard rule #2). Two implementations are planned:

* ``MemoryStore`` (here) — an in-process store mirroring the schema, used by the
  demo runner and the tests. It lets the whole game run and be asserted on
  without a live Postgres.
* ``PgStore`` (asyncpg, in ``server/pgstore.py``) — the authoritative store for
  the running game. It implements the same protocol, so the round loop and
  command layer need zero changes to switch.

The store is deliberately *logic-free*: callers compute all game outcomes (via
``rules``) and hand the store absolute values to write. That keeps the SQL
implementation a straight mapping and the game rules in one place.

Reads hand out *detached copies* of characters so callers can never mutate
persistent state directly — only the store writes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Protocol

from . import content
from .models import (
    AttackRow,
    Bet,
    Character,
    Entry,
    HoFCandidate,
    HoFRecord,
    LeaderRow,
    RoundResult,
)

# place_bet outcomes.
BET_OK = "ok"
BET_EXISTS = "exists"  # user already bet this round
BET_INSUFFICIENT = "insufficient"  # not enough gold

# buy_item outcomes (R5 shop).
SHOP_OK = "ok"
SHOP_INSUFFICIENT = "insufficient"  # not enough gold
SHOP_OWNED = "owned"  # already in the character's inventory (no charge)

# Reward token kinds -> users column (PLAN.md §6.2). bonus_slots is a persistent
# roster bonus (granted, read); reroll/priority are consumable tokens.
TOKEN_BONUS_SLOTS = "bonus_slots"
TOKEN_REROLL = "reroll"
TOKEN_PRIORITY = "priority"
_TOKEN_COLUMN = {
    TOKEN_BONUS_SLOTS: "bonus_slots",
    TOKEN_REROLL: "reroll_tokens",
    TOKEN_PRIORITY: "priority_tokens",
}


def utcnow() -> datetime:
    return datetime.now(tz=UTC)


class Store(Protocol):
    # -- round loop --------------------------------------------------------
    async def recover(self) -> list[int]:
        """Void any round left unfinished by a crash (started but never
        finalized) so it consumes no character's battle lifespan (hard rule #7).
        Returns the voided round ids."""
        ...

    async def create_round(
        self, background: str, season_id: int | None, event: str | None = None
    ) -> int: ...

    async def save_entries(self, round_id: int, entries: list[Entry]) -> None:
        """Persist the locked lineup; sets ``entry.entry_id`` on each Entry."""
        ...

    async def flush_attacks(self, rows: list[AttackRow]) -> None: ...

    async def finalize_round(self, result: RoundResult) -> None:
        """Write round-entry aggregates, character updates, and the winner in one
        transaction. On ``result.voided`` only the round is marked voided."""
        ...

    async def get_living_character(self, character_id: int) -> Character | None: ...

    # -- users / characters (chat command layer) ---------------------------
    async def register_user(
        self, platform: str, platform_user_id: str, login: str, display_name: str
    ) -> int:
        """Upsert by ``(platform, platform_user_id)`` (hard rule #4); returns the
        internal user id. Same human on two platforms = two users (no linking)."""
        ...

    async def is_banned(self, platform: str, platform_user_id: str) -> bool: ...

    async def set_banned(self, platform: str, identifier: str, banned: bool) -> bool:
        """Ban/unban within ``platform`` by ``platform_user_id`` or by ``login``
        (mods type a username). Returns whether a user matched."""
        ...

    async def add_character(
        self,
        *,
        user_id: int,
        name: str,
        class_name: str,
        race: str,
        stats: dict[str, int],
        sprite_set: str,
        personality: str = "",
    ) -> Character: ...

    async def living_roster(self, user_id: int) -> list[Character]: ...

    async def most_recent_living(self, user_id: int) -> Character | None: ...

    async def find_living(self, user_id: int, name: str) -> Character | None: ...

    async def find_living_any(self, name: str) -> Character | None: ...

    async def retire_character(self, character_id: int) -> None: ...

    async def rename_character(self, character_id: int, new_name: str) -> bool: ...

    async def top_by_damage(self, limit: int) -> list[Character]: ...

    async def top_by_wins(self, limit: int) -> list[Character]: ...

    # -- seasons / hall of fame (PLAN.md §8) --------------------------------
    async def ensure_current_season(self, now: datetime) -> int:
        """Return the id of the calendar-month season containing ``now``, creating
        it on month rollover. Rounds are tagged with it so season leaderboards
        reset each month while the Hall of Fame persists all-time."""
        ...

    async def season_leaderboard(self, season_id: int, by: str, limit: int) -> list[LeaderRow]:
        """Top characters within one season. ``by`` is ``"damage"`` (summed round
        totals) or ``"wins"`` (first-place finishes)."""
        ...

    async def update_hall_of_fame(self, candidates: list[HoFCandidate]) -> None:
        """Upsert each candidate as its record only if it beats the stored value
        (all-time high-water marks; survive season resets)."""
        ...

    async def hall_of_fame(self) -> list[HoFRecord]: ...

    # -- economy / betting (PLAN.md §6.6) ----------------------------------
    async def get_gold(self, user_id: int) -> int: ...

    async def award_gold(self, user_ids: list[int], amount: int) -> None:
        """Passive per-round income to present chatters (bulk credit)."""
        ...

    async def place_bet(self, round_id: int, user_id: int, slot: int, amount: int) -> str:
        """Atomically deduct ``amount`` gold and record the bet. Returns
        ``BET_OK`` / ``BET_EXISTS`` (already bet this round) / ``BET_INSUFFICIENT``."""
        ...

    async def bets_for_round(self, round_id: int) -> list[Bet]: ...

    async def settle_bets(self, round_id: int, payouts: dict[int, int]) -> None:
        """Credit each winning bettor their payout and record it on the bet."""
        ...

    # -- EventSub rewards (PLAN.md §6.2) ------------------------------------
    async def mark_processed(self, event_id: str) -> bool:
        """Idempotency guard (hard rule #9): record ``event_id`` and return True
        the first time it's seen, False on Twitch redelivery."""
        ...

    async def grant_tokens(self, user_id: int, kind: str, amount: int) -> None: ...

    async def get_tokens(self, user_id: int, kind: str) -> int: ...

    async def consume_token(self, user_id: int, kind: str) -> bool:
        """Spend one token of ``kind``; return whether one was available."""
        ...

    async def set_character_stats(self, character_id: int, stats: dict[str, int]) -> None: ...

    # -- persistent game state (R4 monster ladder, etc.) -------------------
    async def get_game_state(self, key: str) -> str | None:
        """Value for a persistent key/value game-state key, or None if unset."""
        ...

    async def set_game_state(self, key: str, value: str) -> None:
        """Upsert a persistent game-state key (survives restarts)."""
        ...

    # -- R5 shop economy (docs/R4_R6_plan.md) ------------------------------
    async def credit_gold(self, user_id: int, amount: int) -> None:
        """Credit a single user variable performance gold (per-fighter payout)."""
        ...

    async def get_equipment(self, character_id: int) -> dict[str, str]:
        """Equipped items for a character, ``{slot: item_id}`` (empty if none)."""
        ...

    async def buy_item(
        self, user_id: int, character_id: int, slot: str, item_id: str, price: int
    ) -> str:
        """Atomically: reject if the character already owns ``item_id``
        (``SHOP_OWNED``, no charge), else deduct ``price`` gold, add the item to
        the character's inventory, and equip it in ``slot`` (the previously
        equipped item stays in the inventory). Returns ``SHOP_OK`` /
        ``SHOP_INSUFFICIENT`` / ``SHOP_OWNED``."""
        ...

    # -- gear inventory (website + chat !equip/!unequip; migration 0007) ---
    async def get_inventory(self, character_id: int) -> list[str]:
        """All item_ids the character owns (equipped or not), oldest first."""
        ...

    async def add_item(self, character_id: int, item_id: str) -> None:
        """Add an item to the character's inventory (idempotent)."""
        ...

    async def equip_item(self, character_id: int, slot: str, item_id: str) -> bool:
        """Equip an OWNED item into ``slot`` (replacing frees the old item back
        to the inventory). Returns False when the item isn't owned."""
        ...

    async def unequip_item(self, character_id: int, slot: str) -> bool:
        """Clear ``slot`` (the item stays in the inventory). Returns whether a
        slot was actually cleared."""
        ...

    # -- website reads ------------------------------------------------------
    async def retired_roster(self, user_id: int) -> list[Character]:
        """A user's retired characters, most recently retired first."""
        ...

    async def get_character(self, character_id: int) -> Character | None:
        """A character by id, living OR retired (public character sheets)."""
        ...

    # -- R6 co-training (docs/R4_R6_plan.md) -------------------------------
    async def find_retired(self, user_id: int, name: str) -> Character | None:
        """A *retired* character owned by ``user_id`` (mentors must be retired)."""
        ...

    async def find_retired_any(self, name: str) -> Character | None:
        """Any retired character by name (the other player's consenting mentor)."""
        ...

    async def train_character(
        self, *, initiator_user_id: int, mentor_a_id: int, mentor_b_id: int, cost: int,
        name: str, class_name: str, race: str, stats: dict[str, int], sprite_set: str,
        generation: int, personality: str = "",
    ) -> Character | None:
        """Atomically: deduct ``cost`` gold from the initiator, +1 mentor_use on both
        parents, and create the trained child (lineage + generation) owned by the
        initiator. Returns the child, or None if the initiator can't afford it."""
        ...


class MemoryStore:
    """In-memory Store mirroring the schema tables. Thread-unsafe by design — the
    game is single-process / single-loop."""

    def __init__(self, *, starting_gold: int = 100) -> None:
        self.users: dict[int, dict[str, Any]] = {}
        self.characters: dict[int, Character] = {}
        self.rounds: dict[int, dict[str, Any]] = {}
        self.entries: dict[int, dict[str, Any]] = {}
        self.attacks: list[dict[str, Any]] = []
        self.seasons: dict[int, dict[str, Any]] = {}
        self.hof: dict[str, dict[str, Any]] = {}
        self.bets: list[dict[str, Any]] = []
        self.processed: set[str] = set()
        self.game_state: dict[str, str] = {}  # R4 ladder + misc persistent kv
        self.inventory: dict[int, dict[str, datetime]] = {}  # char_id -> item_id -> acquired_at
        self._starting_gold = starting_gold
        self._round_seq = 0
        self._entry_seq = 0
        self._char_seq = 0
        self._user_seq = 0
        self._season_seq = 0

    # -- sync seeding helpers (tests / demo) -------------------------------
    def add_user(
        self,
        login: str,
        display_name: str | None = None,
        *,
        platform: str = "twitch",
        platform_user_id: str | None = None,
    ) -> int:
        self._user_seq += 1
        uid = self._user_seq
        self.users[uid] = {
            "platform": platform,
            "platform_user_id": platform_user_id or f"seed-{uid}",
            "login": login,
            "display_name": display_name or login,
            "is_banned": False,
            "gold": self._starting_gold,
        }
        return uid

    def create_character(
        self,
        *,
        user_id: int,
        name: str,
        class_name: str,
        race: str,
        stats: dict[str, int],
        sprite_set: str,
        generation: int = 1,
        level: int = 1,
        personality: str = "",
    ) -> Character:
        self._char_seq += 1
        cid = self._char_seq
        user = self.users.get(user_id, {})
        ch = Character(
            id=cid,
            user_id=user_id,
            name=name,
            class_name=class_name,
            race=race,
            stats=dict(stats),
            level=level,
            sprite_set=sprite_set,
            generation=generation,
            personality=personality,
            owner_login=user.get("login"),
            owner_platform=user.get("platform"),
        )
        self.characters[cid] = ch
        return ch

    # -- Store protocol: round loop ----------------------------------------
    async def recover(self) -> list[int]:
        voided = []
        for rid, rnd in self.rounds.items():
            if rnd.get("started_at") and not rnd.get("ended_at") and not rnd.get("is_voided"):
                rnd["is_voided"] = True
                voided.append(rid)
        return voided

    async def create_round(
        self, background: str, season_id: int | None, event: str | None = None
    ) -> int:
        self._round_seq += 1
        rid = self._round_seq
        self.rounds[rid] = {
            "id": rid,
            "season_id": season_id,
            "background": background,
            "event": event,
            "started_at": utcnow(),
            "ended_at": None,
            "winner_entry": None,
            "is_voided": False,
        }
        return rid

    async def save_entries(self, round_id: int, entries: list[Entry]) -> None:
        for e in entries:
            self._entry_seq += 1
            e.entry_id = self._entry_seq
            self.entries[e.entry_id] = {
                "id": e.entry_id,
                "round_id": round_id,
                "character_id": e.character_id,
                "slot": e.slot,
                "is_npc": e.is_npc,
                "dummy_sprite": e.dummy_sprite,
                "total_damage": 0,
                "hits": 0,
                "crits": 0,
                "misses": 0,
                "highest_hit": 0,
                "placement": None,
                "xp_awarded": 0,
            }

    async def flush_attacks(self, rows: list[AttackRow]) -> None:
        for r in rows:
            self.attacks.append(
                {
                    "entry_id": r.entry_id,
                    "roll": r.roll,
                    "damage": r.damage,
                    "is_crit": r.is_crit,
                    "is_miss": r.is_miss,
                }
            )

    async def finalize_round(self, result: RoundResult) -> None:
        rnd = self.rounds[result.round_id]
        rnd["ended_at"] = result.ended_at
        if result.voided:
            rnd["is_voided"] = True
            return
        for e in result.entries:
            row = self.entries[e.entry_id]
            row.update(
                total_damage=e.total_damage,
                hits=e.hits,
                crits=e.crits,
                misses=e.misses,
                highest_hit=e.highest_hit,
                placement=e.placement,
                xp_awarded=e.xp_awarded,
            )
        rnd["winner_entry"] = result.winner_entry_id
        for upd in result.character_updates:
            ch = self.characters[upd.character_id]
            ch.battles_fought = upd.battles_fought
            ch.wins = upd.wins
            ch.losses = upd.losses
            ch.xp = upd.xp
            ch.level = upd.level
            ch.stats = dict(upd.stats)
            ch.lifetime_damage = upd.lifetime_damage
            ch.lifetime_hits = upd.lifetime_hits
            ch.lifetime_crits = upd.lifetime_crits
            ch.highest_hit = upd.highest_hit
            ch.is_retired = upd.is_retired
            ch.retired_at = upd.retired_at

    async def get_living_character(self, character_id: int) -> Character | None:
        ch = self.characters.get(character_id)
        if ch is None or ch.is_retired:
            return None
        return ch.copy()  # detached copy — only the store writes

    # -- Store protocol: users / characters --------------------------------
    async def register_user(
        self, platform: str, platform_user_id: str, login: str, display_name: str
    ) -> int:
        for uid, u in self.users.items():
            if u.get("platform") == platform and u.get("platform_user_id") == platform_user_id:
                u["login"] = login
                u["display_name"] = display_name
                return uid
        self._user_seq += 1
        uid = self._user_seq
        self.users[uid] = {
            "platform": platform,
            "platform_user_id": platform_user_id,
            "login": login,
            "display_name": display_name,
            "is_banned": False,
            "gold": self._starting_gold,
        }
        return uid

    async def is_banned(self, platform: str, platform_user_id: str) -> bool:
        for u in self.users.values():
            if u.get("platform") == platform and u.get("platform_user_id") == platform_user_id:
                return bool(u.get("is_banned"))
        return False

    async def set_banned(self, platform: str, identifier: str, banned: bool) -> bool:
        key = identifier.casefold()
        matched = False
        for u in self.users.values():
            if u.get("platform") != platform:
                continue
            if u.get("platform_user_id") == identifier or (u.get("login") or "").casefold() == key:
                u["is_banned"] = banned
                matched = True
        return matched

    async def add_character(
        self,
        *,
        user_id: int,
        name: str,
        class_name: str,
        race: str,
        stats: dict[str, int],
        sprite_set: str,
        personality: str = "",
    ) -> Character:
        # generation = (retired characters this user has had) + 1
        retired = sum(
            1 for c in self.characters.values() if c.user_id == user_id and c.is_retired
        )
        ch = self.create_character(
            user_id=user_id,
            name=name,
            class_name=class_name,
            race=race,
            stats=stats,
            sprite_set=sprite_set,
            generation=retired + 1,
            personality=personality,
        )
        return ch.copy()

    async def living_roster(self, user_id: int) -> list[Character]:
        return [
            c.copy()
            for c in sorted(self.characters.values(), key=lambda c: c.id)
            if c.user_id == user_id and not c.is_retired
        ]

    async def most_recent_living(self, user_id: int) -> Character | None:
        living = [
            c for c in self.characters.values() if c.user_id == user_id and not c.is_retired
        ]
        return max(living, key=lambda c: c.id).copy() if living else None

    async def find_living(self, user_id: int, name: str) -> Character | None:
        key = name.casefold()
        matches = [
            c
            for c in self.characters.values()
            if c.user_id == user_id and not c.is_retired and c.name.casefold() == key
        ]
        return max(matches, key=lambda c: c.id).copy() if matches else None

    async def find_living_any(self, name: str) -> Character | None:
        key = name.casefold()
        matches = [
            c for c in self.characters.values() if not c.is_retired and c.name.casefold() == key
        ]
        return max(matches, key=lambda c: c.id).copy() if matches else None

    async def find_retired(self, user_id: int, name: str) -> Character | None:
        key = name.casefold()
        matches = [
            c for c in self.characters.values()
            if c.user_id == user_id and c.is_retired and c.name.casefold() == key
        ]
        return max(matches, key=lambda c: c.id).copy() if matches else None

    async def find_retired_any(self, name: str) -> Character | None:
        key = name.casefold()
        matches = [
            c for c in self.characters.values() if c.is_retired and c.name.casefold() == key
        ]
        return max(matches, key=lambda c: c.id).copy() if matches else None

    async def train_character(
        self, *, initiator_user_id: int, mentor_a_id: int, mentor_b_id: int, cost: int,
        name: str, class_name: str, race: str, stats: dict[str, int], sprite_set: str,
        generation: int, personality: str = "",
    ) -> Character | None:
        u = self.users.get(initiator_user_id)
        if u is None or u.get("gold", 0) < cost:
            return None
        u["gold"] -= cost
        for mid in (mentor_a_id, mentor_b_id):
            m = self.characters.get(mid)
            if m is not None:
                m.mentor_uses += 1
        child = self.create_character(
            user_id=initiator_user_id, name=name, class_name=class_name, race=race,
            stats=stats, sprite_set=sprite_set, generation=generation, personality=personality,
        )
        child.trained_by_a = mentor_a_id
        child.trained_by_b = mentor_b_id
        return child

    async def retire_character(self, character_id: int) -> None:
        ch = self.characters.get(character_id)
        if ch is not None and not ch.is_retired:
            ch.is_retired = True
            ch.retired_at = utcnow()

    async def rename_character(self, character_id: int, new_name: str) -> bool:
        ch = self.characters.get(character_id)
        if ch is None:
            return False
        ch.name = new_name
        return True

    async def top_by_damage(self, limit: int) -> list[Character]:
        ranked = sorted(self.characters.values(), key=lambda c: -c.lifetime_damage)
        return [c.copy() for c in ranked[:limit] if c.lifetime_damage > 0]

    async def top_by_wins(self, limit: int) -> list[Character]:
        ranked = sorted(self.characters.values(), key=lambda c: (-c.wins, -c.lifetime_damage))
        return [c.copy() for c in ranked[:limit] if c.wins > 0]

    # -- seasons / hall of fame --------------------------------------------
    async def ensure_current_season(self, now: datetime) -> int:
        key = (now.year, now.month)
        for sid, s in self.seasons.items():
            if s["key"] == key:
                return sid
        self._season_seq += 1
        sid = self._season_seq
        starts = datetime(now.year, now.month, 1, tzinfo=UTC)
        end_year = now.year + (1 if now.month == 12 else 0)
        end_month = 1 if now.month == 12 else now.month + 1
        ends = datetime(end_year, end_month, 1, tzinfo=UTC)
        self.seasons[sid] = {
            "id": sid,
            "key": key,
            "name": f"Season {sid} - {starts:%B %Y}",
            "starts_at": starts,
            "ends_at": ends,
        }
        return sid

    async def season_leaderboard(self, season_id: int, by: str, limit: int) -> list[LeaderRow]:
        agg: dict[int, int] = {}
        for e in self.entries.values():
            rnd = self.rounds.get(e["round_id"])
            if rnd is None or rnd.get("season_id") != season_id or rnd.get("is_voided"):
                continue
            cid = e["character_id"]
            if cid is None:
                continue
            if by == "wins":
                if e["placement"] == 1:
                    agg[cid] = agg.get(cid, 0) + 1
            else:  # "damage"
                agg[cid] = agg.get(cid, 0) + e["total_damage"]
        rows = [
            LeaderRow(self.characters[cid].name, int(val))
            for cid, val in agg.items()
            if val > 0 and cid in self.characters
        ]
        rows.sort(key=lambda r: -r.value)
        return rows[:limit]

    async def update_hall_of_fame(self, candidates: list[HoFCandidate]) -> None:
        for c in candidates:
            cur = self.hof.get(c.record_key)
            if cur is None or c.value > cur["value"]:
                self.hof[c.record_key] = {
                    "character_id": c.character_id,
                    "value": c.value,
                    "achieved_at": utcnow(),
                }

    async def hall_of_fame(self) -> list[HoFRecord]:
        out: list[HoFRecord] = []
        for key in content.HOF_KEYS:
            rec = self.hof.get(key)
            if rec is None:
                continue
            ch = self.characters.get(rec["character_id"])
            out.append(
                HoFRecord(
                    record_key=key,
                    character_id=rec["character_id"],
                    character_name=ch.name if ch else "?",
                    value=rec["value"],
                    achieved_at=rec["achieved_at"],
                )
            )
        return out

    # -- economy / betting -------------------------------------------------
    async def get_gold(self, user_id: int) -> int:
        return int(self.users.get(user_id, {}).get("gold", 0))

    async def award_gold(self, user_ids: list[int], amount: int) -> None:
        for uid in user_ids:
            u = self.users.get(uid)
            if u is not None:
                u["gold"] = u.get("gold", 0) + amount

    async def place_bet(self, round_id: int, user_id: int, slot: int, amount: int) -> str:
        for b in self.bets:
            if b["round_id"] == round_id and b["user_id"] == user_id:
                return BET_EXISTS
        u = self.users.get(user_id)
        if u is None or u.get("gold", 0) < amount:
            return BET_INSUFFICIENT
        u["gold"] -= amount
        self.bets.append(
            {"round_id": round_id, "user_id": user_id, "slot": slot,
             "amount": amount, "payout": None}
        )
        return BET_OK

    async def bets_for_round(self, round_id: int) -> list[Bet]:
        return [
            Bet(user_id=b["user_id"], slot=b["slot"], amount=b["amount"])
            for b in self.bets
            if b["round_id"] == round_id
        ]

    async def settle_bets(self, round_id: int, payouts: dict[int, int]) -> None:
        for b in self.bets:
            if b["round_id"] != round_id:
                continue
            pay = payouts.get(b["user_id"], 0)
            b["payout"] = pay
            if pay:
                self.users[b["user_id"]]["gold"] += pay

    # -- EventSub rewards --------------------------------------------------
    async def mark_processed(self, event_id: str) -> bool:
        if event_id in self.processed:
            return False
        self.processed.add(event_id)
        return True

    async def grant_tokens(self, user_id: int, kind: str, amount: int) -> None:
        col = _TOKEN_COLUMN[kind]
        u = self.users.get(user_id)
        if u is not None:
            u[col] = u.get(col, 0) + amount

    async def get_tokens(self, user_id: int, kind: str) -> int:
        return int(self.users.get(user_id, {}).get(_TOKEN_COLUMN[kind], 0))

    async def consume_token(self, user_id: int, kind: str) -> bool:
        col = _TOKEN_COLUMN[kind]
        u = self.users.get(user_id)
        if u is None or u.get(col, 0) <= 0:
            return False
        u[col] -= 1
        return True

    async def set_character_stats(self, character_id: int, stats: dict[str, int]) -> None:
        ch = self.characters.get(character_id)
        if ch is not None:
            ch.stats = dict(stats)

    async def get_game_state(self, key: str) -> str | None:
        return self.game_state.get(key)

    async def set_game_state(self, key: str, value: str) -> None:
        self.game_state[key] = value

    async def credit_gold(self, user_id: int, amount: int) -> None:
        u = self.users.get(user_id)
        if u is not None and amount:
            u["gold"] = u.get("gold", 0) + amount

    async def get_equipment(self, character_id: int) -> dict[str, str]:
        ch = self.characters.get(character_id)
        return dict(ch.equipment) if ch is not None else {}

    async def buy_item(
        self, user_id: int, character_id: int, slot: str, item_id: str, price: int
    ) -> str:
        ch = self.characters.get(character_id)
        if ch is None:
            return SHOP_INSUFFICIENT
        if item_id in self.inventory.get(character_id, {}):
            return SHOP_OWNED  # no charge; caller may re-equip for free
        u = self.users.get(user_id)
        if u is None or u.get("gold", 0) < price:
            return SHOP_INSUFFICIENT
        u["gold"] -= price
        self.inventory.setdefault(character_id, {})[item_id] = utcnow()
        ch.equipment[slot] = item_id  # replaced item stays in the inventory
        return SHOP_OK

    # -- gear inventory (migration 0007) ------------------------------------
    async def get_inventory(self, character_id: int) -> list[str]:
        items = self.inventory.get(character_id, {})
        return sorted(items, key=lambda i: items[i])

    async def add_item(self, character_id: int, item_id: str) -> None:
        self.inventory.setdefault(character_id, {}).setdefault(item_id, utcnow())

    async def equip_item(self, character_id: int, slot: str, item_id: str) -> bool:
        ch = self.characters.get(character_id)
        if ch is None or item_id not in self.inventory.get(character_id, {}):
            return False
        ch.equipment[slot] = item_id
        return True

    async def unequip_item(self, character_id: int, slot: str) -> bool:
        ch = self.characters.get(character_id)
        if ch is None or slot not in ch.equipment:
            return False
        del ch.equipment[slot]
        return True

    # -- website reads -------------------------------------------------------
    async def retired_roster(self, user_id: int) -> list[Character]:
        retired = [
            c for c in self.characters.values() if c.user_id == user_id and c.is_retired
        ]
        epoch = datetime.min.replace(tzinfo=UTC)
        retired.sort(key=lambda c: c.retired_at or epoch, reverse=True)
        return [c.copy() for c in retired]

    async def get_character(self, character_id: int) -> Character | None:
        ch = self.characters.get(character_id)
        return ch.copy() if ch is not None else None
