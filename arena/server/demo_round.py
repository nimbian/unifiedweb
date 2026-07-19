"""Headless demo of the round state machine.

Runs the arena with the in-memory store and a fake (instant) clock, seeding a
handful of players and printing a compact summary of each round's lineup and
standings. Lets you watch the full lifecycle end-to-end without Twitch or Godot:

    python -m server.demo_round --rounds 3

This is a dev/inspection tool, not part of the running game.
"""

from __future__ import annotations

import argparse
import asyncio
import random
from pathlib import Path

from . import rules
from .arena import Arena
from .config import Config
from .events import RecordingSink
from .store import MemoryStore

_SAMPLE_PLAYERS = [
    ("thornwood", "Grix", "rogue"),
    ("mageduck", "Zathras", "wizard"),
    ("bexley", "Brawnhild", "barbarian"),
    ("kito", "Feather", "monk"),
    ("orlptv", "Ser Beans", "paladin"),
    ("valyra", "Nyx", "warlock"),
    ("pipsqueak", "Pip", "ranger"),
    ("bigmike", "Tank", "fighter"),
]


def _seed_players(store: MemoryStore, cfg: Config, rng: random.Random) -> list[int]:
    ids = []
    for login, name, class_name in _SAMPLE_PLAYERS:
        uid = store.add_user(login)
        stats = rules.roll_stat_block(rng, cfg.stats)
        sprites = cfg.assets.get("sprite_sets", {}).get(class_name, [f"{class_name}_01"])
        ch = store.create_character(
            user_id=uid,
            name=name,
            class_name=class_name,
            race="human",
            stats=stats,
            sprite_set=rng.choice(sprites),
        )
        ids.append(ch.id)
    return ids


def _print_round(n: int, sink: RecordingSink) -> None:
    start = sink.of_type("round_start")[-1]
    end = sink.of_type("round_end")[-1]
    attacks = sink.of_type("attack")
    event = start.get("event")
    banner = f" * {event['label']} *" if event else ""
    print(f"\n=== ROUND {n} - {start['background']}{banner} ({len(attacks)} swings) ===")
    place_by_slot = {s["slot"]: s for s in end["standings"]}
    for f in sorted(start["fighters"], key=lambda f: place_by_slot[f["slot"]]["placement"]):
        s = place_by_slot[f["slot"]]
        who = "[NPC]" if f["is_npc"] else f"@{f['owner']}"
        marker = "WIN" if s["placement"] == 1 else f"{s['placement']:>2}."
        print(f"  {marker:<4} {f['name']:<16} {f['class']:<10} {who:<14} {s['total']:>6} dmg")


async def _amain(rounds: int, seed: int) -> None:
    cfg = Config.load(Path("config/game.toml"))
    rng = random.Random(seed)
    store = MemoryStore()
    player_ids = _seed_players(store, cfg, rng)

    async def instant(_seconds: float) -> None:
        return None

    sink = RecordingSink()
    arena = Arena(cfg, store, sink, rng=rng, sleep=instant)

    for n in range(1, rounds + 1):
        # A rotating subset of players enters each round; the rest is NPC fill.
        for cid in rng.sample(player_ids, k=rng.randint(2, len(player_ids))):
            ch = store.characters[cid]
            if not ch.is_retired:
                await arena.enqueue(cid, ch.user_id)
        sink.events.clear()
        await arena.run_once()
        _print_round(n, sink)

    print("\n--- character standings after demo ---")
    for ch in sorted(store.characters.values(), key=lambda c: -c.lifetime_damage):
        tag = " (retired)" if ch.is_retired else ""
        print(
            f"  {ch.name:<16} Lv{ch.level} {ch.class_name:<10} "
            f"{ch.wins}W/{ch.losses}L  {ch.lifetime_damage:>6} dmg{tag}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Headless round-loop demo")
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args(argv)
    asyncio.run(_amain(args.rounds, args.seed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
