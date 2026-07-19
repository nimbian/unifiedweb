"""Domain data structures shared by the round loop, the store, and events.

These mirror the Postgres schema (``db/migrations/0001_initial.sql``) but are the
in-memory representation the game logic works with. Game rules live in
``rules.py``; these are plain data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Character:
    """A character as the game logic sees it. ``stats`` are the *current* ability
    scores including accumulated per-level primary bumps (PLAN.md §4.5), matching
    how the schema stores them."""

    id: int
    user_id: int | None  # None for house NPCs
    name: str
    class_name: str
    race: str
    stats: dict[str, int]  # keyed by config.STAT_NAMES
    level: int = 1
    xp: int = 0
    battles_fought: int = 0
    wins: int = 0
    losses: int = 0
    lifetime_damage: int = 0
    lifetime_hits: int = 0
    lifetime_crits: int = 0
    highest_hit: int = 0
    sprite_set: str = ""
    generation: int = 1
    # R6 co-training: how many times this (retired) character has mentored, and the
    # two parent character ids if it was itself trained (lineage display).
    mentor_uses: int = 0
    trained_by_a: int | None = None
    trained_by_b: int | None = None
    personality: str = ""  # cosmetic flavor trait shown at round start (PLAN.md §7)
    # R5 shop: equipped items keyed by slot ("weapon"/"armor"/"trinket") -> item_id.
    # Per-character; dies with the character at retirement (gold persists on the user).
    equipment: dict[str, str] = field(default_factory=dict)
    is_retired: bool = False
    retired_at: datetime | None = None
    is_npc: bool = False
    # Denormalized owner identity for round events / the overlay platform badge.
    owner_login: str | None = None      # platform handle (users.login)
    owner_platform: str | None = None   # 'twitch' | 'youtube' | 'tiktok' (users.platform)

    def copy(self) -> Character:
        """A detached copy — the store hands these out so callers can't mutate
        persistent state directly (only the store writes)."""
        from dataclasses import replace

        return replace(self, stats=dict(self.stats), equipment=dict(self.equipment))


@dataclass
class Entry:
    """One fighter slot in a round: display info + live combat accumulators.

    Persisted to ``round_entries``; ``character_id`` is None for NPC fill.
    """

    slot: int
    character_id: int | None
    is_npc: bool
    dummy_sprite: str
    name: str
    class_name: str
    sprite_set: str
    owner: str | None
    owner_platform: str | None = None  # for the overlay platform badge (PLAN.md §6.5)
    race: str = ""  # drives race passives during combat (PLAN.md §4.3)
    personality: str = ""  # cosmetic flavor trait shown at round start (PLAN.md §7)
    # R5 equipped gear (slot -> item_id) for the overlay's paper-doll layers; the
    # client maps each slot to a sprite layer by convention. Empty for NPCs / when
    # the shop is off. Cosmetic-only view state — combat grants come from the gear
    # bundle resolved separately in the round loop.
    equipment: dict[str, str] = field(default_factory=dict)
    # combat parameters resolved at roster lock
    primary_val: int = 0
    secondary_val: int = 0
    # Full level-adjusted ability block, kept so the moore engine (R1) can derive
    # all seven Core Stats (CON→Health, DEX→AC, CHA→Loot, …); the classic engine
    # only needs primary_val/secondary_val.
    stats: dict[str, int] = field(default_factory=dict)
    attack_interval: float = 0.0
    cast_at: float | None = None  # signature-ability cast time this round (PLAN.md §4.2)
    # RAW float accumulators — the source of truth during combat (PLAN.md §4.4.5).
    raw_total: float = 0.0
    raw_highest: float = 0.0
    # Display/persistence projections of the raw accumulators (scaled + rounded).
    total_damage: int = 0
    hits: int = 0
    crits: int = 0
    misses: int = 0
    highest_hit: int = 0
    # R4 monster battles: seconds into combat when this fighter was knocked out
    # (None = stayed conscious), and whether it was the round MVP (top damage on a
    # team victory). Both stay at their defaults in damage-race rounds.
    was_ko_at: float | None = None
    is_mvp: bool = False
    # assigned by the store / results
    entry_id: int | None = None
    placement: int | None = None
    xp_awarded: int = 0


@dataclass
class AttackRow:
    """A single logged swing (~200/round), destined for the ``attacks`` table."""

    entry_id: int | None
    roll: int
    damage: int
    is_crit: bool
    is_miss: bool


@dataclass
class CharacterUpdate:
    """Absolute post-round character state, computed by the round loop and handed
    to the store to persist. Absolute (not deltas) so the store stays logic-free.
    """

    character_id: int
    battles_fought: int
    wins: int
    losses: int
    xp: int
    level: int
    stats: dict[str, int]
    lifetime_damage: int
    lifetime_hits: int
    lifetime_crits: int
    highest_hit: int
    is_retired: bool
    retired_at: datetime | None


@dataclass
class RoundResult:
    """Everything the store needs to finalize a round in one transaction."""

    round_id: int
    ended_at: datetime
    entries: list[Entry]
    character_updates: list[CharacterUpdate] = field(default_factory=list)
    winner_entry_id: int | None = None
    voided: bool = False


@dataclass
class LeaderRow:
    """One row of a leaderboard (season or all-time): a character name + its
    board value (season/lifetime damage, or win count)."""

    name: str
    value: int


@dataclass
class HoFCandidate:
    """A per-round candidate for a Hall-of-Fame record. The store keeps it only if
    it beats the stored record for ``record_key`` (an all-time high-water mark)."""

    record_key: str
    character_id: int
    value: float


@dataclass
class Bet:
    """One chat bet on a round (PLAN.md §6.6). ``amount`` is already deducted from
    the bettor's gold at placement; ``slot`` is the fighter bet on."""

    user_id: int
    slot: int
    amount: int


@dataclass
class HoFRecord:
    """A held Hall-of-Fame record (all-time; survives season resets, PLAN.md §8)."""

    record_key: str
    character_id: int | None
    character_name: str
    value: float
    achieved_at: datetime | None
