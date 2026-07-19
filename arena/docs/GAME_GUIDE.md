# D&D Arena — Game Guide

A reference for how the game works: character creation, the six stats, every
class, race, and personality, how a round plays out, the arenas, arena events,
the economy, and the optional systems. This describes the **live default
behavior**; config-gated systems that ship disabled are called out in their own
section. All numbers here come from [`config/game.toml`](../config/game.toml)
(hot-reloadable — the owner can retune them without a code change).

---

## What the game is

Viewers of a Twitch stream create persistent D&D characters through chat
commands and enter them into recurring **90-second arena rounds**. A round is a
**damage race**: up to 8 fighters attack practice dummies, and whoever deals the
most total damage before the clock runs out wins. Everything is resolved on the
authoritative game server; the Godot overlay is just a renderer. The stream chat
also earns virtual gold and bets on the fights.

---

## Creating a character

```
!create <class> <race> <name>
```

- **Name**: up to 20 characters, letters/numbers/spaces only, profanity-filtered
  (rejected, not censored).
- **Limit**: 3 living characters per user at a time.
- **Stats** are rolled server-side (see below), then the race's creation bonus is
  applied, a **personality** is assigned (cosmetic), and a sprite is chosen.
- A character lives for **25 battles**, then is forced into retirement. Rounds
  that are voided/crashed don't count against that lifespan.

Related: `!reroll` (re-roll a fresh character's stats before its first fight,
needs a reroll token), `!retire <name>` → `!confirm` (retire early), `!enter` to
queue for the next round. Full command list: [`README.md`](../README.md) / `!help`.

---

## The six stats

Every character has six ability scores: **STR, DEX, CON, INT, WIS, CHA**.

Each is rolled as **4d6, drop the lowest die, keep the top 3** — and any natural
1 is re-rolled first — so scores range **6–18, skewed high**. Each class cares
about two of them: a **primary** and a **secondary** stat that drive its damage.
Leveling up adds **+1 to the primary stat per level**.

Damage per hit (live "classic" engine):

```
damage = class_coeff × ((primary × d20_multiplier) + secondary)   ×10 display scale
```

- **Natural 1** on the d20 = a **miss** (0 damage).
- **Natural 20** = a **critical hit**: `coeff × ((primary × 2) + secondary) × 2`.
- Rolls **2–19** use a rising multiplier table (0.5× at a 2 up to 1.8× at a 19),
  so higher rolls hit harder. On-screen hits land in roughly the **80–400** range.

The **class coefficient** is a per-class balance knob tuned by the simulator so
that — despite very different attack speeds — every class wins its fair share of
rounds (~12.5% at 8 fighters). It is not a stat you pick; it just keeps the
classes even.

---

## Classes (13)

Primary/secondary drive damage; the **attack interval** is how many seconds
between swings (faster = more, smaller hits; slower = fewer, bigger hits). Each
class also has a **signature ability** that auto-casts once per round.

| Class | Primary | Secondary | Attack every | Signature ability |
|---|---|---|---|---|
| Barbarian | STR | CON | 4.0s | **Rage** — +40% damage for 10s |
| Fighter | STR | DEX | 3.0s | **Second Wind** — next 3 swings can't miss |
| Rogue | DEX | CHA | 2.0s | **Backstab** — next hit +50% crit chance |
| Monk | DEX | STR | 1.5s | **Flurry** — 5 rapid attacks at 40% each |
| Paladin | STR | INT | 3.5s | **Smite** — one attack at 3× |
| Ranger | DEX | INT | 2.5s | **Volley** — 3 arrows at 60% each |
| Warlock | INT | CON | 4.0s | **Curse** — +20% damage for 15s |
| Wizard | **WIS** | INT | 5.0s | **Fireball** — one hit at 2.5× + screen flash |
| Cleric | STR | WIS | 3.5s | **Bless** — +25% damage for 12s |
| Bard | CHA | DEX | 2.5s | **Inspiration** — next 2 hits +35% crit chance |
| Artificer | INT | DEX | 3.0s | **Turret Volley** — 4 shots at 55% each |
| Druid | WIS | CON | 4.0s | **Wild Shape** — +45% damage for 8s |
| Sorcerer | CHA | CON | 4.5s | **Chaos Bolt** — 2 hits at 140% each |

Notes:
- **Wizard's primary is WIS by design** (not INT) — intentional flavor.
- Fast classes (Monk, Rogue) chip away with many small hits; slow classes
  (Wizard, Sorcerer, Barbarian) swing rarely but huge — swingier, and they tend
  to own the "biggest single hit" records.
- Abilities come in four flavors: **damage_buff** (a timed % boost),
  **no_miss** (guaranteed hits), **crit_buff** (boosted crit chance for a few
  hits), and **burst** (an instant flurry of bonus hits).

---

## Races (10)

Race is chosen at creation. It's mostly flavor plus **one small passive**
(tuned to under ~5% DPS impact so no race dominates).

| Race | Passive |
|---|---|
| Human | +1 to **every** stat at creation (net ~+4.9% damage) |
| Elf | +3% chance to upgrade any hit into a crit |
| Dwarf | +2 CON at creation; immune to Curse events |
| Orc | First swing of each round deals **1.9×** |
| Halfling | Re-rolls its first natural 1 each round (turns one miss into a hit) |
| Tiefling | +5% damage during **Fire Storm** / **Blood Moon** events |
| Dragonborn | Every 10th swing adds a breath-weapon bonus (~half an extra hit) |
| Gnome | +5% XP earned (no combat impact — levels faster) |
| Goblin | +10% attack speed, but −5% damage per hit |
| Aasimar | +5% damage during **Blessing** events |

The event-conditional races (Tiefling, Aasimar, Dwarf) only get their bonus when
the matching arena event is active that round.

---

## Personalities / natures (20, cosmetic)

Assigned at creation and shown at round start. **Purely flavor — no mechanical
effect** (they don't change stats or damage), they just give each character a bit
of character:

> Brave · Reckless · Cautious · Boastful · Grim · Cheerful · Vengeful · Lazy ·
> Proud · Humble · Cunning · Loyal · Greedy · Noble · Feral · Stoic · Chaotic ·
> Serene · Hot-headed · Sly

---

## A round, step by step

Rounds run on a repeating state machine. A mod opens the arena with `!start`
(and idles it with `!close`); while open it loops:

| Phase | Length | What happens |
|---|---|---|
| **Intermission** | 10s | Queue is open; viewers `!enter`. |
| **Roster Lock** | 10s | The 8-fighter lineup is shown; **betting is open**. |
| **Combat** | 90s | Fighters swing on their own cadences; the damage meter climbs. |
| **Results** | 20s | Winner highlighted, XP/gold awarded, bets paid out. |

- **8 slots** per round. If fewer than 8 real characters are queued, house
  **NPCs** fill the rest (they earn nothing).
- Fighters are arranged on a circle around a central live damage meter that
  re-sorts by total damage as the fight goes.
- The winner is simply whoever accumulated the **most total damage**.

---

## Arenas (backgrounds)

Each round the server randomly picks one backdrop to render behind the fight:

- **Castle Courtyard**
- **Dungeon**
- **Forest Clearing**
- **Arena Pit**

These are cosmetic — they don't affect combat. (Fighters attack randomly-chosen
practice dummies in the arena.)

---

## Arena events

There's a **35% chance** each round rolls one **global event** that applies to
every fighter equally. Each is a flat damage swing at one of two tiers — minor
(±5%) or major (±10%):

| Event | Effect | Notes |
|---|---|---|
| **Fire Storm** | +10% damage to all | Tiefling gets an extra +5% |
| **Blessing** | +5% damage to all | Aasimar gets an extra +5% |
| **Roaring Crowd** | +5% damage to all | — |
| **Rain** | −5% damage to all | — |
| **Curse** | −10% damage to all | Dwarves are immune |
| **Fog** | −10% damage to all | — |
| **Blood Moon** | −10% damage to all | Tiefling resists (+5%) |

Because the multiplier hits everyone, an event is roughly win-neutral on its own
— the edge comes from the races that react to it.

---

## Leveling

- Characters gain XP each round: a **base 100** plus a **placement bonus**
  (1st = +150, 2nd = +100, 3rd = +60, 4th–5th = +30).
- The XP curve is triangular: level 1 = 0 XP, up to **level 10 = 4,500 XP** (the
  cap). Most characters retire somewhere around level 7–9 over their 25 battles.
- Each level grants **+1 to the primary stat**, so a character slowly out-scales
  the field as it survives.

---

## Economy & betting

Free virtual **gold** only — never channel points or real money.

- Viewers earn a small amount of gold just for being present in chat each round
  (start with 100, earn +10/round), check it with `!gold`.
- During Roster Lock they can `!bet <fighter> <amount>` on who'll win.
- Payouts are **pari-mutuel**: all bets form a pool, and winners split it in
  proportion to their stake (house rake is 0% by default).

Twitch **channel-point rewards** can also map to in-game perks — an extra
character slot, a stat re-roll, or a priority-queue token — and subs/bits grant
gold.

---

## The player website

Log in with your Twitch account on the game's website to manage your
characters outside of chat:

- **Roster & character sheets** — stats, win/loss record, lifetime damage,
  biggest hit, lineage, and a retired-legends archive. Sheets are public and
  permalinkable; only you can change your own characters.
- **Rename** — self-service (same rules: ≤ 20 characters, letters/numbers/
  spaces, profanity-filtered).
- **Gear locker** — buy from the shop, equip/unequip per slot, and keep
  replaced items in your bag (chat mirrors this with `!equip` / `!unequip`).
- **Retire** — with a confirmation dialog; blocked while the character is
  queued or mid-fight (same in chat).
- **Leaderboards, Hall of Fame, and a live arena page** — no login needed.

Everything you do on the site announces itself on the stream overlay ticker,
tagged "(web)".

## Hall of Fame & seasons

- **Leaderboards reset monthly** (seasons). `!leaderboard` / `!top` shows the
  season's top damage; `!top wins` and `!top alltime` cover the other boards.
- The **Hall of Fame** (`!hof`) keeps all-time records — deliberately a mix of
  single-shot feats (Biggest Hit, Biggest Round — swingy classes like Wizard tend
  to own these) and grind feats (Most Wins, Most Lifetime Damage — steady classes
  like Monk own these). This spread is intentional and not "balanced away."

---

## Optional / advanced systems (config-gated, off by default)

These are built and tested but ship **disabled**; the owner enables them in
config. They belong to an in-progress rules migration (the "MooreDnD" combat
model) and change how combat resolves.

- **Alternate combat engine ("moore")** — a to-hit-vs-Armor-Class model with
  0–1000 "Core Stats," where CON gives Health, CHA gives a gold "Loot Bonus," and
  DEX feeds Armor Class. Live play uses the "classic" multiplier formula above
  until this is switched on.
- **Monster battles** — every Nth round becomes a **co-op** fight against a tiered
  monster instead of a damage race. Five tiers on an escalating ladder (climbs on
  a team win, resets on a loss):

  | Tier | Monster |
  |---|---|
  | I | Giant Rat |
  | II | Gnoll Pack |
  | III | Ogre |
  | IV | Young Dragon |
  | V | Ancient Wyrm |

  The team must drop the monster before time runs out; the monster knocks fighters
  out as it swings back. Top damage dealer is the MVP.
- **Shop & performance gold** — spend gold on **weapons** (Iron/Steel/Mithril —
  Attack Power + crit), **armor** (Leather/Chain/Plate — Armor Class), and
  **trinkets** (Lucky Coin / Swift Charm / Ring of Power — more gold, a little
  speed/power). Gear is bounded so it can't unbalance the classes; it dies with
  the character, but gold persists on the account. (Enabling the shop retires
  chat betting.)
- **Cross-player co-training** — two *retired* characters (yours + a consenting
  player's) can be bred into a new character that inherits blended stats.

---

## Design guarantees (the "hard rules")

A few invariants the game always upholds:

1. **All randomness is server-side** — stat rolls, d20s, sprite/arena picks. The
   overlay only renders outcomes.
2. Damage accumulates internally as precise floats and is only rounded for
   display, so there's no per-hit rounding bias.
3. A character's 25-battle lifespan is never consumed by a crashed/voided round.
4. Hall-of-Fame records are **not** equalized across classes — swingy vs. steady
   classes owning different record types is intentional.
5. Players are identified per platform, so the same name on two platforms is two
   separate accounts (no cross-platform linking).

---

*For the authoritative design spec see [`docs/PLAN.md`](PLAN.md); for the exact
tunable values see [`config/game.toml`](../config/game.toml).*
