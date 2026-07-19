"""Static Phase-1 game content that isn't a tunable number (so it lives in code,
not the balance config): the selectable races and class display strings.

Races are flavor-only in Phase 1 — their passives (PLAN.md §4.3) arrive in
Phase 2. The ``characters.race`` column already stores the choice.
"""

from __future__ import annotations

# The ten selectable races (chosen at creation, not rolled).
VALID_RACES: tuple[str, ...] = (
    "human", "elf", "dwarf", "orc", "halfling",
    "tiefling", "dragonborn", "gnome", "goblin", "aasimar",
)

# Compact class labels for the one-line !roster reply.
CLASS_ABBREV: dict[str, str] = {
    "barbarian": "Barb",
    "fighter": "Fighter",
    "rogue": "Rogue",
    "monk": "Monk",
    "paladin": "Pally",
    "ranger": "Ranger",
    "warlock": "Lock",
    "wizard": "Wiz",
    "cleric": "Cleric",
    "bard": "Bard",
    "artificer": "Artif",
    "druid": "Druid",
    "sorcerer": "Sorc",
}


def title(name: str) -> str:
    """Display form of a class or race name (``barbarian`` -> ``Barbarian``)."""
    return name[:1].upper() + name[1:]


# Personality traits (PLAN.md §7 roadmap): a cosmetic flavor word assigned at
# creation, stored on the character, and shown at round start. Purely flavor —
# no mechanical effect (mechanical traits are Phase 3, the separate `trait`
# column). Server-selected, so it's deterministic for a given RNG.
PERSONALITIES: tuple[str, ...] = (
    "Brave", "Reckless", "Cautious", "Boastful", "Grim", "Cheerful",
    "Vengeful", "Lazy", "Proud", "Humble", "Cunning", "Loyal",
    "Greedy", "Noble", "Feral", "Stoic", "Chaotic", "Serene",
    "Hot-headed", "Sly",
)


# Hall of Fame records (PLAN.md §8, hard rule #11). Deliberately a MIX of
# single-shot records (highest hit / biggest round — swingy classes like Wizard
# own these) and accumulation records (most wins / most lifetime damage — steady
# classes like Monk own these). Do NOT try to equalize which classes hold them.
# Order here is the rotation order for `!hof`.
HOF_RECORDS: tuple[tuple[str, str], ...] = (
    ("highest_hit", "Biggest Hit"),
    ("highest_round", "Biggest Round"),
    ("most_wins", "Most Wins"),
    ("most_damage", "Most Lifetime Damage"),
)
HOF_LABELS: dict[str, str] = dict(HOF_RECORDS)
HOF_KEYS: tuple[str, ...] = tuple(k for k, _ in HOF_RECORDS)
