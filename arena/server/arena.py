"""The authoritative round state machine (PLAN.md §5).

    INTERMISSION (90s) -> ROSTER_LOCK (10s) -> COMBAT (60s) -> RESULTS (20s) -> ...

Runs continuously and unattended. All randomness is server-side (hard rule #1);
Godot only receives the emitted event stream. The loop is decoupled from its
edges through three injected collaborators so it can run fully headless and be
unit-tested with a fake clock:

* ``store`` — persistence (``Store`` protocol); only it writes to the DB.
* ``sink``  — where events go (``EventSink``); a dead sink never stops the game.
* ``sleep`` / ``now`` / ``rng`` — clock and randomness, injected for determinism.

The chat layer (next milestone) feeds the queue via :meth:`enqueue` and reads the
event stream for announcements; the FastAPI WebSocket sink and the asyncpg store
drop in without any change to the logic here.
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from . import events, npc, rules
from .config import ArenaEvent, Config
from .models import AttackRow, Character, CharacterUpdate, Entry, HoFCandidate, RoundResult
from .store import Store


class Phase(StrEnum):
    INTERMISSION = "intermission"
    ROSTER_LOCK = "roster_lock"
    COMBAT = "combat"
    RESULTS = "results"
    PAUSED = "paused"
    IDLE = "idle"  # arena closed (mod !start opens it); no rounds run


@dataclass
class QueueItem:
    character_id: int
    user_id: int
    enqueued_at: float
    priority: bool = False  # EventSub priority token — seated first (PLAN.md §13.1)
    # Rounds spent queued but not selected, bucketed per round kind/tier (R4/§13.1):
    # "race" plus one bucket per monster tier ("tier1".."tier5"). The lottery weights
    # a character by the bucket matching the upcoming round, so someone repeatedly
    # skipped for a given tier climbs THAT tier's priority. Empty when never missed.
    misses: dict[str, int] = field(default_factory=dict)


@dataclass
class RoundContext:
    round_id: int
    background: str
    entries: list[Entry]
    chars_by_id: dict[int, Character]  # pre-round state of the real characters
    event: ArenaEvent | None = None    # the round's arena event (PLAN.md §4.6), if any
    # R4 monster battles: kind is "race" (damage race) or "monster"; for a monster
    # round, tier is the ladder tier and monster is the resolved stat block.
    kind: str = "race"
    tier: int | None = None
    monster: rules.Monster | None = None
    victory: bool | None = None        # set in results: did the team down the monster?


@dataclass
class RoundOutcome:
    round_id: int
    entries: list[Entry]
    voided: bool = False


async def _real_sleep(seconds: float) -> None:
    if seconds > 0:
        await asyncio.sleep(seconds)


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


_LADDER_KEY = "monster_ladder_tier"  # R4 game_state key for the escalating tier


def _queue_key(kind: str, tier: int | None) -> str:
    """The miss bucket the weighted lottery weights against for an upcoming round
    (R4/§13.1): damage races share one bucket, each monster tier gets its own so a
    character repeatedly skipped for a Tier-III monster round climbs Tier III's
    priority without inflating its odds for ordinary races."""
    return "race" if kind != "monster" or tier is None else f"tier{tier}"


def _weighted_index(weights: list[float], rng: random.Random) -> int:
    """Index into ``weights`` chosen with probability proportional to weight.
    All randomness is server-side (hard rule #1). Falls back to a uniform pick
    if every weight is zero."""
    total = sum(weights)
    if total <= 0:
        return rng.randrange(len(weights))
    r = rng.random() * total
    upto = 0.0
    for i, w in enumerate(weights):
        upto += w
        if r <= upto:
            return i
    return len(weights) - 1


class Arena:
    def __init__(
        self,
        cfg: Config,
        store: Store,
        sink: events.EventSink,
        *,
        rng: random.Random | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
        now: Callable[[], datetime] | None = None,
        season_id: int | None = None,
        presence: object | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.cfg = cfg
        self.store = store
        self._sink = sink
        self._rng = rng or random.Random()
        self._sleep = sleep or _real_sleep
        self._now = now or _utcnow
        self._season_id = season_id
        self._presence = presence  # economy.Presence | None (per-round gold accrual)
        self._logger = logger or logging.getLogger("dndarena.arena")

        self._queue: deque[QueueItem] = deque()
        self._current: RoundContext | None = None
        self._round_number = 0  # R4: monster battle every Nth round
        self._running = False
        self._paused = False
        self._resume_event = asyncio.Event()
        self._resume_event.set()
        self._open: bool = cfg.arena.open_on_launch
        self._open_event = asyncio.Event()
        if self._open:
            self._open_event.set()
        self._phase = Phase.INTERMISSION if self._open else Phase.IDLE

    # -- public API --------------------------------------------------------
    @property
    def phase(self) -> Phase:
        return self._phase

    @property
    def queue_size(self) -> int:
        return len(self._queue)

    @property
    def paused(self) -> bool:
        return self._paused

    # -- betting API (PLAN.md §6.6) ----------------------------------------
    @property
    def betting_open(self) -> bool:
        """Bets are accepted only while the lineup is locked and shown, before
        combat starts (the ROSTER_LOCK window)."""
        return self._phase == Phase.ROSTER_LOCK and self._current is not None

    @property
    def current_round_id(self) -> int | None:
        return self._current.round_id if self._current is not None else None

    def resolve_bet_target(self, token: str) -> tuple[int, str] | None:
        """Map a bet target (a slot number or a fighter name) to ``(slot, name)``
        in the current lineup, or ``None`` if it doesn't match."""
        if self._current is None:
            return None
        if token.isdigit():
            slot = int(token)
            for e in self._current.entries:
                if e.slot == slot:
                    return e.slot, e.name
            return None
        key = token.casefold()
        for e in self._current.entries:
            if e.name.casefold() == key:
                return e.slot, e.name
        return None

    async def enqueue(self, character_id: int, user_id: int, *, priority: bool = False) -> int:
        """Queue a character for the next round. Idempotent per character; returns
        the character's 1-based position. ``priority`` (a channel-point reward,
        PLAN.md §6.2) jumps the character to the front of the queue."""
        for i, item in enumerate(self._queue):
            if item.character_id == character_id:
                return i + 1
        item = QueueItem(character_id, user_id, self._now().timestamp(), priority=priority)
        if priority:
            self._queue.appendleft(item)
            return 1
        self._queue.append(item)
        return len(self._queue)

    def is_queued(self, character_id: int) -> bool:
        return any(item.character_id == character_id for item in self._queue)

    def is_fighting(self, character_id: int) -> bool:
        """True while the character is in the CURRENT round's locked lineup
        (retire guard: finish the round first). Phase-checked because
        ``_current`` still holds the last round during the next intermission —
        and a retire mid-round would be clobbered by finalize_round's blanket
        character UPDATE anyway."""
        if self._phase not in (Phase.ROSTER_LOCK, Phase.COMBAT, Phase.RESULTS):
            return False
        return self._current is not None and any(
            e.character_id == character_id for e in self._current.entries
        )

    def queue_view(self) -> list[QueueItem]:
        """Read-only copy of the queue for the website's arena page."""
        return list(self._queue)

    def pause(self) -> None:
        """Halt the loop after the current round finishes (mod ``!pause``)."""
        self._paused = True
        self._resume_event.clear()

    def resume(self) -> None:
        self._paused = False
        self._resume_event.set()

    @property
    def is_open(self) -> bool:
        return self._open

    def open(self) -> None:
        """Open the arena so rounds run (mod ``!start``)."""
        self._open = True
        self._open_event.set()

    def close(self) -> None:
        """Idle the arena after the current round finishes (mod ``!close``).

        Like ``pause()`` this never interrupts an in-flight round, and the
        queue is preserved — queued characters fight when a mod reopens."""
        self._open = False
        self._open_event.clear()

    def stop(self) -> None:
        self._running = False
        self._resume_event.set()
        self._open_event.set()

    def snapshot(self) -> dict:
        """A ``sync`` message for a client joining mid-round (PLAN.md §7)."""
        round_info = None
        entries: list[Entry] = []
        if self._current is not None:
            ev = self._current.event
            m = self._current.monster
            round_info = {
                "round_id": self._current.round_id,
                "background": self._current.background,
                "event": {"name": ev.name, "label": ev.label} if ev else None,
                "kind": self._current.kind,
                "tier": self._current.tier,
                # Monster layout for late joiners; the HP bar starts full and
                # self-corrects on the next monster_hp event (absolute remaining).
                "monster": (
                    {"label": m.label, "hp": round(m.hp_max)} if m is not None else None
                ),
            }
            entries = self._current.entries
        return events.sync(self._phase.value, round_info, entries)

    # -- main loop ---------------------------------------------------------
    async def run(self, max_rounds: int | None = None) -> None:
        voided = await self.store.recover()
        if voided:
            self._logger.info("recovered: voided %d unfinished round(s) %s", len(voided), voided)
        self._running = True
        completed = 0
        while self._running and (max_rounds is None or completed < max_rounds):
            # Gate: closed and/or paused — checked only between rounds, so
            # !close/!pause never interrupt an in-flight round.
            while self._running and (not self._open or self._paused):
                if not self._open:
                    self._phase = Phase.IDLE
                    self._current = None  # snapshot() must not show a stale round
                    await self._emit(events.countdown(Phase.IDLE.value, 0))
                    await self._open_event.wait()
                else:
                    self._phase = Phase.PAUSED
                    await self._emit(events.countdown(Phase.PAUSED.value, 0))
                    await self._resume_event.wait()
            if not self._running:
                break
            try:
                await self.run_once()
            except Exception:  # never let one bad round kill the loop
                self._logger.exception("round loop iteration failed; continuing")
            completed += 1

    async def run_once(self) -> RoundOutcome:
        """One full INTERMISSION→ROSTER_LOCK→COMBAT→RESULTS cycle."""
        await self._intermission()
        ctx = await self._roster_lock()
        self._current = ctx
        try:
            await self._combat(ctx)
            await self._results(ctx)
            return RoundOutcome(ctx.round_id, ctx.entries, voided=False)
        except Exception:
            self._logger.exception(
                "round %s crashed during combat/results; voiding (no lifespan consumed)",
                ctx.round_id,
            )
            await self.store.finalize_round(
                RoundResult(ctx.round_id, self._now(), ctx.entries, voided=True)
            )
            return RoundOutcome(ctx.round_id, ctx.entries, voided=True)

    # -- phases ------------------------------------------------------------
    async def _intermission(self) -> None:
        self._phase = Phase.INTERMISSION
        await self._run_countdown(Phase.INTERMISSION, self.cfg.timings.intermission_seconds)

    async def _roster_lock(self) -> RoundContext:
        self._phase = Phase.ROSTER_LOCK
        cfg = self.cfg
        n_slots = cfg.round.fighters_per_round

        # Decide the upcoming round's kind/tier BEFORE selection so the weighted
        # lottery seats from the miss bucket matching this round (R4/§13.1). The
        # monster stat block still resolves later, once the real roster is known.
        self._round_number += 1
        kind, tier = "race", None
        if cfg.monsters.enabled and self._round_number % cfg.monsters.every_n == 0:
            kind = "monster"
            tier = await self._current_ladder_tier()

        selected = await self._select_from_queue(_queue_key(kind, tier))
        combatants: list[Character] = [ch for _, ch in selected]
        chars_by_id = {ch.id: ch for _, ch in selected}

        # Fill empty slots with NPCs so the arena always looks full.
        needed = n_slots - len(combatants)
        if needed > 0:
            field_levels = [c.level for c in combatants] or [
                self._rng.randint(1, cfg.xp.levels_max)
            ]
            for _ in range(needed):
                combatants.append(npc.generate_npc(self._rng, cfg, self._rng.choice(field_levels)))

        # Arena position is cosmetic in a damage race — shuffle so NPCs and
        # players mix around the circle.
        self._rng.shuffle(combatants)

        background = self._pick(cfg.assets.get("backgrounds"), "arena")
        dummies = cfg.assets.get("dummy_sprites") or ["dummy_01"]

        entries: list[Entry] = []
        for slot, ch in enumerate(combatants):
            cd = cfg.classes[ch.class_name]
            passives = cfg.race_passives(ch.race)
            entries.append(
                Entry(
                    slot=slot,
                    character_id=None if ch.is_npc else ch.id,
                    is_npc=ch.is_npc,
                    dummy_sprite=self._rng.choice(dummies),
                    name=ch.name,
                    class_name=ch.class_name,
                    sprite_set=ch.sprite_set,
                    owner=ch.owner_login,
                    owner_platform=ch.owner_platform,
                    race=ch.race,
                    personality=ch.personality,
                    # Paper-doll gear for the overlay: only real characters carry
                    # gear, and only when the shop is live (NO_GEAR otherwise).
                    equipment=(
                        dict(ch.equipment)
                        if cfg.shop.enabled and not ch.is_npc
                        else {}
                    ),
                    primary_val=ch.stats[cd.primary],
                    secondary_val=ch.stats[cd.secondary],
                    stats=dict(ch.stats),  # full block for the moore engine (R1)
                    # Goblin +10% attack speed shortens the interval (PLAN.md §4.3);
                    # R5 gear speed_mult shortens it further (NO_GEAR when shop off).
                    attack_interval=rules.geared_interval(
                        rules.effective_interval(cd.attack_interval, passives),
                        self._gear_for(ch),
                    ),
                )
            )

        # R4: on a monster round (planned above) resolve the tier's stat block now
        # that the real roster — and thus the team's expected output — is known.
        monster = None
        if kind == "monster":
            cores = [
                rules.derive_core_stats(e.stats, cfg.classes[e.class_name], cfg.combat)
                for e in entries
            ]
            team_output = rules.expected_team_output(
                cores, [e.attack_interval for e in entries], cfg.timings.combat_seconds
            )
            monster = rules.build_monster(cfg.monsters.tier(tier), team_output)

        # Roll the round's random arena event (PLAN.md §4.6); global, server-side.
        # Monster rounds run without an arena event (their own tension mechanic).
        event = (
            None if kind == "monster"
            else rules.pick_arena_event(self._rng, cfg.events, cfg.round.event_chance)
        )

        # Auto-rollover: rounds are tagged with the current calendar-month season
        # so leaderboards reset monthly (an explicit _season_id overrides, for tests).
        season_id = (
            self._season_id
            if self._season_id is not None
            else await self.store.ensure_current_season(self._now())
        )
        round_id = await self.store.create_round(
            background, season_id, event.name if event else None
        )
        await self.store.save_entries(round_id, entries)
        event_view = {"name": event.name, "label": event.label} if event else None
        await self._emit(
            events.round_start(round_id, background, entries, event_view, kind=kind, tier=tier)
        )
        if monster is not None:
            await self._emit(events.monster_spawn(tier, monster.label, round(monster.hp_max)))
            await self._emit(
                events.ticker("monster", f"A Tier {tier} {monster.label} appears!", "house")
            )
        if event is not None:
            # Event banner (overlay cue) + a ticker mirror for feedback parity.
            await self._emit(events.arena_event(event.name, event.label))
            await self._emit(events.ticker("event", f"Arena event: {event.label}!", "house"))

        ctx = RoundContext(
            round_id, background, entries, chars_by_id,
            event=event, kind=kind, tier=tier, monster=monster,
        )
        # Expose the round now so bets can be placed during the ROSTER_LOCK window
        # (the lineup is on screen and the round id is known).
        self._current = ctx
        await self._run_countdown(Phase.ROSTER_LOCK, cfg.timings.roster_lock_seconds)
        return ctx

    async def _combat(self, ctx: RoundContext) -> None:
        """Run the combat window under the configured engine (R1). ``classic`` is
        the shipped multiplier-table model; ``moore`` is the MooreDnD Core-Stats /
        to-hit-vs-AC model (base-loop — races/abilities re-expressed in a later
        increment; arena events apply as the flat damage mod in both)."""
        if ctx.kind == "monster":
            await self._combat_monster(ctx)  # R4 (moore engine required by config)
        elif self.cfg.combat.engine == "moore":
            await self._combat_moore(ctx)
        else:
            await self._combat_classic(ctx)

    async def _tick_combat(self, elapsed: float, ticked: int, total: int) -> int:
        """Emit a `combat` countdown for each whole second crossed as combat
        advances to ``elapsed`` seconds, so the overlay shows a live fight timer
        instead of freezing on the last roster-lock tick. Driven off the combat
        timeline (not a concurrent task), so it's deterministic under any injected
        clock. ``ticked`` is how many seconds have already been emitted; returns
        the updated count."""
        target = min(int(elapsed), total)
        while ticked < target:
            ticked += 1
            await self._emit(events.countdown(Phase.COMBAT.value, total - ticked))
        return ticked

    async def _combat_classic(self, ctx: RoundContext) -> None:
        self._phase = Phase.COMBAT
        cfg = self.cfg
        dmg_cfg = cfg.damage
        combat_seconds = cfg.timings.combat_seconds

        # Merge every fighter's swing times into one ordered timeline: a fighter
        # attacks at t = interval, 2*interval, ... (floor(window/interval) swings,
        # matching the balance model in sim.py).
        # Per-fighter race passive state + ability cast times, threaded through
        # the round. Swings (kind 1) and the mid-round signature ability cast
        # (kind 0, sorts first at equal time) share one ordered timeline.
        passives = {e.slot: cfg.race_passives(e.race) for e in ctx.entries}
        states = {
            e.slot: rules.CombatState(lucky_left=passives[e.slot].lucky_reroll_ones)
            for e in ctx.entries
        }
        timeline: list[tuple[float, int, Entry]] = []
        for e in ctx.entries:
            ability = cfg.classes[e.class_name].ability
            e.cast_at = rules.schedule_cast(self._rng, ability, combat_seconds)
            n = rules.attacks_in_window(e.attack_interval, combat_seconds)
            timeline.extend((k * e.attack_interval, 1, e) for k in range(1, n + 1))
            if e.cast_at is not None:
                timeline.append((e.cast_at, 0, e))
        timeline.sort(key=lambda item: (item[0], item[1], item[2].slot))

        attack_rows: list[AttackRow] = []
        prev = 0.0
        ticked = 0
        await self._emit(events.countdown(Phase.COMBAT.value, combat_seconds))  # fight timer
        for t, kind, e in timeline:
            await self._sleep(t - prev)
            prev = t
            ticked = await self._tick_combat(prev, ticked, combat_seconds)
            cd = cfg.classes[e.class_name]
            if kind == 0:  # signature ability cast
                burst, per_hit = rules.cast_ability(
                    states[e.slot], cd.ability, e.cast_at,
                    e.primary_val, e.secondary_val, cd, dmg_cfg,
                )
                burst = rules.apply_event_damage(burst, ctx.event, passives[e.slot])
                per_hit = rules.apply_event_damage(per_hit, ctx.event, passives[e.slot])
                if burst:
                    e.raw_total += burst
                    if per_hit > e.raw_highest:
                        e.raw_highest = per_hit
                    e.total_damage = rules.display_damage(e.raw_total, dmg_cfg)
                    e.highest_hit = rules.display_damage(e.raw_highest, dmg_cfg)
                await self._emit(events.ability(e.slot, cd.ability.name))
                continue
            res = rules.resolve_race_attack(
                self._rng, e.primary_val, e.secondary_val, cd, dmg_cfg,
                passives[e.slot], states[e.slot], t, ctx.event,
            )
            # Accumulate as raw floats; project to display ints at this boundary.
            e.raw_total += res.damage
            if res.is_miss:
                e.misses += 1
            else:
                e.hits += 1
                if res.is_crit:
                    e.crits += 1
                if res.damage > e.raw_highest:
                    e.raw_highest = res.damage
            e.total_damage = rules.display_damage(e.raw_total, dmg_cfg)
            e.highest_hit = rules.display_damage(e.raw_highest, dmg_cfg)
            hit_damage = rules.display_damage(res.damage, dmg_cfg)
            attack_rows.append(
                AttackRow(e.entry_id, res.roll, hit_damage, res.is_crit, res.is_miss)
            )
            await self._emit(
                events.attack(
                    slot=e.slot,
                    roll=res.roll,
                    damage=hit_damage,
                    crit=res.is_crit,
                    miss=res.is_miss,
                    running_total=e.total_damage,
                )
            )
        # Hold the last sliver so combat lasts the full window in real time.
        await self._sleep(combat_seconds - prev)
        await self.store.flush_attacks(attack_rows)

    async def _combat_moore(self, ctx: RoundContext) -> None:
        """MooreDnD combat (R1, docs/R1_combat_math.md): derive each fighter's Core
        Stats, then swing every ``attack_interval`` — d20 + Attack Modifier vs the
        dummy AC, damage = Attack Power ± variance, ×crit on a nat 20. Damage is
        already on the 0–1000 Core-Stat scale, so it is projected to display/
        persistence with a plain round (no classic ×display_scale). Race passives,
        the signature ability (cast once mid-round), and the arena event are all
        threaded per swing, mirroring the classic path."""
        self._phase = Phase.COMBAT
        cfg = self.cfg
        combat_cfg = cfg.combat
        combat_seconds = cfg.timings.combat_seconds
        dummy_ac = combat_cfg.dummy_ac

        # Per-fighter Core Stats + race-passive state + ability cast times, merged
        # into one ordered timeline (kind 0 = cast sorts before kind 1 = swing).
        passives = {e.slot: cfg.race_passives(e.race) for e in ctx.entries}
        cores = {
            e.slot: rules.apply_gear_to_core(
                rules.derive_core_stats(e.stats, cfg.classes[e.class_name], combat_cfg),
                self._gear_for(ctx.chars_by_id.get(e.character_id)), combat_cfg,
            )
            for e in ctx.entries
        }
        states = {
            e.slot: rules.CombatState(lucky_left=passives[e.slot].lucky_reroll_ones)
            for e in ctx.entries
        }
        timeline: list[tuple[float, int, Entry]] = []
        for e in ctx.entries:
            ability = cfg.classes[e.class_name].ability
            e.cast_at = rules.schedule_cast(self._rng, ability, combat_seconds)
            n = rules.attacks_in_window(e.attack_interval, combat_seconds)
            timeline.extend((k * e.attack_interval, 1, e) for k in range(1, n + 1))
            if e.cast_at is not None:
                timeline.append((e.cast_at, 0, e))
        timeline.sort(key=lambda item: (item[0], item[1], item[2].slot))

        attack_rows: list[AttackRow] = []
        prev = 0.0
        ticked = 0
        await self._emit(events.countdown(Phase.COMBAT.value, combat_seconds))  # fight timer
        for t, kind, e in timeline:
            await self._sleep(t - prev)
            prev = t
            ticked = await self._tick_combat(prev, ticked, combat_seconds)
            cd = cfg.classes[e.class_name]
            if kind == 0:  # signature ability cast
                burst, per_hit = rules.cast_moore_ability(
                    states[e.slot], cd.ability, e.cast_at, cores[e.slot]
                )
                burst = rules.apply_event_damage(burst, ctx.event, passives[e.slot])
                per_hit = rules.apply_event_damage(per_hit, ctx.event, passives[e.slot])
                if burst:
                    e.raw_total += burst
                    if per_hit > e.raw_highest:
                        e.raw_highest = per_hit
                    e.total_damage = round(e.raw_total)
                    e.highest_hit = round(e.raw_highest)
                await self._emit(events.ability(e.slot, cd.ability.name))
                continue
            res = rules.resolve_moore_race_attack(
                self._rng, cores[e.slot], dummy_ac, combat_cfg,
                passives[e.slot], states[e.slot], t, ctx.event,
            )
            e.raw_total += res.damage
            if res.is_miss:
                e.misses += 1
            else:
                e.hits += 1
                if res.is_crit:
                    e.crits += 1
                if res.damage > e.raw_highest:
                    e.raw_highest = res.damage
            e.total_damage = round(e.raw_total)
            e.highest_hit = round(e.raw_highest)
            hit_damage = round(res.damage)
            attack_rows.append(
                AttackRow(e.entry_id, res.roll, hit_damage, res.is_crit, res.is_miss)
            )
            await self._emit(
                events.attack(
                    slot=e.slot,
                    roll=res.roll,
                    damage=hit_damage,
                    crit=res.is_crit,
                    miss=res.is_miss,
                    running_total=e.total_damage,
                )
            )
        await self._sleep(combat_seconds - prev)
        await self.store.flush_attacks(attack_rows)

    async def _combat_monster(self, ctx: RoundContext) -> None:
        """R4 co-op monster battle (docs/R4_R6_plan.md). The team swings at the
        monster with the moore per-swing resolution; the monster swings back every
        ``attack_interval`` at a conscious fighter (d20 + its Attack Modifier vs the
        fighter's Armor Class). A fighter whose damage-taken reaches its Health is
        KO'd and stops swinging. Victory (monster HP -> 0) ends the round early;
        otherwise it times out in defeat. Mirrors rules.simulate_monster_round."""
        self._phase = Phase.COMBAT
        cfg = self.cfg
        combat_cfg = cfg.combat
        combat_seconds = cfg.timings.combat_seconds
        monster = ctx.monster
        assert monster is not None

        passives = {e.slot: cfg.race_passives(e.race) for e in ctx.entries}
        cores = {
            e.slot: rules.apply_gear_to_core(
                rules.derive_core_stats(e.stats, cfg.classes[e.class_name], combat_cfg),
                self._gear_for(ctx.chars_by_id.get(e.character_id)), combat_cfg,
            )
            for e in ctx.entries
        }
        states = {
            e.slot: rules.CombatState(lucky_left=passives[e.slot].lucky_reroll_ones)
            for e in ctx.entries
        }
        by_slot = {e.slot: e for e in ctx.entries}
        taken = {e.slot: 0.0 for e in ctx.entries}
        conscious = {e.slot: True for e in ctx.entries}

        # Merge fighter casts (0) + fighter swings (1) + monster swings (2).
        timeline: list[tuple[float, int, Entry | None]] = []
        for e in ctx.entries:
            ability = cfg.classes[e.class_name].ability
            e.cast_at = rules.schedule_cast(self._rng, ability, combat_seconds)
            n = rules.attacks_in_window(e.attack_interval, combat_seconds)
            timeline.extend((k * e.attack_interval, 1, e) for k in range(1, n + 1))
            if e.cast_at is not None:
                timeline.append((e.cast_at, 0, e))
        n_mon = rules.attacks_in_window(monster.attack_interval, combat_seconds)
        timeline.extend((m * monster.attack_interval, 2, None) for m in range(1, n_mon + 1))
        timeline.sort(key=lambda it: (it[0], it[1], it[2].slot if it[2] is not None else 1 << 30))

        attack_rows: list[AttackRow] = []
        monster_hp = monster.hp_max
        victory = False
        prev = 0.0
        ticked = 0
        await self._emit(events.countdown(Phase.COMBAT.value, combat_seconds))  # fight timer
        for t, kind, e in timeline:
            await self._sleep(t - prev)
            prev = t
            ticked = await self._tick_combat(prev, ticked, combat_seconds)
            if monster_hp <= 0:
                break
            if kind == 2:  # monster swings at a conscious fighter
                targets = [s for s, c in conscious.items() if c]
                if not targets:
                    continue
                if cfg.monsters.target_selection == "aggro_top":
                    vslot = max(targets, key=lambda s: by_slot[s].raw_total)
                else:
                    vslot = targets[self._rng.randrange(len(targets))]
                hit, dmg = rules.resolve_monster_attack(
                    self._rng, monster, cores[vslot].armor_class, combat_cfg
                )
                ko = False
                if hit:
                    taken[vslot] += dmg
                    if taken[vslot] >= cores[vslot].health:
                        conscious[vslot] = False
                        by_slot[vslot].was_ko_at = t
                        ko = True
                await self._emit(events.monster_attack(vslot, round(dmg) if hit else 0, ko))
                if ko:
                    await self._emit(events.fighter_ko(vslot))
                continue
            if not conscious[e.slot]:  # KO'd fighters stop acting
                continue
            cd = cfg.classes[e.class_name]
            if kind == 0:  # signature ability cast (bursts hit the monster)
                burst, per_hit = rules.cast_moore_ability(
                    states[e.slot], cd.ability, e.cast_at, cores[e.slot]
                )
                if burst:
                    e.raw_total += burst
                    monster_hp -= burst
                    if per_hit > e.raw_highest:
                        e.raw_highest = per_hit
                    e.total_damage = round(e.raw_total)
                    e.highest_hit = round(e.raw_highest)
                await self._emit(events.ability(e.slot, cd.ability.name))
                if monster_hp <= 0:
                    victory = True
                    await self._emit(events.monster_hp(0))
                    break
                continue
            res = rules.resolve_moore_race_attack(
                self._rng, cores[e.slot], monster.ac, combat_cfg,
                passives[e.slot], states[e.slot], t, None,
            )
            e.raw_total += res.damage
            if res.is_miss:
                e.misses += 1
            else:
                e.hits += 1
                if res.is_crit:
                    e.crits += 1
                if res.damage > e.raw_highest:
                    e.raw_highest = res.damage
                monster_hp -= res.damage
            e.total_damage = round(e.raw_total)
            e.highest_hit = round(e.raw_highest)
            hit_damage = round(res.damage)
            attack_rows.append(
                AttackRow(e.entry_id, res.roll, hit_damage, res.is_crit, res.is_miss)
            )
            await self._emit(events.attack(
                slot=e.slot, roll=res.roll, damage=hit_damage,
                crit=res.is_crit, miss=res.is_miss, running_total=e.total_damage,
            ))
            await self._emit(events.monster_hp(max(0, round(monster_hp))))
            if monster_hp <= 0:
                victory = True
                break

        if not victory:
            await self._sleep(max(0.0, combat_seconds - prev))
        ctx.victory = victory
        await self.store.flush_attacks(attack_rows)
        await self._emit(events.team_result(victory, ctx.tier))

    def _gear_for(self, ch: Character | None) -> rules.GearBundle:
        """Resolve a character's equipped gear into one bundle (R5). NO_GEAR when
        the shop is off, for NPCs, or for the unequipped — so nothing changes until
        the owner enables the shop."""
        if ch is None or ch.is_npc or not self.cfg.shop.enabled or not ch.equipment:
            return rules.NO_GEAR
        items = [
            self.cfg.shop.items[i] for i in ch.equipment.values() if i in self.cfg.shop.items
        ]
        return rules.resolve_gear(items)

    async def _current_ladder_tier(self) -> int:
        raw = await self.store.get_game_state(_LADDER_KEY)
        try:
            tier = int(raw) if raw is not None else 1
        except ValueError:
            tier = 1
        return max(1, min(tier, self.cfg.monsters.max_tier))

    async def _advance_ladder(self, ctx: RoundContext, victory: bool) -> None:
        nxt = rules.next_ladder_tier(ctx.tier or 1, victory, self.cfg.monsters.max_tier)
        await self.store.set_game_state(_LADDER_KEY, str(nxt))
        label = ctx.monster.label if ctx.monster else "monster"
        verb = "defeated" if victory else "was beaten by"
        await self._emit(events.ticker(
            "monster",
            f"The team {verb} the Tier {ctx.tier} {label}! Next monster: Tier {nxt}.",
            "house",
        ))

    async def _results(self, ctx: RoundContext) -> None:
        self._phase = Phase.RESULTS
        cfg = self.cfg

        # Rank by raw (unrounded) total damage; deterministic tie-breaks. In a
        # monster round "damage" is damage dealt to the monster.
        order = sorted(
            ctx.entries, key=lambda e: (-e.raw_total, -e.crits, -e.raw_highest, e.slot)
        )
        is_monster = ctx.kind == "monster"
        victory = bool(ctx.victory) if is_monster else None
        # MVP = top-damage REAL fighter (NPCs can't take the win). On a team victory
        # the MVP wins the round; everyone else (and everyone, on defeat) loses.
        mvp = next((e for e in order if not e.is_npc and e.character_id is not None), None)

        updates: list[CharacterUpdate] = []
        winner_entry_id: int | None = None
        for i, e in enumerate(order):
            e.placement = i + 1
            if is_monster:
                e.is_mvp = e is mvp and bool(victory)
                won = e.is_mvp
                if e.is_mvp:
                    winner_entry_id = e.entry_id
            else:
                won = e.placement == 1
                if won:
                    winner_entry_id = e.entry_id
            if e.is_npc or e.character_id is None:
                continue  # NPCs earn no XP and never touch the leaderboards
            if cfg.xp.mode == "per_battle":
                # R3: completing the battle is the whole reward (1 level, below);
                # placement XP and the xp-multiplier passives/events are retired.
                e.xp_awarded = 0
            else:
                # Gnome earns +5% XP (PLAN.md §4.3); Crowd event grants +25% to all
                # this round (§4.6). Both are meta only — no effect on damage/placement.
                xp_mult = cfg.race_passives(e.race).xp_mult
                if ctx.event is not None:
                    xp_mult *= ctx.event.xp_mult
                e.xp_awarded = round(rules.xp_for_placement(e.placement, cfg.xp) * xp_mult)
            updates.append(self._character_update(ctx.chars_by_id[e.character_id], e, won))

        await self.store.finalize_round(
            RoundResult(
                round_id=ctx.round_id,
                ended_at=self._now(),
                entries=ctx.entries,
                character_updates=updates,
                winner_entry_id=winner_entry_id,
                voided=False,
            )
        )
        if is_monster:
            await self._advance_ladder(ctx, bool(victory))
        await self._update_hall_of_fame(ctx.entries, updates)
        if cfg.shop.enabled:
            # R5: performance gold replaces betting + the presence stipend.
            await self._award_performance_gold(ctx)
        else:
            await self._settle_bets(ctx, winner_entry_id)
            await self._accrue_gold()
        await self._emit(events.round_end(ctx.entries))
        await self._emit_winner_ticker(ctx.entries, winner_entry_id)
        await self._run_countdown(Phase.RESULTS, cfg.timings.results_seconds)

    async def _settle_bets(self, ctx: RoundContext, winner_entry_id: int | None) -> None:
        """Pay out this round's chat bets pari-mutuel (PLAN.md §6.6): winners split
        the pool in proportion to their stake on the winning fighter."""
        winner = next((e for e in ctx.entries if e.entry_id == winner_entry_id), None)
        if winner is None:
            return
        bets = await self.store.bets_for_round(ctx.round_id)
        if not bets:
            return
        payouts = rules.settle_parimutuel(
            [(b.user_id, b.slot, b.amount) for b in bets], winner.slot, self.cfg.economy.rake
        )
        await self.store.settle_bets(ctx.round_id, payouts)
        pool = sum(b.amount for b in bets)
        winners = sum(1 for p in payouts.values() if p > 0)
        await self._emit(
            events.ticker(
                "bet",
                f"Bets settled: {len(bets)} wager(s), {pool:,} gold pool -> {winner.name} "
                f"({winners} winner(s))",
                "system",
            )
        )

    async def _accrue_gold(self) -> None:
        """Pay the per-round gold stipend to everyone present in chat this round."""
        if self._presence is None:
            return
        active = self._presence.drain()
        if not active:
            return
        user_ids = [
            await self.store.register_user(platform, puid, login, display)
            for (platform, puid), (login, display) in active
        ]
        await self.store.award_gold(user_ids, self.cfg.economy.gold_per_round)

    async def _award_performance_gold(self, ctx: RoundContext) -> None:
        """R5: pay each real fighter's owner gold = damage × Loot Bonus% × tier mult
        (§13.1). Tier mult is the monster's gold_mult (×1.0 for damage races)."""
        cfg = self.cfg
        tier_mult = ctx.monster.gold_mult if ctx.monster is not None else 1.0
        payouts: list[tuple[str, int]] = []
        for e in ctx.entries:
            if e.is_npc or e.character_id is None:
                continue
            ch = ctx.chars_by_id.get(e.character_id)
            if ch is None:
                continue
            core = rules.apply_gear_to_core(
                rules.derive_core_stats(e.stats, cfg.classes[e.class_name], cfg.combat),
                self._gear_for(ch), cfg.combat,
            )
            gold = rules.gold_from_damage(e.total_damage, core.loot_bonus, tier_mult)
            if gold:
                await self.store.credit_gold(ch.user_id, gold)
                payouts.append((ch.name, gold))
        if payouts:
            summary = ", ".join(f"{name} +{g}" for name, g in payouts[:6])
            await self._emit(events.ticker("info", f"Gold earned: {summary}", "house"))

    async def _update_hall_of_fame(
        self, entries: list[Entry], updates: list[CharacterUpdate]
    ) -> None:
        """Offer this round's records to the all-time Hall of Fame (hard rule #11:
        do NOT equalize which classes hold what). Single-round records come from
        the entries; accumulation records from the post-round lifetime stats. The
        store keeps a candidate only if it beats the standing record."""
        candidates: list[HoFCandidate] = []
        real = [e for e in entries if not e.is_npc and e.character_id is not None]
        if real:
            hit = max(real, key=lambda e: e.highest_hit)
            candidates.append(HoFCandidate("highest_hit", hit.character_id, hit.highest_hit))
            rnd = max(real, key=lambda e: e.total_damage)
            candidates.append(HoFCandidate("highest_round", rnd.character_id, rnd.total_damage))
        if updates:
            wins = max(updates, key=lambda u: u.wins)
            candidates.append(HoFCandidate("most_wins", wins.character_id, wins.wins))
            dmg = max(updates, key=lambda u: u.lifetime_damage)
            candidates.append(HoFCandidate("most_damage", dmg.character_id, dmg.lifetime_damage))
        if candidates:
            await self.store.update_hall_of_fame(candidates)

    async def _emit_winner_ticker(self, entries: list[Entry], winner_entry_id: int | None) -> None:
        """Round winners are a required ticker feed (PLAN.md §6.1). Emitted here
        so the overlay carries the result independently of the chat announcer."""
        winner = next((e for e in entries if e.entry_id == winner_entry_id), None)
        if winner is None:
            return
        text = f"{winner.name} wins with {winner.total_damage:,} damage!"
        if not winner.is_npc and winner.owner:
            text += f" (@{winner.owner})"
        await self._emit(events.ticker("winner", text, winner.owner_platform or "house"))

    # -- helpers -----------------------------------------------------------
    def _character_update(self, ch: Character, e: Entry, won: bool) -> CharacterUpdate:
        cfg = self.cfg
        new_xp = ch.xp + e.xp_awarded
        if cfg.xp.mode == "per_battle":
            new_level = rules.level_after_battle(ch.level, cfg.xp)  # +1/battle, capped
        else:
            new_level = rules.level_for_xp(new_xp, cfg.xp)
        stats = dict(ch.stats)
        if new_level > ch.level:
            primary = cfg.classes[ch.class_name].primary
            stats[primary] += (new_level - ch.level) * cfg.xp.per_level_primary_bonus
        battles = ch.battles_fought + 1
        retired = rules.should_retire(battles, cfg.round.lifespan_battles)
        return CharacterUpdate(
            character_id=ch.id,
            battles_fought=battles,
            wins=ch.wins + (1 if won else 0),
            losses=ch.losses + (0 if won else 1),
            xp=new_xp,
            level=new_level,
            stats=stats,
            lifetime_damage=ch.lifetime_damage + e.total_damage,
            lifetime_hits=ch.lifetime_hits + e.hits,
            lifetime_crits=ch.lifetime_crits + e.crits,
            highest_hit=max(ch.highest_hit, e.highest_hit),
            is_retired=retired,
            retired_at=self._now() if retired else ch.retired_at,
        )

    async def _select_from_queue(self, key: str) -> list[tuple[QueueItem, Character]]:
        """Pick this round's real fighters, at most one character per user. The
        model is config-selected (PLAN.md §13.1); ``key`` is the round's miss
        bucket ("race" or "tier<N>") for the weighted lottery."""
        if self.cfg.queue.selection == "weighted_lottery":
            return await self._select_weighted_lottery(key)
        return await self._select_fifo()

    async def _select_fifo(self) -> list[tuple[QueueItem, Character]]:
        """FIFO pick with a cap of one character per user per round. Entries not
        chosen (slots full, or user already in) stay queued in order, so they get
        priority next round (PLAN.md §5.2)."""
        n_slots = self.cfg.round.fighters_per_round
        selected: list[tuple[QueueItem, Character]] = []
        used_users: set[int] = set()
        leftover: deque[QueueItem] = deque()
        for item in self._queue:
            if len(selected) >= n_slots or item.user_id in used_users:
                leftover.append(item)
                continue
            ch = await self.store.get_living_character(item.character_id)
            if ch is None:  # retired / deleted since queueing -> drop it
                continue
            selected.append((item, ch))
            used_users.add(item.user_id)
        self._queue = leftover
        return selected

    async def _select_weighted_lottery(self, key: str) -> list[tuple[QueueItem, Character]]:
        """R2 weighted lottery (PLAN.md §13.1). EventSub priority tokens are seated
        first (in queue order); the rest of the slots are filled by a server-side
        lottery weighted by ``1 + misses[key] * miss_weight`` so a character that
        keeps getting skipped for THIS round kind/tier climbs toward a guaranteed
        seat (R4 per-tier priority). One character per user; retired/deleted
        characters are dropped; everyone left over gets +1 miss in ``key``'s
        bucket."""
        n_slots = self.cfg.round.fighters_per_round
        miss_weight = self.cfg.queue.miss_weight

        # Resolve living characters once, in queue order; drop retired/deleted.
        living: list[tuple[QueueItem, Character]] = []
        for item in self._queue:
            ch = await self.store.get_living_character(item.character_id)
            if ch is not None:
                living.append((item, ch))

        selected: list[tuple[QueueItem, Character]] = []
        used_users: set[int] = set()

        # 1) Priority tokens are guaranteed, in queue order (one per user).
        pool: list[tuple[QueueItem, Character]] = []
        for item, ch in living:
            if item.priority and len(selected) < n_slots and item.user_id not in used_users:
                selected.append((item, ch))
                used_users.add(item.user_id)
            else:
                pool.append((item, ch))

        # 2) Weighted lottery fills the remaining slots without replacement.
        while len(selected) < n_slots:
            eligible = [i for i, (it, _) in enumerate(pool) if it.user_id not in used_users]
            if not eligible:
                break
            weights = [1.0 + pool[i][0].misses.get(key, 0) * miss_weight for i in eligible]
            chosen = eligible[_weighted_index(weights, self._rng)]
            item, ch = pool.pop(chosen)
            selected.append((item, ch))
            used_users.add(item.user_id)

        # 3) Everyone still living but unselected stays queued with one more miss.
        leftover: deque[QueueItem] = deque()
        for item, _ch in pool:
            item.misses[key] = item.misses.get(key, 0) + 1
            leftover.append(item)
        self._queue = leftover
        return selected

    async def _run_countdown(self, phase: Phase, seconds: int) -> None:
        self._phase = phase
        for s in range(seconds, 0, -1):
            await self._emit(events.countdown(phase.value, s))
            await self._sleep(1)

    async def _emit(self, event: dict) -> None:
        # A dead/slow renderer must never stop the game (PLAN.md §10).
        try:
            await self._sink.emit(event)
        except Exception:
            self._logger.exception("event sink raised on %s; dropping", event.get("type"))

    def _pick(self, options: list | None, default: str) -> str:
        return self._rng.choice(options) if options else default
