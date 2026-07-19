"""Core game rules: stat generation, the attack roll / damage formula, and the
XP / leveling / placement math.

Everything here is **pure** (no I/O, no global RNG) and deterministic given an
injected ``random.Random``. This is the only place game math lives, and it is
unit-tested before any integration (see ``tests/test_rules.py``). The server and
the headless simulator both call into this module so they can never diverge.

Reference: ``docs/PLAN.md`` §4. Where PLAN.md and this code disagree, PLAN.md
wins — flag it, don't silently deviate.
"""

from __future__ import annotations

import random
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace

from .config import (
    NEUTRAL_RACE,
    STAT_NAMES,
    AbilityDef,
    ArenaEvent,
    ClassDef,
    CombatConfig,
    DamageConfig,
    MonsterTier,
    RacePassives,
    ShopItem,
    StatConfig,
    TrainingConfig,
    XpConfig,
)

StatBlock = dict[str, int]  # keyed by STAT_NAMES, values 6..18 at creation


# ---------------------------------------------------------------------------
# 4.1 Stat generation
# ---------------------------------------------------------------------------
def roll_die(rng: random.Random, cfg: StatConfig) -> int:
    """Roll one die, rerolling any result below ``reroll_below`` until it isn't.

    With the default config (d6, reroll_below=2) this yields a uniform 2..6:
    every natural 1 is rerolled until it isn't a 1.
    """
    while True:
        value = rng.randint(1, cfg.sides)
        if value >= cfg.reroll_below:
            return value


def roll_stat(rng: random.Random, cfg: StatConfig) -> int:
    """Roll one ability score: roll ``dice`` dice, drop the lowest, keep the top
    ``keep``. Default (4d6 reroll-1s, keep 3) gives 6..18, skewed high."""
    dice = sorted(roll_die(rng, cfg) for _ in range(cfg.dice))
    return sum(dice[cfg.dice - cfg.keep :])  # keep the highest `keep` dice


def roll_stat_block(rng: random.Random, cfg: StatConfig) -> StatBlock:
    """Roll a full six-stat block (STR, DEX, CON, INT, WIS, CHA)."""
    return {name: roll_stat(rng, cfg) for name in STAT_NAMES}


# ---------------------------------------------------------------------------
# 4.4 The attack roll / damage formula
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class AttackResult:
    roll: int  # raw d20, 1..20
    damage: float  # RAW float damage (pre display-scale); 0.0 on a miss
    is_crit: bool
    is_miss: bool


def attack_multiplier(roll: int, cfg: DamageConfig) -> float:
    """Multiplier for a raw d20 roll in 2..19. Rolls 1 (miss) and 20 (crit) are
    handled by ``resolve_attack`` and are not valid inputs here."""
    if not 2 <= roll <= 19:
        raise ValueError(f"attack_multiplier only defined for rolls 2..19, got {roll}")
    return cfg.roll_multipliers[roll - 2]


def display_damage(raw: float, cfg: DamageConfig) -> int:
    """Convert a raw float damage value to the on-screen / persisted integer.

    This is the single display/persistence boundary where the ×display_scale is
    applied and rounding happens (PLAN.md §4.4.5). Everything internal stays a
    float so fast/low-coefficient classes aren't penalized by per-hit rounding.
    """
    return round(raw * cfg.display_scale)


def resolve_attack(
    roll: int,
    primary_val: int,
    secondary_val: int,
    class_def: ClassDef,
    cfg: DamageConfig,
) -> AttackResult:
    """Resolve a single swing given an already-rolled d20, returning RAW float
    damage (accumulate as float; scale + round only at the display/persistence
    boundary via :func:`display_damage`).

    raw = coeff * ((PS * mult) + SS)
      - Natural 1  -> MISS, 0 damage.
      - Natural 20 -> CRIT: coeff * ((PS * crit_primary_mult) + SS) * crit_final_mult.
      - Rolls 2..19 use the multiplier table.

    The secondary stat is a flat consistency bonus and is NOT multiplied by the
    roll (except by the crit final multiplier, per the formula above).
    """
    if not 1 <= roll <= 20:
        raise ValueError(f"d20 roll out of range: {roll}")
    coeff = class_def.coeff
    if roll == 1:
        return AttackResult(roll=1, damage=0.0, is_crit=False, is_miss=True)
    if roll == 20:
        raw = (primary_val * cfg.crit_primary_mult + secondary_val) * cfg.crit_final_mult
        return AttackResult(roll=20, damage=coeff * raw, is_crit=True, is_miss=False)
    mult = cfg.roll_multipliers[roll - 2]
    return AttackResult(roll=roll, damage=coeff * (primary_val * mult + secondary_val),
                        is_crit=False, is_miss=False)


def roll_attack(
    rng: random.Random,
    primary_val: int,
    secondary_val: int,
    class_def: ClassDef,
    cfg: DamageConfig,
) -> AttackResult:
    """Roll a d20 server-side and resolve the swing."""
    return resolve_attack(rng.randint(1, 20), primary_val, secondary_val, class_def, cfg)


def attacks_in_window(attack_interval: float, combat_seconds: int) -> int:
    """How many swings a fighter gets in a combat window: one every
    ``attack_interval`` seconds (at t = interval, 2*interval, ... <= window)."""
    return int(combat_seconds // attack_interval)


@dataclass
class FighterTotals:
    total_damage: float  # RAW float sum (scale + round only for display/persistence)
    hits: int  # landed swings (rolls 2..20); crits are a subset of hits
    crits: int
    misses: int  # natural 1s
    highest_hit: float  # RAW float largest single hit


def _accumulate(
    rolls: Iterable[int],
    primary_val: int,
    secondary_val: int,
    class_def: ClassDef,
    cfg: DamageConfig,
) -> FighterTotals:
    """Aggregate a sequence of d20 ``rolls`` into a fighter's round totals as RAW
    floats. Shared by the rolled path (:func:`simulate_fighter`) and the
    common-random-numbers path (:func:`tally_fighter`), and kept numerically
    identical to :func:`resolve_attack` (verified by a unit test)."""
    coeff = class_def.coeff
    table = cfg.roll_multipliers
    crit_p = cfg.crit_primary_mult
    crit_f = cfg.crit_final_mult
    total = 0.0
    highest = 0.0
    hits = crits = misses = 0
    for roll in rolls:
        if roll == 1:
            misses += 1
            continue
        hits += 1
        if roll == 20:
            crits += 1
            dmg = coeff * ((primary_val * crit_p + secondary_val) * crit_f)
        else:
            dmg = coeff * (primary_val * table[roll - 2] + secondary_val)
        total += dmg
        if dmg > highest:
            highest = dmg
    return FighterTotals(
        total_damage=total, hits=hits, crits=crits, misses=misses, highest_hit=highest
    )


def simulate_fighter(
    rng: random.Random,
    primary_val: int,
    secondary_val: int,
    class_def: ClassDef,
    cfg: DamageConfig,
    n_attacks: int,
) -> FighterTotals:
    """Roll ``n_attacks`` d20s and aggregate the round totals (the hot path for
    the simulator's independent-luck mode and the live round loop)."""
    return _accumulate(
        (rng.randint(1, 20) for _ in range(n_attacks)),
        primary_val,
        secondary_val,
        class_def,
        cfg,
    )


def tally_fighter(
    rolls: Sequence[int],
    primary_val: int,
    secondary_val: int,
    class_def: ClassDef,
    cfg: DamageConfig,
) -> FighterTotals:
    """Aggregate over a GIVEN d20 sequence — used for common random numbers, where
    every fighter in a round reads from one shared d20 stream (PLAN.md §9)."""
    return _accumulate(rolls, primary_val, secondary_val, class_def, cfg)


# ---------------------------------------------------------------------------
# 4.3 Race passives
# ---------------------------------------------------------------------------
def apply_creation_bonus(block: StatBlock, passives: RacePassives) -> StatBlock:
    """Apply a race's creation-time stat bumps (Human +1 all, Dwarf +2 CON) to a
    freshly rolled stat block. Returns a new block; the caller persists it, so the
    bonus is baked into the character's stored stats and needs no combat-time
    handling. A no-op for neutral races (returns a copy)."""
    out = dict(block)
    if passives.all_stats_bonus:
        for s in STAT_NAMES:
            out[s] += passives.all_stats_bonus
    if passives.con_bonus:
        out["CON"] += passives.con_bonus
    return out


def effective_interval(base_interval: float, passives: RacePassives) -> float:
    """Attack interval after the race's attack-speed passive (Goblin +10% speed
    shortens the interval). Feeds ``attacks_in_window`` and the arena timeline."""
    return base_interval / passives.attack_speed_mult


@dataclass
class CombatState:
    """Per-fighter, per-round mutable state threaded through every swing. Race
    fields: the 1-based swing ordinal (Orc first hit, Dragonborn every-Nth) and
    remaining Halfling natural-1 rerolls. Ability fields, set at cast by
    :func:`cast_ability`: a timed damage-buff window (Rage/Curse), a no-miss
    counter (Second Wind), and a crit-buff counter + magnitude (Backstab)."""

    attack_index: int = 0
    lucky_left: int = 0
    # Signature-ability effects (inactive by default -> a no-op on every swing).
    no_miss_left: int = 0
    crit_buff_left: int = 0
    crit_buff_mag: float = 0.0
    buff_mult: float = 1.0
    buff_start: float = 0.0
    buff_until: float = -1.0


def apply_event_damage(dmg: float, event: ArenaEvent | None, passives: RacePassives) -> float:
    """Layer an arena event's global damage effects onto an already-computed raw
    hit (PLAN.md §4.6): the uniform ``damage_mult`` (Fire/Curse — skipped for a
    ``curse_immune`` race under a ``curse`` event, i.e. Dwarf) and the matching
    race's ``event_damage_bonus`` (Tiefling/Aasimar when the event ``tag`` is in
    their ``event_tags``). A no-op when ``event`` is None. Shared by auto-attacks
    and ability bursts so both feel the event identically."""
    if event is None:
        return dmg
    if not (event.curse and passives.curse_immune):
        dmg *= event.damage_mult
    if event.tag and event.tag in passives.event_tags:
        dmg *= 1.0 + passives.event_damage_bonus
    return dmg


def resolve_race_attack(
    rng: random.Random,
    primary_val: int,
    secondary_val: int,
    class_def: ClassDef,
    cfg: DamageConfig,
    passives: RacePassives,
    state: CombatState,
    swing_time: float = 0.0,
    event: ArenaEvent | None = None,
) -> AttackResult:
    """One swing with race passives, active ability effects, AND the round's arena
    event, returning RAW float damage. Mutates ``state``. With neutral passives, no
    active ability (the default ``CombatState``), and no event, this is numerically
    AND rng-identical to :func:`resolve_attack` (one ``randint`` per swing, no extra
    draws), so the tuned baseline is preserved exactly.

    Race: Halfling (reroll the round's first natural 1), Elf (upgrade a hit to a
    crit), Goblin (``damage_mult``), Orc (first swing ``first_hit_mult``),
    Dragonborn (bonus every Nth swing). Ability: Second Wind (``no_miss_left`` —
    a natural 1 lands as the minimum hit), Backstab (``crit_buff_left`` adds crit
    chance to the next landed hit), Rage/Curse (``buff_mult`` on swings inside
    ``[buff_start, buff_until]``). Event (PLAN.md §4.6): Blessing (``no_miss``),
    Rain (``crit_chance_bonus`` < 0), Fog/Blood Moon (``crit_damage_mult``), plus
    the global ``damage_mult`` / race bonus applied via :func:`apply_event_damage`.
    Goblin attack-speed is applied upstream via :func:`effective_interval`.
    """
    state.attack_index += 1
    i = state.attack_index

    roll = rng.randint(1, 20)
    if roll == 1 and state.lucky_left > 0:
        state.lucky_left -= 1
        roll = rng.randint(1, 20)
    if state.no_miss_left > 0:
        state.no_miss_left -= 1  # Second Wind: this swing can't miss
        if roll == 1:
            roll = 2  # a natural 1 lands as the minimum hit
    if roll == 1 and event is not None and event.no_miss:
        roll = 2  # Blessing: no whiffs for anyone this round
    if roll == 1:
        return AttackResult(roll=1, damage=0.0, is_crit=False, is_miss=True)

    coeff = class_def.coeff
    is_crit = roll == 20
    crit_chance = passives.crit_chance_bonus
    if event is not None:
        crit_chance += event.crit_chance_bonus  # Rain dampens chance-based crits
    if state.crit_buff_left > 0:
        crit_chance += state.crit_buff_mag  # Backstab on the next landed hit
        state.crit_buff_left -= 1
    if not is_crit and crit_chance > 0.0 and rng.random() < crit_chance:
        is_crit = True

    if is_crit:
        raw = (primary_val * cfg.crit_primary_mult + secondary_val) * cfg.crit_final_mult
        if event is not None:
            raw *= event.crit_damage_mult  # Fog halves / Blood Moon amps crits
    else:
        raw = primary_val * cfg.roll_multipliers[roll - 2] + secondary_val
    dmg = coeff * raw * passives.damage_mult
    if i == 1:
        dmg *= passives.first_hit_mult
    if passives.breath_every and i % passives.breath_every == 0:
        avg_hit = primary_val * cfg.mean_multiplier + secondary_val
        dmg += coeff * avg_hit * passives.breath_bonus_mult
    if state.buff_start <= swing_time <= state.buff_until:
        dmg *= state.buff_mult  # Rage / Curse damage window
    dmg = apply_event_damage(dmg, event, passives)

    return AttackResult(roll=roll, damage=dmg, is_crit=is_crit, is_miss=False)


def schedule_cast(
    rng: random.Random, ability: AbilityDef | None, combat_seconds: float,
    *, lo: float = 0.2, hi: float = 0.8,
) -> float | None:
    """Pick the random mid-round cast time for a signature ability (PLAN.md §4.2),
    in ``[lo, hi] × window``. ``None`` for classes without an ability."""
    if ability is None:
        return None
    return rng.uniform(lo, hi) * combat_seconds


def pick_arena_event(
    rng: random.Random, events: dict[str, ArenaEvent], chance: float
) -> ArenaEvent | None:
    """Roll the round's arena event (PLAN.md §4.6): with probability ``chance`` pick
    one event uniformly, else ``None`` (a plain round). Selection is server-side
    (hard rule #1); the chosen event applies globally to every fighter."""
    if not events or chance <= 0.0 or rng.random() >= chance:
        return None
    return rng.choice(list(events.values()))


def cast_ability(
    state: CombatState,
    ability: AbilityDef,
    cast_at: float,
    primary_val: int,
    secondary_val: int,
    class_def: ClassDef,
    cfg: DamageConfig,
) -> tuple[float, float]:
    """Fire a signature ability at ``cast_at``: arm the buff window / counters on
    ``state`` and return ``(instant_burst_total, largest_single_burst_hit)`` —
    ``(0.0, 0.0)`` for the non-burst kinds. Deterministic (no rolls), so bursts
    are reliable signature moments and add no variance to the balance."""
    if ability.kind == "damage_buff":
        state.buff_mult = 1.0 + ability.magnitude
        state.buff_start = cast_at
        state.buff_until = cast_at + ability.duration
    elif ability.kind == "no_miss":
        state.no_miss_left = ability.count
    elif ability.kind == "crit_buff":
        state.crit_buff_left = ability.count
        state.crit_buff_mag = ability.magnitude
    elif ability.kind == "burst":
        avg_hit = primary_val * cfg.mean_multiplier + secondary_val
        per_hit = class_def.coeff * avg_hit * ability.hit_mult
        return per_hit * ability.hits, per_hit
    return 0.0, 0.0


def simulate_fighter_round(
    rng: random.Random,
    primary_val: int,
    secondary_val: int,
    class_def: ClassDef,
    cfg: DamageConfig,
    passives: RacePassives,
    ability: AbilityDef | None,
    n_attacks: int,
    interval: float,
    combat_seconds: float,
    event: ArenaEvent | None = None,
) -> FighterTotals:
    """Simulate one fighter's whole round with race passives, the signature
    ability (cast once at a random mid-round moment), AND the round's arena event
    (PLAN.md §4.6). The single shared combat core the simulator uses; the live
    arena drives the same :func:`cast_ability` / :func:`resolve_race_attack` per
    event so they can't diverge."""
    state = CombatState(lucky_left=passives.lucky_reroll_ones)
    cast_at = schedule_cast(rng, ability, combat_seconds)
    cast_pending = cast_at is not None
    total = 0.0
    highest = 0.0
    hits = crits = misses = 0
    for k in range(1, n_attacks + 1):
        swing_time = k * interval
        if cast_pending and swing_time >= cast_at:
            burst, per_hit = cast_ability(
                state, ability, cast_at, primary_val, secondary_val, class_def, cfg
            )
            burst = apply_event_damage(burst, event, passives)
            per_hit = apply_event_damage(per_hit, event, passives)
            total += burst
            highest = max(highest, per_hit)
            cast_pending = False
        res = resolve_race_attack(
            rng, primary_val, secondary_val, class_def, cfg, passives, state, swing_time, event
        )
        if res.is_miss:
            misses += 1
            continue
        hits += 1
        if res.is_crit:
            crits += 1
        total += res.damage
        if res.damage > highest:
            highest = res.damage
    if cast_pending:  # cast scheduled past the last swing — the burst still lands
        burst, per_hit = cast_ability(
            state, ability, cast_at, primary_val, secondary_val, class_def, cfg
        )
        burst = apply_event_damage(burst, event, passives)
        per_hit = apply_event_damage(per_hit, event, passives)
        total += burst
        highest = max(highest, per_hit)
    return FighterTotals(
        total_damage=total, hits=hits, crits=crits, misses=misses, highest_hit=highest
    )


def simulate_fighter_with_race(
    rng: random.Random,
    primary_val: int,
    secondary_val: int,
    class_def: ClassDef,
    cfg: DamageConfig,
    passives: RacePassives,
    n_attacks: int,
) -> FighterTotals:
    """Race-only whole-round simulation (no signature ability) — kept for the race
    unit tests. Delegates to :func:`simulate_fighter_round` with ``ability=None``."""
    return simulate_fighter_round(
        rng, primary_val, secondary_val, class_def, cfg, passives, None, n_attacks, 1.0, 1.0
    )


# ---------------------------------------------------------------------------
# R1: MooreDnD combat model (docs/R1_combat_math.md)
#
# Additive and inert under the "classic" engine. These are the pure primitives
# for the new Core-Stats / to-hit-vs-AC math: ability→core-stat derivation, the
# sorted-4d6 stat assignment, and the per-swing resolution. The round/sim/arena
# wiring and the `moore` tuner are separate increments; the classic path is
# untouched until the moore balance gate is green and the engine flag flips.
# ---------------------------------------------------------------------------
def dnd_modifier(score: int) -> int:
    """Standard D&D ability modifier: ``(score - 10) // 2`` (8–9→−1, 10–11→0,
    12–13→+1, 14–15→+2, …). Floor division matches the canonical table for the
    below-10 scores too (7→−2)."""
    return (score - 10) // 2


@dataclass(frozen=True)
class CoreStats:
    """The seven MooreDnD Core Stats derived from a character's abilities + class
    (R1 §1). Attack Power / Health / Loot are 0–1000-ish scale; Attack/Armor use
    the D&D integer scale; ``crit_damage_mult`` is a multiplier (1.6 == 160%)."""

    attack_power: float
    attack_modifier: int
    attack_speed: int
    health: float
    armor_class: int
    crit_damage_mult: float
    loot_bonus: float


def derive_core_stats(
    abilities: StatBlock, class_def: ClassDef, combat: CombatConfig
) -> CoreStats:
    """Derive Core Stats from D&D abilities (R1 §1). Attack Power scales by the
    tuned ``class_def.coeff`` (which survives from the classic model as the
    per-class balance factor) and is capped at ``combat.ap_cap``. Crit damage is
    governed by ``class_def.crit_ability`` (defaults to the secondary)."""
    primary = abilities[class_def.primary]
    attack_power = min(
        combat.ap_cap, primary * combat.ap_per_point * class_def.ap_coeff()
    )
    crit_score = abilities[class_def.crit_ability]
    crit_mult = 1.0 + (combat.crit_pp_per_point * crit_score) / 100.0
    return CoreStats(
        attack_power=attack_power,
        attack_modifier=dnd_modifier(primary),
        attack_speed=class_def.attack_speed(),
        health=combat.health_base + abilities["CON"] * combat.health_per_con,
        armor_class=class_def.base_ac + dnd_modifier(abilities["DEX"]),
        crit_damage_mult=crit_mult,
        loot_bonus=combat.loot_base + abilities["CHA"] * combat.loot_per_cha,
    )


def stat_priority(class_def: ClassDef) -> list[str]:
    """The class's six-stat priority order for sorted-4d6 assignment (R1 §2):
    primary, secondary, then the remaining four in canonical STAT_NAMES order."""
    order = [class_def.primary, class_def.secondary]
    order += [s for s in STAT_NAMES if s not in order]
    return order


def assign_sorted_stats(rolls: Sequence[int], class_def: ClassDef) -> StatBlock:
    """Assign six rolled values to abilities by the class's priority order —
    highest roll to the most important stat (R1 §2, the sorted-4d6 rule)."""
    if len(rolls) != len(STAT_NAMES):
        raise ValueError(f"expected {len(STAT_NAMES)} rolls, got {len(rolls)}")
    ranked = sorted(rolls, reverse=True)
    return dict(zip(stat_priority(class_def), ranked, strict=True))


def roll_sorted_stat_block(
    rng: random.Random, stat_cfg: StatConfig, class_def: ClassDef
) -> StatBlock:
    """Roll six 4d6-drop-lowest values and assign them into the class's priority
    order (R1 §2). All randomness server-side (hard rule #1)."""
    rolls = [roll_stat(rng, stat_cfg) for _ in STAT_NAMES]
    return assign_sorted_stats(rolls, class_def)


# ---------------------------------------------------------------------------
# R6 — cross-player co-training (docs/R4_R6_plan.md)
# ---------------------------------------------------------------------------
def sorted_stat_expectations(stat_cfg: StatConfig, *, samples: int = 40000,
                             seed: int = 0) -> list[float]:
    """Expected value of each rank of a sorted (desc) six-stat creation block —
    the regression target for training. Monte-Carlo'd from the stat config (so it
    tracks the 4d6-drop-lowest + reroll rules); deterministic under a fixed seed."""
    rng = random.Random(seed)
    n = len(STAT_NAMES)
    sums = [0.0] * n
    for _ in range(samples):
        block = sorted((roll_stat(rng, stat_cfg) for _ in range(n)), reverse=True)
        for i in range(n):
            sums[i] += block[i]
    return [s / samples for s in sums]


def training_cost(base_cost: int, mentor_uses: int) -> int:
    """Gold the trainee's owner pays: rises with the mentor's prior uses (R6)."""
    return base_cost * (1 + max(0, mentor_uses))


def blend_training_stats(
    parent_a: StatBlock, parent_b: StatBlock, child_class: ClassDef,
    expectations: Sequence[float], tcfg: TrainingConfig, rng: random.Random,
) -> StatBlock:
    """Blend two retired parents' final stats into a child's creation stats (R6).
    Per sorted rank: regress the parents' mean toward the creation expectation, add
    a small variance; clamp to the 3–18 ability range; cap the total above the
    expectation at ``max_bonus_points`` (shaving the top stats first, which bounds
    the DPS-driving primary); then assign into the child's class priority order.
    Regression + cap make repeated max-lineage training converge, not snowball."""
    n = len(STAT_NAMES)
    a_sorted = sorted(parent_a.values(), reverse=True)
    b_sorted = sorted(parent_b.values(), reverse=True)
    # Per-rank ceiling caps each stat's edge over its creation mean, which bounds the
    # DPS-driving primary (parents' *leveled* stats would otherwise clamp it to 18).
    ranked: list[int] = []
    for i in range(n):
        parent_mid = (a_sorted[i] + b_sorted[i]) / 2.0
        val = expectations[i] + tcfg.regression * (parent_mid - expectations[i])
        val += rng.uniform(-tcfg.variance, tcfg.variance)
        stat_ceiling = min(18, round(expectations[i]) + tcfg.max_bonus_points)
        ranked.append(max(3, min(stat_ceiling, round(val))))
    ranked.sort(reverse=True)
    return dict(zip(stat_priority(child_class), ranked, strict=True))


def resolve_moore_attack(
    rng: random.Random,
    core: CoreStats,
    target_ac: int,
    combat: CombatConfig,
    *,
    force_hit: bool = False,
    crit_expanded: bool = False,
) -> AttackResult:
    """One MooreDnD swing (R1 §3): roll d20; natural 1 always misses (unless
    ``force_hit``, e.g. Second Wind), natural 20 always hits and crits, otherwise
    hit iff ``d20 + attack_modifier >= target_ac``. Damage on a hit is
    ``attack_power ± uniform variance`` floored at ``min_hit``, ×crit multiplier on
    a crit. ``crit_expanded`` (Elf / Backstab) upgrades a landed hit to a crit.
    Returns RAW float damage (scaled/rounded only at the display boundary)."""
    roll = rng.randint(1, 20)
    if roll == 1 and not force_hit:
        return AttackResult(roll=1, damage=0.0, is_crit=False, is_miss=True)
    hit = force_hit or roll == 20 or (roll + core.attack_modifier) >= target_ac
    if not hit:
        return AttackResult(roll=roll, damage=0.0, is_crit=False, is_miss=True)
    # Variance is a flat term plus an optional fraction of Attack Power; the
    # proportional term keeps each class's relative per-hit swing equal (R1).
    spread = combat.damage_variance + combat.damage_variance_pct * core.attack_power
    dmg = max(combat.min_hit, core.attack_power + rng.uniform(-spread, spread))
    is_crit = roll == 20 or crit_expanded
    if is_crit:
        dmg *= core.crit_damage_mult
    return AttackResult(roll=roll, damage=dmg, is_crit=is_crit, is_miss=False)


def cast_moore_ability(
    state: CombatState, ability: AbilityDef, cast_at: float, core: CoreStats
) -> tuple[float, float]:
    """Fire a signature ability under the moore engine (R1 §4). Arms the same buff
    window / counters on ``state`` as the classic :func:`cast_ability` (those set
    engine-independent flags), and for a ``burst`` returns
    ``(total, per_hit)`` where an average moore hit is the Attack Power itself, so
    ``per_hit = attack_power × hit_mult``. ``(0.0, 0.0)`` for the non-burst kinds."""
    if ability.kind == "damage_buff":
        state.buff_mult = 1.0 + ability.magnitude
        state.buff_start = cast_at
        state.buff_until = cast_at + ability.duration
    elif ability.kind == "no_miss":
        state.no_miss_left = ability.count
    elif ability.kind == "crit_buff":
        state.crit_buff_left = ability.count
        state.crit_buff_mag = ability.magnitude
    elif ability.kind == "burst":
        per_hit = core.attack_power * ability.hit_mult
        return per_hit * ability.hits, per_hit
    return 0.0, 0.0


def resolve_moore_race_attack(
    rng: random.Random,
    core: CoreStats,
    target_ac: int,
    combat: CombatConfig,
    passives: RacePassives,
    state: CombatState,
    swing_time: float = 0.0,
    event: ArenaEvent | None = None,
) -> AttackResult:
    """One MooreDnD swing with race passives, active ability effects, AND the
    round's arena event (R1 §4–5) — the moore analogue of
    :func:`resolve_race_attack`, layering the same effects onto the moore base hit.
    With neutral passives, no active ability, and no event it is rng-identical to
    :func:`resolve_moore_attack`, so the tuned base loop is preserved.

    Race: Halfling (reroll the round's first natural 1), Elf (crit-upgrade chance),
    Goblin/Human (``damage_mult``), Orc (first-swing ``first_hit_mult``), Dragonborn
    (breath every Nth swing). Ability: Second Wind (``no_miss`` — force the hit),
    Backstab/Inspiration (``crit_buff``), Rage/Curse/Bless/Wild Shape (``buff_mult``
    window). Event handled via :func:`apply_event_damage` + crit knobs."""
    state.attack_index += 1
    i = state.attack_index

    roll = rng.randint(1, 20)
    if roll == 1 and state.lucky_left > 0:  # Halfling: reroll the round's first 1
        state.lucky_left -= 1
        roll = rng.randint(1, 20)
    force = state.no_miss_left > 0 or (event is not None and event.no_miss)
    if state.no_miss_left > 0:  # Second Wind consumes a charge
        state.no_miss_left -= 1
    if roll == 1 and not force:
        return AttackResult(roll=1, damage=0.0, is_crit=False, is_miss=True)
    if not (force or roll == 20 or roll + core.attack_modifier >= target_ac):
        return AttackResult(roll=roll, damage=0.0, is_crit=False, is_miss=True)

    is_crit = roll == 20
    crit_chance = passives.crit_chance_bonus  # Elf
    if event is not None:
        crit_chance += event.crit_chance_bonus
    if state.crit_buff_left > 0:  # Backstab / Inspiration
        crit_chance += state.crit_buff_mag
        state.crit_buff_left -= 1
    if not is_crit and crit_chance > 0.0 and rng.random() < crit_chance:
        is_crit = True

    spread = combat.damage_variance + combat.damage_variance_pct * core.attack_power
    dmg = max(combat.min_hit, core.attack_power + rng.uniform(-spread, spread))
    if is_crit:
        dmg *= core.crit_damage_mult
        if event is not None:
            dmg *= event.crit_damage_mult
    dmg *= passives.damage_mult  # Human / Goblin
    if i == 1:
        dmg *= passives.first_hit_mult  # Orc
    if passives.breath_every and i % passives.breath_every == 0:  # Dragonborn
        dmg += core.attack_power * passives.breath_bonus_mult
    if state.buff_start <= swing_time <= state.buff_until:  # Rage / Curse / Bless / …
        dmg *= state.buff_mult
    dmg = apply_event_damage(dmg, event, passives)  # Fire/Curse + Tiefling/Aasimar/Dwarf
    return AttackResult(roll=roll, damage=dmg, is_crit=is_crit, is_miss=False)


def simulate_moore_fighter_round(
    rng: random.Random,
    core: CoreStats,
    target_ac: int,
    combat: CombatConfig,
    n_attacks: int,
    *,
    passives: RacePassives = NEUTRAL_RACE,
    ability: AbilityDef | None = None,
    interval: float = 1.0,
    combat_seconds: float = 0.0,
    event: ArenaEvent | None = None,
) -> FighterTotals:
    """Simulate one fighter's whole round under the MooreDnD model with race
    passives, its signature ability (cast once mid-round), AND the arena event.
    With neutral passives + no ability + no event this reduces to the base loop
    (rng-identical to :func:`resolve_moore_attack`). Shared by the moore simulator;
    the live arena drives the same :func:`cast_moore_ability` /
    :func:`resolve_moore_race_attack` per swing so they can't diverge."""
    state = CombatState(lucky_left=passives.lucky_reroll_ones)
    cast_at = schedule_cast(rng, ability, combat_seconds)
    cast_pending = cast_at is not None
    total = 0.0
    highest = 0.0
    hits = crits = misses = 0
    for k in range(1, n_attacks + 1):
        swing_time = k * interval
        if cast_pending and swing_time >= cast_at:
            burst, per_hit = cast_moore_ability(state, ability, cast_at, core)
            burst = apply_event_damage(burst, event, passives)
            per_hit = apply_event_damage(per_hit, event, passives)
            total += burst
            highest = max(highest, per_hit)
            cast_pending = False
        res = resolve_moore_race_attack(
            rng, core, target_ac, combat, passives, state, swing_time, event
        )
        if res.is_miss:
            misses += 1
            continue
        hits += 1
        if res.is_crit:
            crits += 1
        total += res.damage
        if res.damage > highest:
            highest = res.damage
    if cast_pending:  # cast scheduled past the last swing — the burst still lands
        burst, per_hit = cast_moore_ability(state, ability, cast_at, core)
        burst = apply_event_damage(burst, event, passives)
        per_hit = apply_event_damage(per_hit, event, passives)
        total += burst
        highest = max(highest, per_hit)
    return FighterTotals(
        total_damage=total, hits=hits, crits=crits, misses=misses, highest_hit=highest
    )


# ---------------------------------------------------------------------------
# R4 — tiered monster battles (docs/R4_R6_plan.md)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Monster:
    """A resolved monster for one battle: HP sized to the team, absolute AC /
    attack / cadence from its tier. Damage to it comes from the same moore per-swing
    resolution the team uses on dummies; it swings back at fighters' Armor Class."""

    label: str
    tier: int
    hp_max: float
    ac: int
    attack_mod: int
    damage: float
    attack_interval: float
    gold_mult: float
    sprite: str = ""


def expected_team_output(cores: Sequence[CoreStats], intervals: Sequence[float],
                         combat_seconds: int) -> float:
    """Nominal max team damage over the window: Σ AttackPower × swings (every swing
    a hit, no variance). Monster HP is a fraction of this so it scales with the
    roster's level/class mix; real hit rate (< 100% vs the monster's real AC) and
    KO attrition then decide whether the team makes it."""
    return float(sum(
        core.attack_power * attacks_in_window(interval, combat_seconds)
        for core, interval in zip(cores, intervals, strict=True)
    ))


def build_monster(tier: MonsterTier, team_output: float) -> Monster:
    """Instantiate a tier's monster against this team's expected output."""
    return Monster(
        label=tier.label,
        tier=tier.tier,
        hp_max=max(1.0, tier.hp_pct_of_team * team_output),
        ac=tier.ac,
        attack_mod=tier.attack_mod,
        damage=tier.damage,
        attack_interval=tier.attack_interval,
        gold_mult=tier.gold_mult,
        sprite=tier.sprite,
    )


def resolve_monster_attack(
    rng: random.Random, monster: Monster, target_ac: int, combat: CombatConfig
) -> tuple[bool, float]:
    """The monster swings at one fighter: d20 + Attack Modifier vs the fighter's
    Armor Class (nat 1 miss, nat 20 auto-hit + ×2 crit). Returns ``(hit, damage)``
    with damage = ``monster.damage ± variance`` floored at ``min_hit``."""
    roll = rng.randint(1, 20)
    if roll == 1:
        return False, 0.0
    is_crit = roll == 20
    if not (is_crit or roll + monster.attack_mod >= target_ac):
        return False, 0.0
    spread = combat.damage_variance + combat.damage_variance_pct * monster.damage
    dmg = max(combat.min_hit, monster.damage + rng.uniform(-spread, spread))
    if is_crit:
        dmg *= 2.0
    return True, dmg


def next_ladder_tier(current_tier: int, victory: bool, max_tier: int) -> int:
    """Escalating ladder (R4): +1 tier on a team victory (capped at ``max_tier``),
    reset to tier 1 on a defeat."""
    if not victory:
        return 1
    return min(current_tier + 1, max_tier)


@dataclass
class MonsterFighterResult:
    damage_to_monster: float = 0.0
    hits: int = 0
    crits: int = 0
    misses: int = 0
    ko_at: float | None = None  # seconds into combat when knocked out, else None


@dataclass
class MonsterRoundResult:
    victory: bool
    kill_time: float | None                 # seconds to down the monster, else None
    fighters: list[MonsterFighterResult]    # parallel to the input team order
    monster_hp_remaining: float


@dataclass
class TeamFighter:
    """One combatant in a monster battle: its Core Stats, effective cadence,
    signature ability, and race passives (same inputs the damage-race loop uses)."""

    core: CoreStats
    interval: float
    ability: AbilityDef | None = None
    passives: RacePassives = NEUTRAL_RACE


def simulate_monster_round(
    rng: random.Random,
    team: Sequence[TeamFighter],
    monster: Monster,
    combat: CombatConfig,
    combat_seconds: int,
    *,
    target_selection: str = "random",
    event: ArenaEvent | None = None,
) -> MonsterRoundResult:
    """Resolve one co-op monster battle on a merged event timeline (R4). Fighters
    swing at the monster with the standard moore resolution; the monster swings back
    every ``attack_interval`` at a conscious fighter (random or top-damage aggro).
    A fighter whose accumulated damage-taken reaches its Health is KO'd and stops
    swinging. Ends early in victory when the monster's HP hits 0, else times out in
    defeat. Pure + deterministic under a seeded rng — the arena mirrors this loop."""
    n = len(team)
    states = [CombatState(lucky_left=f.passives.lucky_reroll_ones) for f in team]
    results = [MonsterFighterResult() for _ in team]
    taken = [0.0 for _ in team]           # damage taken per fighter
    conscious = [True for _ in team]
    cast_done = [False for _ in team]

    # Merge fighter swings (kind 1) + fighter casts (kind 0) + monster swings (kind 2).
    # kind orders casts before swings before monster hits at equal time; slot tiebreak.
    timeline: list[tuple[float, int, int]] = []  # (t, kind, actor_index; -1 = monster)
    cast_at: list[float | None] = []
    for i, f in enumerate(team):
        n_swings = attacks_in_window(f.interval, combat_seconds)
        timeline.extend((k * f.interval, 1, i) for k in range(1, n_swings + 1))
        ca = schedule_cast(rng, f.ability, combat_seconds)
        cast_at.append(ca)
        if ca is not None:
            timeline.append((ca, 0, i))
    n_mon = attacks_in_window(monster.attack_interval, combat_seconds)
    timeline.extend((m * monster.attack_interval, 2, -1) for m in range(1, n_mon + 1))
    timeline.sort(key=lambda item: (item[0], item[1], item[2]))

    monster_hp = monster.hp_max
    for t, kind, idx in timeline:
        if monster_hp <= 0:
            break
        if kind == 0:  # fighter signature ability cast
            if not conscious[idx]:
                continue
            burst, _per_hit = cast_moore_ability(states[idx], team[idx].ability,
                                                 cast_at[idx] or 0.0, team[idx].core)
            burst = apply_event_damage(burst, event, team[idx].passives)
            cast_done[idx] = True
            if burst:
                results[idx].damage_to_monster += burst
                monster_hp -= burst
                if monster_hp <= 0:
                    return MonsterRoundResult(True, t, results, 0.0)
            continue
        if kind == 1:  # fighter swings at the monster
            if not conscious[idx]:
                continue
            res = resolve_moore_race_attack(
                rng, team[idx].core, monster.ac, combat,
                team[idx].passives, states[idx], t, event,
            )
            if res.is_miss:
                results[idx].misses += 1
            else:
                results[idx].hits += 1
                if res.is_crit:
                    results[idx].crits += 1
                results[idx].damage_to_monster += res.damage
                monster_hp -= res.damage
                if monster_hp <= 0:
                    return MonsterRoundResult(True, t, results, 0.0)
            continue
        # kind == 2: monster swings at a conscious fighter
        targets = [i for i in range(n) if conscious[i]]
        if not targets:
            continue
        if target_selection == "aggro_top":
            victim = max(targets, key=lambda i: results[i].damage_to_monster)
        else:
            victim = targets[rng.randrange(len(targets))]
        hit, dmg = resolve_monster_attack(rng, monster, team[victim].core.armor_class, combat)
        if hit:
            taken[victim] += dmg
            if taken[victim] >= team[victim].core.health:
                conscious[victim] = False
                results[victim].ko_at = t

    return MonsterRoundResult(False, None, results, max(0.0, monster_hp))


# ---------------------------------------------------------------------------
# R5 — shop equipment + performance gold (docs/R4_R6_plan.md)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class GearBundle:
    """The summed grants of a character's equipped items. Applied to Core Stats +
    cadence at combat time; the balance gate runs naked (empty bundle)."""

    ap_mult: float = 0.0
    ac_bonus: int = 0
    speed_mult: float = 0.0
    crit_pp: float = 0.0
    loot_pp: float = 0.0


NO_GEAR = GearBundle()


def resolve_gear(items: Iterable[ShopItem]) -> GearBundle:
    """Sum a character's equipped items into one bundle."""
    ap = ac = spd = crit = loot = 0.0
    for it in items:
        ap += it.ap_mult
        ac += it.ac_bonus
        spd += it.speed_mult
        crit += it.crit_pp
        loot += it.loot_pp
    return GearBundle(ap_mult=ap, ac_bonus=int(ac), speed_mult=spd, crit_pp=crit, loot_pp=loot)


def apply_gear_to_core(core: CoreStats, gear: GearBundle, combat: CombatConfig) -> CoreStats:
    """Layer gear grants onto derived Core Stats: Attack Power ×(1+ap_mult) (still
    capped), +AC, +crit%, +loot%. Speed is applied to the interval separately
    (:func:`geared_interval`). With ``NO_GEAR`` this returns ``core`` unchanged, so
    the naked balance gate is untouched."""
    if gear is NO_GEAR or gear == NO_GEAR:
        return core
    return replace(
        core,
        attack_power=min(combat.ap_cap, core.attack_power * (1.0 + gear.ap_mult)),
        armor_class=core.armor_class + gear.ac_bonus,
        crit_damage_mult=core.crit_damage_mult + gear.crit_pp / 100.0,
        loot_bonus=core.loot_bonus + gear.loot_pp,
    )


def geared_interval(base_interval: float, gear: GearBundle) -> float:
    """Attack speed shortens the interval: interval / (1 + speed_mult)."""
    return base_interval / (1.0 + gear.speed_mult) if gear.speed_mult else base_interval


def gold_from_damage(total_damage: int, loot_bonus_pct: float, tier_mult: float) -> int:
    """R5 performance gold: damage dealt × Loot Bonus% × tier multiplier (§13.1)."""
    return max(0, round(total_damage * (loot_bonus_pct / 100.0) * tier_mult))


# ---------------------------------------------------------------------------
# 4.5 XP, leveling, retirement, placement
# ---------------------------------------------------------------------------
def cumulative_xp_for_level(level: int, cfg: XpConfig) -> int:
    """Total XP required to have reached ``level`` (from level 1).

    Triangular curve: curve_coeff * (level-1) * level / 2. Level 1 costs 0 XP,
    so a freshly created character is level 1. (PLAN.md §4.5 writes the formula
    as ``100*N*(N+1)/2``; this is that curve shifted so level 1 is the free
    starting level rather than costing 100 XP.)
    """
    if level < 1:
        raise ValueError(f"level must be >= 1, got {level}")
    return cfg.curve_coeff * (level - 1) * level // 2


def level_for_xp(xp: int, cfg: XpConfig) -> int:
    """Highest level (capped at ``levels_max``) attainable with ``xp`` total XP."""
    level = 1
    while level < cfg.levels_max and xp >= cumulative_xp_for_level(level + 1, cfg):
        level += 1
    return level


def level_after_battle(current_level: int, cfg: XpConfig) -> int:
    """R3 (PLAN.md §13.1): one completed battle grants exactly one level, capped
    at ``levels_max``. Placement is irrelevant — finishing the battle is enough.
    Voided rounds never reach here (hard rule #10), so they don't count."""
    return min(current_level + 1, cfg.levels_max)


def primary_at_level(base_primary: int, level: int, cfg: XpConfig) -> int:
    """Primary stat after level-ups: +``per_level_primary_bonus`` per level gained."""
    return base_primary + (level - 1) * cfg.per_level_primary_bonus


def xp_for_placement(placement: int, cfg: XpConfig) -> int:
    """XP awarded for finishing a round at ``placement`` (1 = winner)."""
    if placement < 1:
        raise ValueError(f"placement must be >= 1, got {placement}")
    idx = placement - 1
    bonus = cfg.placement_bonus[idx] if idx < len(cfg.placement_bonus) else 0
    return cfg.base_per_round + bonus


def is_win(placement: int) -> bool:
    """Damage-race win/loss: 1st place is a win, everything else a loss."""
    return placement == 1


# ---------------------------------------------------------------------------
# 6.6 Chat betting — pari-mutuel settlement
# ---------------------------------------------------------------------------
def settle_parimutuel(
    bets: Iterable[tuple[int, int, int]], winning_slot: int, rake: float = 0.0
) -> dict[int, int]:
    """Pari-mutuel payout. ``bets`` are ``(user_id, slot, amount)`` with the stake
    already deducted at placement. Winners split the whole pool in proportion to
    their stake on ``winning_slot``; ``rake`` (0..1) is the house take.

    Returns ``{user_id: gold_to_credit}`` for winners only (losers get 0 and are
    absent). If nobody backed the winner, every stake is refunded (payout ==
    stake) so gold isn't destroyed. A user's payout INCLUDES their returned stake.
    """
    bets = list(bets)
    total_pool = sum(amount for _, _, amount in bets)
    winning_pool = sum(amount for _, slot, amount in bets if slot == winning_slot)
    payouts: dict[int, int] = {}
    if total_pool == 0:
        return payouts
    if winning_pool == 0:  # no one backed the winner -> refund all stakes
        for user_id, _slot, amount in bets:
            payouts[user_id] = payouts.get(user_id, 0) + amount
        return payouts
    distributable = total_pool * (1.0 - rake)
    for user_id, slot, amount in bets:
        if slot == winning_slot:
            share = round(amount * distributable / winning_pool)
            payouts[user_id] = payouts.get(user_id, 0) + share
    return payouts


def should_retire(battles_fought: int, cfg_round_lifespan: int) -> bool:
    """True once a character has used up its battle lifespan."""
    return battles_fought >= cfg_round_lifespan
