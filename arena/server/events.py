"""Server → client message contract (PLAN.md §7) and the event sink abstraction.

The round loop pushes events through an ``EventSink``. In Phase 1 the concrete
sink is the FastAPI WebSocket broadcaster (built with the Godot-client
milestone); here we define the message shapes plus in-memory sinks used by the
demo runner and the tests. Godot is a dumb renderer — it receives these outcomes
and never generates game state.

Every builder returns a plain JSON-serializable ``dict`` so a sink can
``json.dumps`` it straight onto the wire.
"""

from __future__ import annotations

import contextlib
from typing import Any, Protocol, runtime_checkable

from .models import Entry


# ---------------------------------------------------------------------------
# Message builders (the wire contract)
# ---------------------------------------------------------------------------
def fighter_view(entry: Entry) -> dict[str, Any]:
    """The per-fighter object embedded in round_start / sync messages."""
    return {
        "slot": entry.slot,
        "name": entry.name,
        "class": entry.class_name,
        "sprite": entry.sprite_set,
        "dummy_sprite": entry.dummy_sprite,
        "owner": entry.owner,
        "platform": entry.owner_platform,
        "personality": entry.personality,
        "is_npc": entry.is_npc,
        "gear": entry.equipment,  # slot -> item_id; drives the overlay paper-doll layers (R5)
    }


def round_start(
    round_id: int,
    background: str,
    entries: list[Entry],
    event: dict[str, str] | None = None,
    kind: str = "race",
    tier: int | None = None,
) -> dict[str, Any]:
    return {
        "type": "round_start",
        "round_id": round_id,
        "background": background,
        "event": event,  # {"name","label"} or None — the round's arena event (PLAN.md §4.6)
        "kind": kind,    # "race" | "monster" — drives the overlay layout (R4)
        "tier": tier,    # monster ladder tier (1-5) or None for races
        "fighters": [fighter_view(e) for e in entries],
    }


def arena_event(name: str, label: str) -> dict[str, Any]:
    """A random arena event announced at round start (PLAN.md §4.6, §7) — the cue
    for the overlay's event banner. The global modifier is already baked into the
    server-side combat resolution; this event drives the visual + is mirrored to
    the ticker for command-feedback parity."""
    return {"type": "event", "name": name, "label": label}


def attack(
    *, slot: int, roll: int, damage: int, crit: bool, miss: bool, running_total: int
) -> dict[str, Any]:
    return {
        "type": "attack",
        "slot": slot,
        "roll": roll,
        "damage": damage,
        "crit": crit,
        "miss": miss,
        "running_total": running_total,
    }


def ability(slot: int, name: str) -> dict[str, Any]:
    """A signature ability firing mid-round (PLAN.md §4.2, §7) — the cue for the
    overlay's 'big animation'. Damage lands via the running total on later
    attacks; this event drives the visual."""
    return {"type": "ability", "slot": slot, "ability": name}


# -- R4 monster battles (docs/R4_R6_plan.md) -------------------------------
def monster_spawn(tier: int, label: str, hp: int) -> dict[str, Any]:
    """A tiered monster enters the arena; the overlay draws it + its HP bar."""
    return {"type": "monster_spawn", "tier": tier, "label": label, "hp": hp}


def monster_hp(remaining: int) -> dict[str, Any]:
    """Update the monster's HP bar after a fighter's hit."""
    return {"type": "monster_hp", "remaining": remaining}


def monster_attack(target_slot: int, damage: int, ko: bool) -> dict[str, Any]:
    """The monster swings at a fighter (``damage`` 0 = a miss); ``ko`` marks a
    knockout."""
    return {"type": "monster_attack", "target_slot": target_slot, "damage": damage, "ko": ko}


def fighter_ko(slot: int) -> dict[str, Any]:
    """A fighter dropped to 0 Health — the overlay greys them out for the round."""
    return {"type": "fighter_ko", "slot": slot}


def team_result(victory: bool, tier: int | None) -> dict[str, Any]:
    """The monster round's outcome banner (team victory or defeat)."""
    return {"type": "team_result", "victory": victory, "tier": tier}


def round_end(entries: list[Entry]) -> dict[str, Any]:
    """Final standings, ordered by placement (winner first)."""
    standings = sorted(entries, key=lambda e: e.placement or 10**9)
    return {
        "type": "round_end",
        "standings": [
            {
                "slot": e.slot,
                "name": e.name,
                "total": e.total_damage,
                "placement": e.placement,
                "is_npc": e.is_npc,
            }
            for e in standings
        ],
    }


def countdown(phase: str, seconds_left: int) -> dict[str, Any]:
    return {"type": "countdown", "phase": phase, "seconds_left": seconds_left}


def ticker(kind: str, text: str, platform: str) -> dict[str, Any]:
    """The overlay event ticker line — the PRIMARY command-feedback channel
    (PLAN.md §6.1). ``kind`` is one of
    create|enter|error|retire|info|mod|winner|bet|reward|event (drives styling);
    ``platform`` drives the small platform badge on the line."""
    return {"type": "ticker", "kind": kind, "text": text, "platform": platform}


def sync(phase: str, round_info: dict[str, Any] | None, entries: list[Entry]) -> dict[str, Any]:
    """Sent to a client on (re)connect so it can join mid-round (PLAN.md §7).
    ``round_info`` carries the arena event (if any) so a late joiner sees the
    banner too."""
    return {
        "type": "sync",
        "phase": phase,
        "round": round_info,
        "fighters": [fighter_view(e) for e in entries],
    }


def panel(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Intermission info panel content (PLAN.md §8), server-authored."""
    return {"type": "panel", "kind": kind, "payload": payload}


# ---------------------------------------------------------------------------
# Sinks
# ---------------------------------------------------------------------------
@runtime_checkable
class EventSink(Protocol):
    """Where the round loop emits events. Implementations must not raise back into
    the loop — a dead renderer must never stop the game (PLAN.md §10)."""

    async def emit(self, event: dict[str, Any]) -> None: ...


class NullSink:
    """Drops every event (headless with no renderer attached)."""

    async def emit(self, event: dict[str, Any]) -> None:  # noqa: D102
        return None


class RecordingSink:
    """Keeps every event in a list — for tests and the demo runner."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def emit(self, event: dict[str, Any]) -> None:
        self.events.append(event)

    def of_type(self, type_: str) -> list[dict[str, Any]]:
        return [e for e in self.events if e.get("type") == type_]


class FanoutSink:
    """Emits each event to several sinks (e.g. the Godot WebSocket hub *and* the
    chat announcer). One misbehaving sink never blocks the others or the loop."""

    def __init__(self, *sinks: EventSink) -> None:
        self.sinks: list[EventSink] = list(sinks)

    async def emit(self, event: dict[str, Any]) -> None:
        for sink in self.sinks:
            # Isolate sinks from each other and from the loop.
            with contextlib.suppress(Exception):
                await sink.emit(event)
