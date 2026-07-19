"""PostgreSQL store (asyncpg) — the authoritative persistence for the running
game. Implements the same ``Store`` protocol as ``MemoryStore``, so the arena
and command layer use it unchanged.

Only this module (the server) writes to Postgres (hard rule #2). The ability
score ``INT`` maps to the ``intl`` column (``int`` collides with the type name).

Requires ``asyncpg`` (declared runtime dep) and a database migrated with
``db/migrations`` (see ``server/migrate.py``). Not exercised by the unit tests,
which use ``MemoryStore``; integration-tested against a live Postgres.
"""

from __future__ import annotations

from datetime import UTC, datetime

import asyncpg

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
from .store import _TOKEN_COLUMN, BET_EXISTS, BET_INSUFFICIENT, BET_OK

_CHAR_COLUMNS = (
    "c.id, c.user_id, c.name, c.class, c.race, "
    "c.str, c.dex, c.con, c.intl, c.wis, c.cha, "
    "c.level, c.xp, c.battles_fought, c.wins, c.losses, "
    "c.lifetime_damage, c.lifetime_hits, c.lifetime_crits, c.highest_hit, "
    "c.sprite_set, c.generation, c.personality, c.is_retired, c.retired_at, "
    "c.mentor_uses, c.trained_by_a, c.trained_by_b, "
    "u.login AS owner_login, u.platform AS owner_platform"
)
_CHAR_SELECT = f"SELECT {_CHAR_COLUMNS} FROM characters c JOIN users u ON u.id = c.user_id"


def _row_to_character(row: asyncpg.Record) -> Character:
    return Character(
        id=row["id"],
        user_id=row["user_id"],
        name=row["name"],
        class_name=row["class"],
        race=row["race"],
        stats={
            "STR": row["str"],
            "DEX": row["dex"],
            "CON": row["con"],
            "INT": row["intl"],
            "WIS": row["wis"],
            "CHA": row["cha"],
        },
        level=row["level"],
        xp=row["xp"],
        battles_fought=row["battles_fought"],
        wins=row["wins"],
        losses=row["losses"],
        lifetime_damage=row["lifetime_damage"],
        lifetime_hits=row["lifetime_hits"],
        lifetime_crits=row["lifetime_crits"],
        highest_hit=row["highest_hit"],
        sprite_set=row["sprite_set"],
        generation=row["generation"],
        mentor_uses=row["mentor_uses"],
        trained_by_a=row["trained_by_a"],
        trained_by_b=row["trained_by_b"],
        personality=row["personality"] or "",
        is_retired=row["is_retired"],
        retired_at=row["retired_at"],
        owner_login=row["owner_login"],
        owner_platform=row["owner_platform"],
    )


class PgStore:
    def __init__(self, pool: asyncpg.Pool, *, starting_gold: int = 100) -> None:
        self._pool = pool
        self._starting_gold = starting_gold

    @classmethod
    async def connect(
        cls, dsn: str, *, min_size: int = 1, max_size: int = 5, starting_gold: int = 100
    ) -> PgStore:
        pool = await asyncpg.create_pool(dsn, min_size=min_size, max_size=max_size)
        return cls(pool, starting_gold=starting_gold)

    async def close(self) -> None:
        await self._pool.close()

    # -- round loop --------------------------------------------------------
    async def recover(self) -> list[int]:
        rows = await self._pool.fetch(
            "UPDATE rounds SET is_voided = TRUE, ended_at = now() "
            "WHERE started_at IS NOT NULL AND ended_at IS NULL AND NOT is_voided "
            "RETURNING id"
        )
        return [r["id"] for r in rows]

    async def create_round(
        self, background: str, season_id: int | None, event: str | None = None
    ) -> int:
        return await self._pool.fetchval(
            "INSERT INTO rounds (background, season_id, event, started_at) "
            "VALUES ($1, $2, $3, now()) RETURNING id",
            background,
            season_id,
            event,
        )

    async def save_entries(self, round_id: int, entries: list[Entry]) -> None:
        async with self._pool.acquire() as con, con.transaction():
            for e in entries:
                e.entry_id = await con.fetchval(
                    "INSERT INTO round_entries "
                    "(round_id, character_id, slot, is_npc, dummy_sprite) "
                    "VALUES ($1, $2, $3, $4, $5) RETURNING id",
                    round_id,
                    e.character_id,
                    e.slot,
                    e.is_npc,
                    e.dummy_sprite,
                )

    async def flush_attacks(self, rows: list[AttackRow]) -> None:
        if not rows:
            return
        await self._pool.executemany(
            "INSERT INTO attacks (entry_id, roll, damage, is_crit, is_miss) "
            "VALUES ($1, $2, $3, $4, $5)",
            [(r.entry_id, r.roll, r.damage, r.is_crit, r.is_miss) for r in rows],
        )

    async def finalize_round(self, result: RoundResult) -> None:
        async with self._pool.acquire() as con, con.transaction():
            if result.voided:
                await con.execute(
                    "UPDATE rounds SET is_voided = TRUE, ended_at = $2 WHERE id = $1",
                    result.round_id,
                    result.ended_at,
                )
                return
            for e in result.entries:
                await con.execute(
                    "UPDATE round_entries SET total_damage=$2, hits=$3, crits=$4, misses=$5, "
                    "highest_hit=$6, placement=$7, xp_awarded=$8 WHERE id=$1",
                    e.entry_id,
                    e.total_damage,
                    e.hits,
                    e.crits,
                    e.misses,
                    e.highest_hit,
                    e.placement,
                    e.xp_awarded,
                )
            for u in result.character_updates:
                await con.execute(
                    "UPDATE characters SET battles_fought=$2, wins=$3, losses=$4, xp=$5, level=$6, "
                    "str=$7, dex=$8, con=$9, intl=$10, wis=$11, cha=$12, "
                    "lifetime_damage=$13, lifetime_hits=$14, lifetime_crits=$15, highest_hit=$16, "
                    "is_retired=$17, retired_at=$18 WHERE id=$1",
                    u.character_id,
                    u.battles_fought,
                    u.wins,
                    u.losses,
                    u.xp,
                    u.level,
                    u.stats["STR"],
                    u.stats["DEX"],
                    u.stats["CON"],
                    u.stats["INT"],
                    u.stats["WIS"],
                    u.stats["CHA"],
                    u.lifetime_damage,
                    u.lifetime_hits,
                    u.lifetime_crits,
                    u.highest_hit,
                    u.is_retired,
                    u.retired_at,
                )
            await con.execute(
                "UPDATE rounds SET winner_entry=$2, ended_at=$3 WHERE id=$1",
                result.round_id,
                result.winner_entry_id,
                result.ended_at,
            )

    async def get_living_character(self, character_id: int) -> Character | None:
        row = await self._pool.fetchrow(
            f"{_CHAR_SELECT} WHERE c.id = $1 AND NOT c.is_retired", character_id
        )
        if not row:
            return None
        ch = _row_to_character(row)
        ch.equipment = await self.get_equipment(character_id)  # R5 gear (combat needs it)
        return ch

    # -- users / characters ------------------------------------------------
    async def register_user(
        self, platform: str, platform_user_id: str, login: str, display_name: str
    ) -> int:
        return await self._pool.fetchval(
            "INSERT INTO users (platform, platform_user_id, login, display_name, gold) "
            "VALUES ($1, $2, $3, $4, $5) "
            "ON CONFLICT (platform, platform_user_id) DO UPDATE SET login = EXCLUDED.login, "
            "display_name = EXCLUDED.display_name RETURNING id",
            platform,
            platform_user_id,
            login,
            display_name,
            self._starting_gold,
        )

    async def is_banned(self, platform: str, platform_user_id: str) -> bool:
        return bool(
            await self._pool.fetchval(
                "SELECT is_banned FROM users WHERE platform = $1 AND platform_user_id = $2",
                platform,
                platform_user_id,
            )
        )

    async def set_banned(self, platform: str, identifier: str, banned: bool) -> bool:
        # Within the platform, accept either a platform_user_id or a login (mods
        # type a username). May match more than one row only if logins collide.
        result = await self._pool.execute(
            "UPDATE users SET is_banned = $3 WHERE platform = $1 "
            "AND (platform_user_id = $2 OR lower(login) = lower($2))",
            platform,
            identifier,
            banned,
        )
        # asyncpg returns e.g. 'UPDATE 1'; >0 rows means a user matched.
        return not result.endswith(" 0")

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
        row = await self._pool.fetchrow(
            "WITH gen AS (SELECT count(*) + 1 AS n FROM characters "
            "             WHERE user_id = $1 AND is_retired) "
            "INSERT INTO characters "
            "(user_id, name, class, race, str, dex, con, intl, wis, cha, sprite_set, "
            " personality, generation) "
            "SELECT $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12, gen.n FROM gen "
            "RETURNING id",
            user_id,
            name,
            class_name,
            race,
            stats["STR"],
            stats["DEX"],
            stats["CON"],
            stats["INT"],
            stats["WIS"],
            stats["CHA"],
            sprite_set,
            personality,
        )
        created = await self.get_living_character(row["id"])
        assert created is not None
        return created

    async def living_roster(self, user_id: int) -> list[Character]:
        rows = await self._pool.fetch(
            f"{_CHAR_SELECT} WHERE c.user_id = $1 AND NOT c.is_retired ORDER BY c.id", user_id
        )
        return [_row_to_character(r) for r in rows]

    async def most_recent_living(self, user_id: int) -> Character | None:
        row = await self._pool.fetchrow(
            f"{_CHAR_SELECT} WHERE c.user_id = $1 AND NOT c.is_retired "
            "ORDER BY c.id DESC LIMIT 1",
            user_id,
        )
        return _row_to_character(row) if row else None

    async def find_living(self, user_id: int, name: str) -> Character | None:
        row = await self._pool.fetchrow(
            f"{_CHAR_SELECT} WHERE c.user_id = $1 AND NOT c.is_retired "
            "AND lower(c.name) = lower($2) ORDER BY c.id DESC LIMIT 1",
            user_id,
            name,
        )
        return _row_to_character(row) if row else None

    async def find_living_any(self, name: str) -> Character | None:
        row = await self._pool.fetchrow(
            f"{_CHAR_SELECT} WHERE NOT c.is_retired AND lower(c.name) = lower($1) "
            "ORDER BY c.id DESC LIMIT 1",
            name,
        )
        return _row_to_character(row) if row else None

    async def find_retired(self, user_id: int, name: str) -> Character | None:
        row = await self._pool.fetchrow(
            f"{_CHAR_SELECT} WHERE c.user_id = $1 AND c.is_retired "
            "AND lower(c.name) = lower($2) ORDER BY c.id DESC LIMIT 1",
            user_id, name,
        )
        return _row_to_character(row) if row else None

    async def find_retired_any(self, name: str) -> Character | None:
        row = await self._pool.fetchrow(
            f"{_CHAR_SELECT} WHERE c.is_retired AND lower(c.name) = lower($1) "
            "ORDER BY c.id DESC LIMIT 1",
            name,
        )
        return _row_to_character(row) if row else None

    async def train_character(
        self, *, initiator_user_id: int, mentor_a_id: int, mentor_b_id: int, cost: int,
        name: str, class_name: str, race: str, stats: dict[str, int], sprite_set: str,
        generation: int, personality: str = "",
    ) -> Character | None:
        async with self._pool.acquire() as con, con.transaction():
            gold = await con.fetchval(
                "SELECT gold FROM users WHERE id=$1 FOR UPDATE", initiator_user_id
            )
            if gold is None or gold < cost:
                return None
            await con.execute(
                "UPDATE users SET gold = gold - $2 WHERE id=$1", initiator_user_id, cost
            )
            await con.execute(
                "UPDATE characters SET mentor_uses = mentor_uses + 1 WHERE id = ANY($1::bigint[])",
                [mentor_a_id, mentor_b_id],
            )
            cid = await con.fetchval(
                "INSERT INTO characters (user_id, name, class, race, str, dex, con, intl, "
                " wis, cha, sprite_set, personality, generation, trained_by_a, trained_by_b) "
                "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15) RETURNING id",
                initiator_user_id, name, class_name, race,
                stats["STR"], stats["DEX"], stats["CON"], stats["INT"], stats["WIS"], stats["CHA"],
                sprite_set, personality, generation, mentor_a_id, mentor_b_id,
            )
        return await self.get_living_character(cid)

    async def retire_character(self, character_id: int) -> None:
        await self._pool.execute(
            "UPDATE characters SET is_retired = TRUE, retired_at = now() "
            "WHERE id = $1 AND NOT is_retired",
            character_id,
        )

    async def rename_character(self, character_id: int, new_name: str) -> bool:
        result = await self._pool.execute(
            "UPDATE characters SET name = $2 WHERE id = $1", character_id, new_name
        )
        return result.endswith("1")

    async def top_by_damage(self, limit: int) -> list[Character]:
        rows = await self._pool.fetch(
            f"{_CHAR_SELECT} WHERE c.lifetime_damage > 0 "
            "ORDER BY c.lifetime_damage DESC LIMIT $1",
            limit,
        )
        return [_row_to_character(r) for r in rows]

    async def top_by_wins(self, limit: int) -> list[Character]:
        rows = await self._pool.fetch(
            f"{_CHAR_SELECT} WHERE c.wins > 0 "
            "ORDER BY c.wins DESC, c.lifetime_damage DESC LIMIT $1",
            limit,
        )
        return [_row_to_character(r) for r in rows]

    # -- seasons / hall of fame --------------------------------------------
    async def ensure_current_season(self, now: datetime) -> int:
        found = await self._pool.fetchval(
            "SELECT id FROM seasons WHERE $1 >= starts_at AND $1 < ends_at "
            "ORDER BY starts_at DESC LIMIT 1",
            now,
        )
        if found is not None:
            return found
        starts = datetime(now.year, now.month, 1, tzinfo=UTC)
        end_year = now.year + (1 if now.month == 12 else 0)
        end_month = 1 if now.month == 12 else now.month + 1
        ends = datetime(end_year, end_month, 1, tzinfo=UTC)
        n = (await self._pool.fetchval("SELECT count(*) FROM seasons")) + 1
        return await self._pool.fetchval(
            "INSERT INTO seasons (name, starts_at, ends_at) VALUES ($1, $2, $3) RETURNING id",
            f"Season {n} - {starts:%B %Y}",
            starts,
            ends,
        )

    async def season_leaderboard(self, season_id: int, by: str, limit: int) -> list[LeaderRow]:
        if by == "wins":
            rows = await self._pool.fetch(
                "SELECT c.name AS name, count(*) AS value FROM round_entries re "
                "JOIN rounds r ON r.id = re.round_id JOIN characters c ON c.id = re.character_id "
                "WHERE r.season_id = $1 AND NOT r.is_voided AND re.placement = 1 "
                "GROUP BY c.id, c.name ORDER BY value DESC LIMIT $2",
                season_id,
                limit,
            )
        else:  # "damage"
            rows = await self._pool.fetch(
                "SELECT c.name AS name, sum(re.total_damage) AS value FROM round_entries re "
                "JOIN rounds r ON r.id = re.round_id JOIN characters c ON c.id = re.character_id "
                "WHERE r.season_id = $1 AND NOT r.is_voided "
                "GROUP BY c.id, c.name HAVING sum(re.total_damage) > 0 "
                "ORDER BY value DESC LIMIT $2",
                season_id,
                limit,
            )
        return [LeaderRow(name=r["name"], value=int(r["value"])) for r in rows]

    async def update_hall_of_fame(self, candidates: list[HoFCandidate]) -> None:
        if not candidates:
            return
        async with self._pool.acquire() as con, con.transaction():
            for c in candidates:
                await con.execute(
                    "INSERT INTO hall_of_fame (record_key, character_id, value, achieved_at) "
                    "VALUES ($1, $2, $3, now()) "
                    "ON CONFLICT (record_key) DO UPDATE SET character_id = EXCLUDED.character_id, "
                    "value = EXCLUDED.value, achieved_at = now() "
                    "WHERE EXCLUDED.value > hall_of_fame.value",
                    c.record_key,
                    c.character_id,
                    c.value,
                )

    async def hall_of_fame(self) -> list[HoFRecord]:
        rows = await self._pool.fetch(
            "SELECT h.record_key, h.character_id, h.value, h.achieved_at, c.name AS name "
            "FROM hall_of_fame h LEFT JOIN characters c ON c.id = h.character_id"
        )
        by_key = {r["record_key"]: r for r in rows}
        out: list[HoFRecord] = []
        for key in content.HOF_KEYS:
            r = by_key.get(key)
            if r is None:
                continue
            out.append(
                HoFRecord(
                    record_key=key,
                    character_id=r["character_id"],
                    character_name=r["name"] or "?",
                    value=float(r["value"]),
                    achieved_at=r["achieved_at"],
                )
            )
        return out

    # -- economy / betting -------------------------------------------------
    async def get_gold(self, user_id: int) -> int:
        val = await self._pool.fetchval("SELECT gold FROM users WHERE id = $1", user_id)
        return int(val or 0)

    async def award_gold(self, user_ids: list[int], amount: int) -> None:
        if not user_ids or amount == 0:
            return
        await self._pool.execute(
            "UPDATE users SET gold = gold + $2 WHERE id = ANY($1::bigint[])", user_ids, amount
        )

    async def place_bet(self, round_id: int, user_id: int, slot: int, amount: int) -> str:
        async with self._pool.acquire() as con, con.transaction():
            if await con.fetchval(
                "SELECT 1 FROM bets WHERE round_id = $1 AND user_id = $2", round_id, user_id
            ):
                return BET_EXISTS
            bal = await con.fetchval("SELECT gold FROM users WHERE id = $1 FOR UPDATE", user_id)
            if bal is None or bal < amount:
                return BET_INSUFFICIENT
            await con.execute("UPDATE users SET gold = gold - $2 WHERE id = $1", user_id, amount)
            await con.execute(
                "INSERT INTO bets (round_id, user_id, slot, amount) VALUES ($1, $2, $3, $4)",
                round_id, user_id, slot, amount,
            )
            return BET_OK

    async def bets_for_round(self, round_id: int) -> list[Bet]:
        rows = await self._pool.fetch(
            "SELECT user_id, slot, amount FROM bets WHERE round_id = $1", round_id
        )
        return [Bet(user_id=r["user_id"], slot=r["slot"], amount=r["amount"]) for r in rows]

    async def settle_bets(self, round_id: int, payouts: dict[int, int]) -> None:
        async with self._pool.acquire() as con, con.transaction():
            rows = await con.fetch("SELECT user_id FROM bets WHERE round_id = $1", round_id)
            for r in rows:
                pay = payouts.get(r["user_id"], 0)
                await con.execute(
                    "UPDATE bets SET payout = $3 WHERE round_id = $1 AND user_id = $2",
                    round_id, r["user_id"], pay,
                )
                if pay:
                    await con.execute(
                        "UPDATE users SET gold = gold + $2 WHERE id = $1", r["user_id"], pay
                    )

    # -- EventSub rewards --------------------------------------------------
    async def mark_processed(self, event_id: str) -> bool:
        row = await self._pool.fetchval(
            "INSERT INTO processed_events (event_id) VALUES ($1) "
            "ON CONFLICT (event_id) DO NOTHING RETURNING event_id",
            event_id,
        )
        return row is not None

    async def grant_tokens(self, user_id: int, kind: str, amount: int) -> None:
        col = _TOKEN_COLUMN[kind]  # whitelisted column name
        await self._pool.execute(
            f"UPDATE users SET {col} = {col} + $2 WHERE id = $1", user_id, amount
        )

    async def get_tokens(self, user_id: int, kind: str) -> int:
        col = _TOKEN_COLUMN[kind]
        val = await self._pool.fetchval(f"SELECT {col} FROM users WHERE id = $1", user_id)
        return int(val or 0)

    async def consume_token(self, user_id: int, kind: str) -> bool:
        col = _TOKEN_COLUMN[kind]
        row = await self._pool.fetchval(
            f"UPDATE users SET {col} = {col} - 1 WHERE id = $1 AND {col} > 0 RETURNING id",
            user_id,
        )
        return row is not None

    async def set_character_stats(self, character_id: int, stats: dict[str, int]) -> None:
        await self._pool.execute(
            "UPDATE characters SET str=$2, dex=$3, con=$4, intl=$5, wis=$6, cha=$7 WHERE id=$1",
            character_id,
            stats["STR"], stats["DEX"], stats["CON"], stats["INT"], stats["WIS"], stats["CHA"],
        )

    async def get_game_state(self, key: str) -> str | None:
        return await self._pool.fetchval("SELECT value FROM game_state WHERE key=$1", key)

    async def set_game_state(self, key: str, value: str) -> None:
        await self._pool.execute(
            "INSERT INTO game_state (key, value, updated_at) VALUES ($1, $2, now()) "
            "ON CONFLICT (key) DO UPDATE SET value=$2, updated_at=now()",
            key, value,
        )

    async def credit_gold(self, user_id: int, amount: int) -> None:
        if amount:
            await self._pool.execute(
                "UPDATE users SET gold = gold + $2 WHERE id = $1", user_id, amount
            )

    async def get_equipment(self, character_id: int) -> dict[str, str]:
        rows = await self._pool.fetch(
            "SELECT slot, item_id FROM character_equipment WHERE character_id=$1", character_id
        )
        return {r["slot"]: r["item_id"] for r in rows}

    async def buy_item(
        self, user_id: int, character_id: int, slot: str, item_id: str, price: int
    ) -> str:
        from .store import SHOP_INSUFFICIENT, SHOP_OK, SHOP_OWNED

        async with self._pool.acquire() as con, con.transaction():
            owned = await con.fetchval(
                "SELECT 1 FROM character_items WHERE character_id=$1 AND item_id=$2",
                character_id, item_id,
            )
            if owned:
                return SHOP_OWNED  # no charge; caller may re-equip for free
            gold = await con.fetchval(
                "SELECT gold FROM users WHERE id=$1 FOR UPDATE", user_id
            )
            if gold is None or gold < price:
                return SHOP_INSUFFICIENT
            await con.execute("UPDATE users SET gold = gold - $2 WHERE id=$1", user_id, price)
            await con.execute(
                "INSERT INTO character_items (character_id, item_id) VALUES ($1, $2) "
                "ON CONFLICT DO NOTHING",
                character_id, item_id,
            )
            # Equip it; the previously equipped item stays in character_items.
            await con.execute(
                "INSERT INTO character_equipment (character_id, slot, item_id) "
                "VALUES ($1, $2, $3) ON CONFLICT (character_id, slot) "
                "DO UPDATE SET item_id=$3, purchased_at=now()",
                character_id, slot, item_id,
            )
        return SHOP_OK

    # -- gear inventory (migration 0007) ------------------------------------
    async def get_inventory(self, character_id: int) -> list[str]:
        rows = await self._pool.fetch(
            "SELECT item_id FROM character_items WHERE character_id=$1 ORDER BY acquired_at",
            character_id,
        )
        return [r["item_id"] for r in rows]

    async def add_item(self, character_id: int, item_id: str) -> None:
        await self._pool.execute(
            "INSERT INTO character_items (character_id, item_id) VALUES ($1, $2) "
            "ON CONFLICT DO NOTHING",
            character_id, item_id,
        )

    async def equip_item(self, character_id: int, slot: str, item_id: str) -> bool:
        # Single statement: equips only when the item is owned (no TOCTOU window).
        result = await self._pool.execute(
            "INSERT INTO character_equipment (character_id, slot, item_id) "
            "SELECT $1, $2, $3 WHERE EXISTS "
            "  (SELECT 1 FROM character_items WHERE character_id=$1 AND item_id=$3) "
            "ON CONFLICT (character_id, slot) DO UPDATE SET item_id=$3, purchased_at=now()",
            character_id, slot, item_id,
        )
        return not result.endswith(" 0")

    async def unequip_item(self, character_id: int, slot: str) -> bool:
        result = await self._pool.execute(
            "DELETE FROM character_equipment WHERE character_id=$1 AND slot=$2",
            character_id, slot,
        )
        return not result.endswith(" 0")

    # -- website reads -------------------------------------------------------
    async def retired_roster(self, user_id: int) -> list[Character]:
        rows = await self._pool.fetch(
            f"{_CHAR_SELECT} WHERE c.user_id = $1 AND c.is_retired "
            "ORDER BY c.retired_at DESC NULLS LAST, c.id DESC",
            user_id,
        )
        return [_row_to_character(r) for r in rows]

    async def get_character(self, character_id: int) -> Character | None:
        row = await self._pool.fetchrow(f"{_CHAR_SELECT} WHERE c.id = $1", character_id)
        if not row:
            return None
        ch = _row_to_character(row)
        ch.equipment = await self.get_equipment(character_id)
        return ch
