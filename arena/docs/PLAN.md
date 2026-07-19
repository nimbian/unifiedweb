# D&D Arena — Twitch Chat Battle Game
## Implementation Plan (v1.0)

A community stream game in the spirit of the horse-racing game on GrandPooBear's stream: viewers create persistent D&D characters through Twitch chat, enter them into recurring 60-second arena rounds rendered in a Godot overlay, and compete for damage supremacy, leaderboard spots, and permanent Hall of Fame records.

This document is the authoritative spec. Implement phases in order. Do not build Phase 3+ systems into Phase 1 code paths, but design the data model to accommodate them (columns/tables may exist early and sit unused).

---

## 1. Locked Design Decisions

| Decision | Value |
|---|---|
| Win condition | **Damage race** — all entrants attack their own dummy for the round; highest total damage wins |
| Character creation | **Free for everyone** via chat command; paid boosts deferred to Phase 2+ |
| Classes (v1) | Barbarian, Fighter, Rogue, Monk, Paladin, Ranger, Warlock, Wizard (the remaining 6 classes ship in Phase 2) |
| Damage formula | `damage_per_hit = (PS × d20_multiplier) + SS` (secondary stat is a flat consistency bonus, NOT multiplied by the roll) |
| Renderer | Godot 4.x, 2D, transparent/chroma window captured in OBS |
| Database | PostgreSQL 15+ |
| Server | Authoritative game server separate from Godot (Python recommended, see §3) |
| Roster limit | 3 living characters per Twitch user |
| Character lifespan | 25 battles, then forced retirement |
| Round length | 60 seconds of combat |
| Fighters per round | 10 |

---

## 2. Architecture

Two components in v1. The game server is the single source of truth; Godot is a dumb renderer. (The companion website shipped 2026-07-11 as an interactive player portal — see §8; it lives inside the server process, so the server is still the only Postgres writer.)

```
 Chat platforms — Twitch (v1) · YouTube · TikTok (later)
        │
        ▼  platform adapters → normalized message events
┌─────────────────────┐     WebSocket (localhost)     ┌──────────────┐
│   Game Server       │ ────────────────────────────▶ │ Godot Client │
│  (Python)           │      (server → client         │  - renders   │
│  - command parsing  │       event stream)           │  - animates  │
│  - all game rules   │                               │  - no logic  │
│  - all RNG          │                               └──────────────┘
│  - round scheduler  │                                 captured in OBS
│  - Postgres I/O     │
└─────────────────────┘
        │
        ▼
   PostgreSQL          (deferred: read-only companion website)
```

Rules that must never be violated:

1. **All randomness happens on the server.** Stat rolls, d20 rolls, sprite assignment, dummy selection, background selection. Godot receives outcomes, never generates them.
2. **Godot holds no persistent state.** If the Godot client crashes mid-round, the server keeps simulating; results are still recorded; the client reconnects and resyncs on the next round.
3. **Nothing but the server writes to Postgres.** The player website upholds this: its `/api` runs inside the server process and mutates only through the server's `Store` (no second writer).
4. **Chat platforms are quarantined behind adapters.** Each platform (Twitch in v1) has an adapter that normalizes inbound chat into a common event — `{platform, platform_user_id, display_name, text, timestamp}` — and the command parser consumes only that. No twitchio (or other platform-library) types may cross the adapter boundary into game logic. This is a v1 requirement even though Twitch is the only v1 platform: it is a day of discipline now vs. a week of refactor when YouTube/TikTok are added (§6.4).

### Stack (locked)

- **Game server:** Python 3.12+. `twitchio` (IRC chat + EventSub in one library), `asyncpg`, FastAPI hosting the Godot-facing WebSocket endpoint (twitchio and FastAPI coexist cleanly in one asyncio event loop / process), asyncio tasks for the round state machine. (Rationale for twitchio over a Nightbot-webhook approach is in §6.1.)
- **Godot:** 4.x, GDScript, `WebSocketPeer` for the event stream.
- **Deployment:** everything runs on the streaming PC or a LAN box for v1. Docker-compose for Postgres + server is fine.

---

## 3. Data Model (PostgreSQL)

Schema sketch — Opus should refine types/indexes but keep the shape:

```sql
CREATE TABLE users (
    id               BIGSERIAL PRIMARY KEY,
    platform         TEXT NOT NULL DEFAULT 'twitch',  -- 'twitch' | 'youtube' | 'tiktok'
    platform_user_id TEXT NOT NULL,                   -- Twitch user id, YT channel id, etc.
    login            TEXT,                            -- platform login/handle where applicable
    display_name     TEXT NOT NULL,
    created_at       TIMESTAMPTZ DEFAULT now(),
    is_banned        BOOLEAN DEFAULT FALSE,
    UNIQUE(platform, platform_user_id)
);
-- The same human on two platforms is two user rows. Cross-platform account
-- linking is explicitly OUT OF SCOPE (see §12); rosters are per-platform-identity.

CREATE TABLE characters (
    id              BIGSERIAL PRIMARY KEY,
    user_id         BIGINT REFERENCES users(id),
    name            TEXT NOT NULL,            -- profanity-filtered, <= 20 chars
    class           TEXT NOT NULL,            -- enum via CHECK constraint
    race            TEXT NOT NULL,
    str INT, dex INT, con INT, intl INT, wis INT, cha INT,
    level           INT DEFAULT 1,
    xp              INT DEFAULT 0,
    battles_fought  INT DEFAULT 0,            -- retire at 20
    wins            INT DEFAULT 0,
    losses          INT DEFAULT 0,
    lifetime_damage BIGINT DEFAULT 0,
    lifetime_hits   BIGINT DEFAULT 0,
    lifetime_crits  INT DEFAULT 0,
    highest_hit     INT DEFAULT 0,
    sprite_set      TEXT NOT NULL,            -- assigned at creation
    trait           TEXT,                     -- Phase 3, nullable
    generation      INT DEFAULT 1,            -- increments per retired char for that user
    personality     TEXT,                     -- cosmetic flavor line
    is_retired      BOOLEAN DEFAULT FALSE,
    retired_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_characters_user_alive ON characters(user_id) WHERE NOT is_retired;

CREATE TABLE seasons (
    id         SERIAL PRIMARY KEY,
    name       TEXT NOT NULL,                 -- "Season 3 — March 2026"
    starts_at  TIMESTAMPTZ NOT NULL,
    ends_at    TIMESTAMPTZ NOT NULL
);

CREATE TABLE rounds (
    id           BIGSERIAL PRIMARY KEY,
    season_id    INT REFERENCES seasons(id),
    started_at   TIMESTAMPTZ,
    ended_at     TIMESTAMPTZ,
    background   TEXT NOT NULL,
    event        TEXT,                        -- Phase 3 random events, nullable
    winner_entry BIGINT                       -- FK to round_entries, set at end
);

CREATE TABLE round_entries (
    id            BIGSERIAL PRIMARY KEY,
    round_id      BIGINT REFERENCES rounds(id),
    character_id  BIGINT REFERENCES characters(id),
    slot          INT NOT NULL,               -- 0-9 arena position
    is_npc        BOOLEAN DEFAULT FALSE,
    dummy_sprite  TEXT NOT NULL,
    total_damage  BIGINT DEFAULT 0,
    hits          INT DEFAULT 0,
    crits         INT DEFAULT 0,
    misses        INT DEFAULT 0,
    highest_hit   INT DEFAULT 0,
    placement     INT,                        -- 1-10, set at round end
    xp_awarded    INT DEFAULT 0,
    UNIQUE(round_id, slot)
);

-- Per-swing log. ~200 rows/round; cheap, invaluable for balance analysis
-- and Hall of Fame stats. Partition or prune by month if it ever matters.
CREATE TABLE attacks (
    id        BIGSERIAL PRIMARY KEY,
    entry_id  BIGINT REFERENCES round_entries(id),
    ts        TIMESTAMPTZ DEFAULT now(),
    roll      INT NOT NULL,                   -- raw d20
    damage    INT NOT NULL,                   -- 0 on miss
    is_crit   BOOLEAN,
    is_miss   BOOLEAN
);

-- Idempotency guard for Twitch EventSub redeliveries (Phase 2)
CREATE TABLE processed_events (
    event_id    TEXT PRIMARY KEY,
    processed_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE hall_of_fame (
    record_key   TEXT PRIMARY KEY,            -- 'highest_dps', 'highest_hit', etc.
    character_id BIGINT REFERENCES characters(id),
    value        NUMERIC NOT NULL,
    achieved_at  TIMESTAMPTZ
);

-- Phase 3: items, character_items (slot-unique), traits reference table
```

Leaderboards are computed with queries over `round_entries` joined to `rounds`/`seasons` — no denormalized leaderboard table in v1. Add materialized views if query cost ever matters (it won't at this scale).

---

## 4. Core Game Rules

### 4.1 Stat generation

For each of the six stats (STR, DEX, CON, INT, WIS, CHA):

1. Roll 4d6. Any die showing 1 is rerolled until it is not a 1 (i.e., effectively 4d5+1 per die, values 2–6).
2. Drop the lowest of the four dice.
3. Sum the remaining three. Range: 6–18, heavily skewed high.

### 4.2 Classes (v1)

| Class | Primary | Secondary | Attack interval | Signature ability (Phase 2) |
|---|---|---|---|---|
| Barbarian | STR | CON | 4.0s | Rage — +40% damage for 10s |
| Fighter | STR | DEX | 3.0s | Second Wind — next 3 attacks can't miss |
| Rogue | DEX | CHA | 2.0s | Backstab — next hit has +50% crit chance |
| Monk | DEX | STR | 1.5s | Flurry — 5 rapid attacks at 40% damage each |
| Paladin | STR | INT | 3.5s | Smite — one attack at 3× damage |
| Ranger | DEX | INT | 2.5s | Volley — 3 arrows at 60% damage each |
| Warlock | INT | CON | 4.0s | Curse — dummy takes +20% damage from this character for 15s |
| Wizard | WIS | INT | 5.0s | Fireball — one massive hit (2.5×) with screen flash |

Notes for Opus:
- Wizard's WIS primary is intentional per the design owner. Do not "correct" it to INT.
- **Attack intervals ship in Phase 1** (they're cheap and immediately make classes feel different); signature abilities ship in Phase 2.
- Per-class DPS must be normalized via a per-class damage coefficient tuned by the simulator (§9). Formula becomes `damage = round(class_coeff × ((PS × mult) + SS))` where `class_coeff` compensates for attack interval so no class is strictly dominant. Store coefficients in a config table/file, not hardcoded.

Phase 2 adds: Cleric (STR/WIS), Bard (CHA/DEX), Artificer (INT/DEX), Druid (WIS/CON), Sorcerer (CHA/CON).

### 4.3 Races and passives (Phase 2)

Ten races, chosen (not rolled) at creation. Race is flavor + one passive; race does NOT determine sprite in v1 (asset pipeline stays sane). Passives should be small (≤ ~5% expected DPS impact) and tuned by the simulator:

| Race | Passive |
|---|---|
| Human | +1 to all stats at creation (with a small damage normalizer in config — the integer bonus alone is worth +6.4% DPS, over the ≤ ~5% target) |
| Elf | +3% crit chance |
| Dwarf | +2 CON; immune to Curse-type debuff events |
| Orc | First hit of each round deals 1.9× damage (trimmed from 2× to meet the ≤ ~5% DPS target) |
| Halfling | Rerolls natural 1s once per round (Lucky) |
| Tiefling | +5% damage during Fire/Blood Moon arena events |
| Dragonborn | Every 10th attack adds a small breath-weapon bonus hit |
| Gnome | +5% XP earned |
| Goblin | +10% attack speed, −5% damage per hit |
| Aasimar | +5% damage during Blessing arena events |

Environment/race interaction (the "environment bonus/weakness" idea) is implemented via the arena-event passives above (Tiefling, Aasimar, Dwarf) rather than a full race×background matrix — a full matrix is a balance nightmare for marginal viewer-visible payoff. Revisit post-Phase 3 if desired.

### 4.4 The attack roll

Every `attack_interval` seconds during a round, each fighter attacks once:

1. Roll d20 (server-side, uniform 1–20).
2. **Natural 1 → MISS.** Zero damage. Red "1" sprite, whiff/faceplant animation. Counted in `misses`.
3. **Natural 20 → CRITICAL.** Multiplier 2.0 is applied AND the final damage is doubled: `damage = round(class_coeff × ((PS × 2.0) + SS) × 2)`. Yellow "20" sprite, crit flash, screen shake.
4. **Rolls 2–19** use this 18-entry multiplier table (this fixes the 19-entry bug in the draft spec — rolls 1 and 20 are handled above, so the table only needs 18 values):

```
roll:  2    3    4    5    6    7    8    9    10   11   12   13   14   15   16   17   18   19
mult: 0.5  0.7  0.7  0.8  0.8  0.9  0.9  1.0  1.0  1.0  1.1  1.1  1.3  1.3  1.6  1.6  1.8  1.8
```

5. `damage = class_coeff × ((PS × mult) + SS)` — **accumulate internally as floats; round only at display and persistence boundaries.** Apply a global ×10 display scale (config value) so per-hit numbers land in the 80–400 range: this eliminates the integer-rounding bias that penalizes fast/low-coefficient classes like Monk, and bigger floating numbers read better on stream.
6. The raw d20 result is displayed above the character's head as a spritesheet animation: **red for 1, yellow for 20, white otherwise.**

### 4.5 XP, leveling, retirement

- Levels **1–10** (not 1–20 — a 25-battle lifespan cannot support a 20-level curve; hitting level 10 before retirement should be an achievement, not routine). *(R3 replaces this with 1 level/battle to 20 behind `[xp].mode = "per_battle"`; §13.1.)*
- XP per round: `base 100 + placement bonus (1st: 150, 2nd: 100, 3rd: 60, 4th–5th: 30) + participation streak bonuses` (tunable config).
- Suggested curve: level N requires `100 × N × (N+1) / 2` cumulative XP (triangular) — expect an average character to retire around level 6–8.
- Each level grants **+1 to primary stat** (simple, legible in chat).
- At `battles_fought = 20` the character is auto-retired after the round: retirement announcement in chat, stats frozen, eligible for Hall of Fame, and the user's next created character gets `generation + 1`.
- **Win/Loss record:** placement 1st = win; everything else = loss. (Simple and unambiguous under the damage-race model.)

---

## 5. Round Lifecycle and Matchmaking

The game runs continuously and unattended. State machine:

```
INTERMISSION (90s) → ROSTER_LOCK (10s) → COMBAT (60s) → RESULTS (20s) → INTERMISSION ...
```

1. **INTERMISSION:** entry queue is open (`!enter`). Godot shows the previous results / leaderboard rotation and a countdown.
2. **Queue → slots:** when roster locks, take up to 10 entries. If more than 10 are queued, selection is **FIFO with a cap of one character per user per round**; overflow stays queued with priority for the next round (announce queue position). If fewer than 10, **fill remaining slots with NPC characters** (house-generated, clearly labeled `[NPC]`, excluded from leaderboards) so rounds always look full.
3. **ROSTER_LOCK:** server assigns slots 0–9, random dummy sprite per slot, random background for the round; pushes `round_start` to Godot; announces the lineup in chat (one compact message).
4. **COMBAT:** server runs each fighter on its own attack timer for 60s, emitting an `attack` event per swing. Accumulates damage in memory; flushes `attacks` rows in batches; writes `round_entries` aggregates at end.
5. **RESULTS:** compute placements, XP, wins; update character aggregates and Hall of Fame records in one transaction; push `round_end` with final standings; announce top 3 in chat; Godot plays victory animation on the winner.

**Arena layout:** 10 fighter positions evenly spaced on a circle facing inward; each fighter's target dummy sits just inside the circle in front of them (dummies form an inner ring toward the center). Winner's fighter is highlighted in RESULTS.

**Chat betting (Phase 2, high priority):** during INTERMISSION after the lineup is announced, viewers `!bet <slot|name> <amount>` using a free virtual currency ("gold") earned passively by watching (e.g., 10/round present in chat). This is the single biggest engagement mechanic in the horse-race genre — treat it as near-mandatory. Payouts proportional to a simple pari-mutuel pool or fixed odds; keep it fake-currency only (no channel points payout) to avoid Twitch policy complexity.

---

## 6. Chat Platform Integration

### 6.0 Adapter layer (v1 requirement)

All chat ingress goes through platform adapters (see architecture rule 4). Each adapter is an independent asyncio task implementing a common interface: emit normalized inbound message events, expose an optional `send(text)` capability flag (Twitch: yes; YouTube: limited; TikTok: no), and report its own health. **An adapter crashing or disconnecting must never affect the round loop or other adapters.** Platforms are enabled/disabled in config.

### 6.1 Feedback model: the overlay ticker is primary, chat replies are secondary

Because later platforms can't reliably receive bot messages (§6.4), **the authoritative feedback channel is an on-screen event ticker in the Godot overlay**, fed by `{"type":"ticker", ...}` WebSocket messages: character creation results, queue confirmations with position, command errors, retirement announcements, round winners. Every command outcome MUST appear on the ticker. Chat replies still happen where the platform supports them (Twitch in v1) as a convenience mirror, but no feature may depend on chat replies existing. This also declutters chat on busy streams.

### 6.2 Twitch adapter (v1)

- **Chat commands:** IRC via `twitchio` with a dedicated bot account (moderator status in the channel to relax rate limits).
- **Why twitchio, not FastAPI + Nightbot `$(urlfetch)`:** Nightbot calling HTTP endpoints works for simple read commands, but it's the wrong foundation here. It's pull-only (the game can't announce round starts, lineups, or winners on its own), adds a third-party dependency and extra latency to time-sensitive commands like `!enter`, imposes Nightbot's own response-length and rate limits, provides no reliable user identity guarantees beyond what Nightbot forwards, and does nothing for EventSub (subs/bits/channel points), so a direct integration would be required in Phase 2 anyway. Direct twitchio gives full duplex chat, one codebase, and the same library handles EventSub later. FastAPI still exists in the stack — it hosts the Godot WebSocket — it just isn't the chat ingress.
- **EventSub (Phase 2):** channel point redemptions, subs, bits, via twitchio's EventSub support. Every EventSub handler must check/insert `processed_events` first — Twitch redelivers.
- **Auth:** OAuth tokens in env vars; token refresh handled by the library; document the app registration steps in the repo README.

### 6.3 Commands (v1)

Same command grammar on every platform. Every outcome renders on the overlay ticker (§6.1); on Twitch, a ≤ 1-line chat reply mirrors it. Reply examples below are the Twitch mirror format:

| Command | Behavior |
|---|---|
| `!create <class> <race> <name>` | Creates a character if user has < 3 living. Rolls stats, assigns sprite. Reply: `@user Thorak the Barbarian (Orc) is born! STR 16 DEX 12 CON 15 INT 8 WIS 10 CHA 9 — !enter to fight` |
| `!enter [name]` | Queues a character for the next round. If user has multiple, `name` picks one; otherwise defaults to most recently used. Reply includes queue position. |
| `!stats [name]` | One line: `Thorak — Lv6 Barbarian (Orc) | 14W/3L | 2,341 lifetime DPS | best hit 188 | 3 battles left` |
| `!roster` | User's living characters, one line: `1) Thorak Lv6 Barb (3 left) 2) Pip Lv2 Rogue (18 left)` |
| `!retire <name>` | Confirms then retires early (two-step: `!retire X` → `!confirm`). |
| `!leaderboard` / `!top` | Top 3 season DPS in one line. `!top wins` and `!top alltime` variants cover the other two boards. |
| `!inspect <name>` | Public: look up anyone's character (same format as `!stats`). |
| `!hof` | Rotates through Hall of Fame records, one per invocation (Phase 2). |
| `!bet` | Phase 2. |
| `!gear` | Phase 3. |
| `!help` | One line listing the core commands, plus a link to the project's GitHub README for the full how-to (a static README is not a website build). |
| Mod-only: `!banplayer <user>`, `!renamechar <old> <new>`, `!pause`, `!resume`, `!start`, `!close` | Moderation and stream control. `!start` opens the arena (rounds run); `!close` idles it after the current round, keeping the queue. |

### 6.4 Rate limiting and safety

- Per-user command cooldown: 3s global, 30s on `!create`.
- Character names: ≤ 20 chars, alphanumeric + spaces, passed through a profanity filter (use a maintained wordlist library; this is a platform TOS concern since names render on stream). Reject, don't sanitize.
- All command handling wrapped so a malformed command can never crash the round loop.

### 6.5 Multi-platform roadmap (YouTube, TikTok)

Not in v1, but the v1 adapter interface and identity schema must support this without refactor:

- **YouTube (adapter #2, when needed):** official Live Chat API. Polling-based (2–5s latency) and quota-metered (default 10,000 units/day); *sending* messages is quota-expensive, so the YouTube adapter is read-mostly — the ticker carries feedback. The `liveChatId` changes per broadcast and must be resolved at stream start. Memberships/Super Chats map into the Phase 2 support-event abstraction.
- **TikTok (adapter #3, last, eyes open):** no official public chat API. Community libraries (e.g., the TikTokLive Python package) read the webcast websocket unofficially and break periodically when TikTok changes the protocol; sending messages as a bot is effectively unsupported (read-only adapter) and this is TOS gray area. Isolate it hard; expect maintenance.
- **Timing tolerance:** polling latency means `!enter` can arrive after roster lock. Accept entries whose platform timestamp precedes the lock, and keep the intermission window generous.
- **Monetization normalization (Phase 2+):** bits/subs, Super Chats/memberships, and TikTok gifts all normalize to one internal support event `{platform, user, tier_value}` feeding the same boost logic, with a per-platform value mapping in config.
- **Overlay affordance:** a small platform badge (Twitch/YT/TikTok glyph) renders next to each fighter's owner name so viewers can distinguish same-named users across platforms.
- **Simulcast note:** video distribution (Restream/multi-RTMP) is an OBS concern, not a game concern — all platforms watch the same rendered output.

---

## 7. Godot Client

- Godot 4.x, 2D. Window runs borderless with a solid chroma background (or transparent window where the OS/OBS setup allows); the streamer captures it in OBS.
- Connects to the server WebSocket on launch; on connect (or reconnect) receives a `sync` message describing current phase and state so it can join mid-round gracefully.
- **Server → client message contract (JSON):**

```json
{"type":"sync",        "phase":"combat", "round": {...}, "fighters":[...]}
{"type":"round_start", "round_id":1, "background":"castle_courtyard",
 "fighters":[{"slot":0,"name":"Thorak","class":"barbarian","sprite":"barb_03",
              "dummy_sprite":"dummy_07","owner":"brian_ttv","is_npc":false}, ...]}
{"type":"attack",      "slot":0, "roll":17, "damage":42, "crit":false, "miss":false,
                       "running_total":312}
{"type":"ability",     "slot":3, "ability":"fireball"}          // Phase 2
{"type":"ticker",      "kind":"create|enter|error|retire|winner", "text":"Thorak the Barbarian is born! (@brian_ttv)", "platform":"twitch"}
{"type":"round_end",   "standings":[{"slot":4,"name":"...","total":1873,"placement":1}, ...]}
{"type":"countdown",   "phase":"intermission", "seconds_left":42}
```

### Animation and asset approach

Spritesheets are correct for v1 — but **equipment must render on the character**, which changes how the sheets are structured. Two viable approaches; Opus should implement **Option A**:

**Option A — Layered "paper-doll" spritesheets (recommended).** Every character is a stack of `Sprite2D`/`AnimatedSprite2D` layers sharing an identical frame grid and driven by one `AnimationPlayer`: body layer, then one layer per equipment slot (weapon, helmet, armor, boots, gloves; ring/amulet render as aura/glow effects rather than pixels). Because all layers use the same grid and frame timing, equipping an item is just swapping one layer's texture — no combinatorial sprite explosion. The **LPC (Liberated Pixel Cup) sprite ecosystem** is purpose-built for exactly this: hundreds of community body/hair/armor/weapon layers on a shared 64×64 frame grid, with walk/slash/thrust/cast animation rows, and a generator tool for previewing combinations. Licensing is CC-BY-SA / GPL / OGA-BY per layer — attribution must be tracked in `assets/CREDITS.md`, which is compatible with a free community stream game. This single decision makes the entire Phase 3 equipment system visually real for near-zero art budget.

**Option B — Baked per-set spritesheets** (each class×sprite-set is one flattened sheet, gear shown only as tints/glows). Simpler rendering, but equipment is invisible, which undercuts the loot system's viewer appeal. Only fall back to this if LPC's pixel-art style is rejected.

Additional asset rules:
- **Attack effects, spell effects, the d20 head-roll, and impact hits are their own effect spritesheets** played on separate short-lived nodes — never baked into character sheets. Supplement with Godot's built-in `GPUParticles2D` for trails, embers, and crit bursts (particles are cheaper and better-looking than hand-animated sheets for those).
- Multiple sprite sets per class = multiple body/palette/outfit layer combos, assigned randomly at creation and stored on the character row.
- Dummies: several standalone spritesheets (idle + hit-flinch frames), randomized per round. Backgrounds: a folder of swappable images, random per round.
- Keep `assets/CREDITS.md` with per-layer license records.
- **v1 visual effects:** floating damage numbers, the d20 roll spritesheet above heads (red 1 / yellow 20 / white), crit flash + light screen shake, per-dummy damage total bars (this is the "race" — a horizontal progress comparison of all 10 totals along one edge of the screen is the most legible option), owner's username + platform badge under each fighter, the scrolling event ticker (§6.1), winner victory animation.
- **Phase 3 effects:** particles, attack trails, weapon glow, camera work, combo counter, MEGA HIT callouts.

---

## 8. In-Game Presentation (website deferred)

The companion website is **deferred to a later phase** — all information surfaces live in chat replies (§6.2) and in the Godot overlay itself:

- **Intermission panels:** during the 90s intermission, Godot rotates through display cards pushed by the server — season top-3 leaderboards (DPS month / DPS all-time / most wins), a random "character spotlight" (a queued or recently victorious character's full sheet), one Hall of Fame record, and the next-round lineup once roster locks. This replaces the website's discovery role and gives the stream something to show between rounds.
- The server sends these as `{"type":"panel", ...}` WebSocket messages so panel content stays server-authored.

**Hall of Fame records (all-time, survive season resets):** Highest DPS ever (single round), Highest single hit, Most career wins, Most wins in a 20-battle career, Most critical hits, Fastest to reach level 10, Longest win streak, Oldest character (wall-clock days between creation and retirement).

**Seasons:** calendar-month, rolled over automatically at midnight **America/New_York** on the 1st. Season leaderboards reset; Hall of Fame and character records persist. Announce season champion in chat and feature them on an intermission panel for the first week of the new season.

**Player website (SHIPPED 2026-07-11 — supersedes the original "strictly read-only" deferral, owner-ratified):** a React SPA (`web/`) + REST API (`/api`, `server/webapi.py`) hosted **inside the game-server process** — the server remains the only Postgres writer (rule #3 upheld: web mutations route through the same `Store`, never raw SQL, and never through the chat command layer). Scope: "Login with Twitch" OAuth (empty scope, maps onto `(platform, platform_user_id)` — rule #12 intact, no linking), roster + permalinked character sheets, retired-legends archive, **self-service rename** (same validation as chat), **gear inventory** (migration 0007: buy/equip/unequip; replaced items are kept, not destroyed; chat gains matching `!equip`/`!unequip`), **retire** (guarded while queued/fighting — backported to chat `!retire`), public leaderboards top-25 + Hall of Fame, and a live arena page (polls `/api/arena`; the token-gated overlay WS is not exposed to browsers). Every web mutation emits an overlay ticker suffixed "(web)" (rule #5). Character-token-gated creation (§13 roadmap) remains future work — creation stays chat-only.

---

## 9. Balance and Simulation Harness (build in Phase 1)

Because the server owns all game logic, ship a headless simulator in the same codebase from day one:

- `sim.py --rounds 10000` generates random characters across all classes/levels and simulates rounds without Twitch or Godot.
- Outputs per-class mean DPS, variance, win rate, and crit distribution.
- **Tune coefficients against WIN RATE, not mean DPS** — win rate is what leaderboards and W/L records measure, and equal mean DPS does not yield equal win rates in a max-of-10 race (per-hit variance differs by class). Closed-loop tuner: `coeff_new = coeff × (0.10 / actual_win_rate) ** 0.5` (damped), iterate until convergence.
- **Acceptance target:** every class's win rate within 9.5%–10.5% at **100k rounds** of level-matched characters (10k rounds has ±0.3pp standard error — too noisy to distinguish real imbalance from luck; deviations under ~2σ are not actionable). Use common random numbers (shared stat arrays and d20 streams across classes) to sharpen comparisons.
- **Audit schedule edge effects:** verify whether an attack fires at t=0 and whether fractional-interval classes (e.g., Paladin at 3.5s → 17.14 attacks/round) silently lose a partial attack — that's systematic bias, not noise.
- **Intentional trade-off (do not "fix"):** even at equal win rates, slow/heavy classes (Wizard) have higher round-total variance than fast/steady classes (Monk), so swingy classes will disproportionately own "highest single hit" and "highest single-round DPS" Hall of Fame records while steady classes accumulate wins. This is designed class identity.
- Rerun after every Phase 2/3 mechanic (abilities, races, traits, gear) lands. This is the only way affix/trait/passive stacking stays sane.

---

## 10. Reliability and Operations

- Round state (queue, active entries, in-round damage) is checkpointed to Postgres at phase transitions; on server restart mid-round, the round is voided gracefully (announce in chat, no battle consumed from anyone's 20).
- Godot disconnect does not stop the server; rounds continue headless and results persist.
- Structured logging; a `!pause` mod command halts the loop after the current round (for stream segments where the overlay should idle).
- The arena boots **closed** (idle, no rounds) until a mod types `!start`; `!close` idles it again after the current round finishes, preserving the queue (`!enter` still queues while closed). `[arena].open_on_launch = true` overrides the boot state for dev. The overlay shows "ARENA CLOSED" from the `idle` phase in `countdown`/`sync`.
- Config (timings, XP tables, coefficients, asset lists) in a hot-reloadable TOML/JSON file — balance tweaks must not require code deploys.
- **Remote deployment:** the overlay may run on a different network than the server. The WS feed then sits behind a reverse proxy (Apache httpd, TLS on 443) with uvicorn bound to loopback, gated by a shared `WS_AUTH_TOKEN` (`Authorization: Bearer` from the client's gitignored `overlay.cfg`). The server process is never exposed directly. Runbook: README "Remote deployment".
- Backups: nightly `pg_dump`.

---

## 11. Phased Milestones

**Phase 1 — Streamable MVP.** Server (platform adapter interface with Twitch as sole adapter; IRC commands: create/enter/stats/roster/leaderboard/help + mod commands), stat rolls, 8 classes with attack intervals and tuned coefficients, damage-race rounds with full state machine and NPC fill, d20 mechanics with crit/miss, Postgres persistence, retirement at 25 battles, XP/levels 1–10, Godot client with circle layout, LPC layered character rendering (body layers only in Phase 1 — the layer stack exists so gear slots drop in later), attack + d20 effect spritesheets, floating damage, race progress bars, overlay event ticker, victory animation, random dummies/backgrounds, intermission info panels, simulator harness with win-rate-targeted tuner.
*Acceptance: game runs unattended for a 4-hour stream with 30+ unique participants and zero crashes; all commands respond < 1s; class win rates within target band in sim.*

**Phase 2 — Identity and Engagement.** Signature abilities (auto-cast once per round at a random mid-round moment, big animation), the 6 remaining classes, races + passives, chat betting with gold currency, seasons with auto-rollover, Hall of Fame + `!hof`, EventSub channel-point hooks (extra character slot rental, stat reroll at creation, priority queue token), personality traits (cosmetic flavor lines shown at round start).

**Phase 3 — Depth.** Equipment: 7 slots (Weapon/Helmet/Armor/Boots/Gloves/Ring/Amulet), 6 rarities (Common→Mythic), affix system (stat bonuses, +crit%, +attack speed, elemental bonus damage) with rarity-gated affix counts; loot drops awarded by round placement; **equipped gear renders on the character via the paper-doll layers (§7)**, with rarity-colored glow; `!gear`/`!equip`. Character traits (one rolled at creation: Lucky, Aggressive, Clumsy, Fearless, Berserker, Coward, Determined — each a small tuned modifier). Ultimates (once per round at the 45s mark, per-class big animation). Combo counter and hit callouts. Random arena events (Rain, Fire, Blessing, Curse, Fog, Blood Moon, Crowd — each a small global modifier announced at round start). Sub/bits premium boosts.
*Rerun simulator; item + trait + race stacking must keep class win rates in band.*

**Phase 4 — Modes, Platforms, Web.** Wave-survival mode (team of 10 vs escalating monster waves — requires monster AI and character HP, a significant new system), raid-boss mode (all entrants vs one giant boss with a shared HP pool and phase mechanics), **YouTube adapter, then TikTok adapter** (per §6.5 — YouTube may be pulled earlier if simulcasting starts sooner), and the read-only companion website. Environment×race matrix revisit. The modes are co-op variations of the same round state machine; schedule them as special rounds every Nth round.

---

## 12. Deliberately Deferred / Open Questions

1. Character HP and taking damage exist only in Phase 4 modes — arena rounds are pure damage races (dummies never die; a dummy HP/"break" mechanic could be a fun Phase 3 event but is out of scope before then).
2. Trading/economy between players: out of scope indefinitely (moderation surface too large).
3. Multi-channel support: schema keys on `(platform, platform_user_id)` so it's not precluded, but v1 is single-channel.
4. **Cross-platform account linking:** the same human on Twitch and YouTube is two separate users with separate rosters, permanently, unless a linking flow (link codes + verification) is built later. Out of scope indefinitely.
5. Unique per-affix item art beyond the LPC layer library: base LPC weapon/armor layers + rarity glow tint cover Phase 3; bespoke sprites for legendary/mythic items are a stretch goal.

---

## 13. Design Revision — 2026-07-05 (MooreDnD Battle System Guide)

The owner supplied the *MooreDnD Battle System Guide* and ratified the following
decisions where it diverged from this plan. **Where §13 conflicts with earlier
sections, §13 wins.** Earlier sections remain authoritative for everything §13
doesn't touch, and for the CURRENT engine until each migration milestone ships.

### 13.1 Ratified decisions

| Topic | Decision |
|---|---|
| Battle core | **Hybrid rounds.** Damage-race rounds (current engine) remain the default; every Nth round is a **tiered monster battle** — the monster fights back (d20 + its Attack Modifier vs character AC), characters have Health, a character at 0 Health is knocked unconscious and stops attacking for the round. N configurable. |
| Combat math | **Full MooreDnD math for both round types** (replaces §4.4 when R1 ships): Core Stats on a 0–1000 scale; Attack Power = relevant ability × 25 (hard cap 1000); to-hit = d20 + Attack Modifier (standard D&D modifier scale) vs target AC; damage = Attack Power ± Damage Variance (base ±75); natural 20 = crit at Critical Damage % (100% + 5 pp per point of its governing ability); Attack Speed stat (100 = 1 attack/10 s); Loot Bonus stat (% of damage converted to gold). |
| Leveling | **1 level per completed battle, levels 1–20.** Voided rounds still don't count (hard rule #10). Retirement at level 20 + veteran battles (count TBD, §13.4). Placement XP, the XP curve, and xp-multiplier passives/events retire with this. |
| Economy | **Doc economy only**: Gold = damage dealt × Loot Bonus × tier multiplier (tiers I–V = ×1.0/1.5/2.0/2.5/3.0). Gold buys permanent equipment in a **shop** (replaces §Phase-3 placement loot drops). **Chat betting (§6.6) and the presence stipend retire** when the shop economy ships — until then they keep running. |
| Creation | **Stays free via chat (`!create`).** The doc's website + character-token flow lands with the website phase; tokens gate creation then, not before. |
| Stat generation | **Sorted 4d6**: keep 4d6-drop-lowest rolls (server-side, hard rule #1) but auto-sort the six results into the class's stat priority order. (Owner-chosen deviation from the doc's Standard-Array-or-roll choice — no creation-time choice, no array floor.) |
| Round shape | **90-second battles, 8 slots.** Queue becomes a **weighted lottery**: characters that missed the previous battle of that tier get priority; repeated misses accumulate selection weight; priority tracked per tier. (Replaces FIFO-with-carryover; EventSub priority tokens still jump ahead.) |
| Training (new) | **Cross-player co-training** at retirement: two RETIRED characters — one yours, one another consenting player's — co-train a new character. Starting abilities = blend of the parents' final scores **regressed toward the creation mean** (prevents multi-generation snowballing) + a small capped bonus + random variance. Lineage is displayed ("Trained by X & Y") and `characters.generation` increments. Parameters TBD (§13.4). |

### 13.2 Migration order (each milestone keeps the game streamable)

Migration status (2026-07-09): most R-milestones land **additively behind config
flags, default = shipped behavior**, so live play is untouched until the owner flips
them — flags `[combat].engine` (R1), `[queue].selection` (R2 queue), `[xp].mode`
(R3). The exception is **R2 round shape (90 s / 8 slots), which shipped live** (it
is not flag-gated — the round-shape change applies to the current classic engine as
well as moore); both engines were re-tuned around the 12.5% fair share. See
`docs/R1_combat_math.md` for R1 detail.

- **R1 — Combat math rewrite** — *code complete, behind `[combat].engine = "moore"`.* Core Stats, to-hit vs AC, per-class ability→stat mappings + priority orders, sorted-4d6 creation, moore simulator/tuner. Races + abilities re-expressed; WITH-races gate passes 9.38–10.42% across 5 seeds. Supersedes hard rule #7 when the flag flips (not before). Sorted-4d6 is now wired into live `!create`/`!reroll` and NPC fill (2026-07-10), **gated on `[combat].engine == "moore"`** so it activates with the flip and classic play keeps its tuned per-stat roll. **Remaining: owner live smoke test, then flip the default.**
- **R2 — Round shape** — *SHIPPED (2026-07-09).* Round is now **90 s / 8 slots** (live, both engines) with the balance gate re-centered on the 8-slot fair share of 12.5% (owner ratified 2026-07-09: bands re-centered, applied live). Both engines were re-tuned and pass every verification seed; the gate half-widths are now `fair_share ± half` so they follow the slot count (`sim.band_for`). At 8 slots both engines use ±0.7 → **11.8–13.2** (classic's half was widened 0.5→0.7 — its max-of-8 spread is ~0.9pp, flagged in sim.py for owner review). The **weighted-lottery queue** is code-complete behind `[queue].selection = "weighted_lottery"` (priority tokens seat first, miss-weight accumulation; **per-tier priority implemented 2026-07-10** — misses bucket per round kind/tier); default stays `fifo` until the owner flips it.
- **R3 — Leveling** — *code complete, behind `[xp].mode = "per_battle"`.* 1 level per completed battle to `levels_max`; placement XP, the XP curve, and xp-multiplier passives/events retire. Veteran-battle count past 20 still owner-gated (gap 8).
- **R4 — Monster battles** — *code-complete behind `[monsters].every_n` (default 0 = off; requires moore engine).* Co-op + MVP outcome; escalating-ladder tiers (climb on victory, reset on defeat, persisted); round-scoped KOs; parametric tier stat blocks sim-tuned to the win-rate ladder (~98/87/72/59/40% at level 10); **per-tier lottery priority + the Godot monster-battle overlay landed 2026-07-10** (client renders `monster_spawn`/`monster_hp`/`monster_attack`, `fighter_ko` grey-out, and the `team_result` banner, fail-soft without art). `--monsters` report. See `docs/R4_R6_plan.md`.
- **R5 — Economy swap** — *code-complete behind `[shop].enabled` (default off).* Gear dies with the character, gold persists on the user; balance gate stays naked (config caps, full-gear DPS delta 13.5% < 15%); performance gold (damage × Loot% × tier) + `!shop`/`!buy`/`!gear` replace betting + the stipend when enabled. `--economy` report. **Paper-doll gear rendering wired 2026-07-10**: the server sends equipped gear in `fighter_view` (shop-on, non-NPC only) and the client stacks each item onto the LPC layer by `item_id` convention (`res://assets/sprites/<layer>/<item_id>.png`), fail-soft — only the gear/monster **art PNGs** remain to drop in.
- **R6 — Training** — *code-complete behind `[training].enabled` (default off).* Limited mentor uses + rising gold cost; per-rank-regressed blend (+4.5% edge, convergent); `!train`/`!accept`/`!decline`; lineage recorded. `--training` report.
- **Website + character tokens**: unchanged from the roadmap (Phase 4-era); creation stays chat-only until then.

### 13.3 Hard-rule impacts

- Rule #7 (damage formula): superseded by §13.1 math **when R1 ships**; until then it remains in force and the current balance gate stays authoritative.
- Rule #6 (Wizard primary = WIS): the doc's examples use INT for Wizards. **Owner must re-confirm each class's priority order at R1** — do not silently flip Wizard to INT.
- Rules #1–5, #8–11 unchanged. §6.6 (betting) is retired at R5.

### 13.4 Open design gaps (ask the owner before the relevant milestone — do not invent)

**R1 gaps 1–5 RESOLVED 2026-07-05 — see `docs/R1_combat_math.md`** (owner ratified:
Wizard keeps WIS; Attack Speed = round(1000/interval) per class; low dummy AC so
to-hit matters only vs monsters; crit damage from a per-class config ability
default-secondary; `class_coeff` survives as an Attack-Power scaling factor).

1. ~~Per-class ability→stat mappings + priority order.~~ **Resolved — R1 spec §1–2.**
2. ~~Class base AC values + AC formula.~~ **Resolved (provisional, R4-tuned) — R1 spec §2–3.**
3. ~~Attack intervals → Attack Speed.~~ **Resolved — R1 spec §0.2, §2.**
4. ~~Signature abilities in the new math.~~ **Resolved — R1 spec §4.**
5. ~~Race passives in the new math.~~ **Resolved — R1 spec §5.**
6. ~~Health formula + whether anything damages characters in damage races.~~ **Resolved 2026-07-09** — Health = `health_base + CON × health_per_con` (R1 config, constants tuned at R4); nothing damages characters in damage races; KOs exist only in monster rounds and are round-scoped. See `docs/R4_R6_plan.md`.
7. ~~Monster stat blocks per tier.~~ **Design resolved 2026-07-09** — parametric per-tier template (HP as % of expected team output, AC/attack_mod/cadence per tier) sim-tuned against owner lethality targets (tier I ~0–1 KOs → tier V ~half team, team win ~95%→~40%); target selection uniform-random (proposal). Final numbers ratified from the first `--monsters` report. See `docs/R4_R6_plan.md`.
8. Veteran battles: how many battles after level 20 before retirement? Needed for R3. *(Partly settled 2026-07-09: lifespan is now 25 battles; under per-battle leveling a character reaches level 20 at battle 19, so ~6 battles are spent at the level-20 cap before retirement. Owner may still tune the lifespan or add a distinct veteran phase.)*
9. ~~Shop catalog.~~ **Implemented 2026-07-09 behind `[shop].enabled` (default off).** Gear dies with the character (gold persists on the user); balance gate stays naked with config caps bounding full-gear power; 3 slots (weapon/armor/trinket), 9-item config catalog; `!shop`/`!buy`/`!gear` commands; performance gold (damage × Loot% × tier mult) replaces betting + the stipend when enabled. Sim-calibrated (`--economy`): mid item in ~5 rounds, full-gear DPS delta 13.5% (< 15% cap). Paper-doll LPC rendering + owner ratification of catalog/prices still pending. See `docs/R4_R6_plan.md`.
10. Damage Variance: flat ±75 at all power levels, or scaled? Needed for R1.
11. ~~Training parameters.~~ **Implemented 2026-07-09 behind `[training].enabled` (default off).** Limited mentor uses (default 3) + rising gold cost (base × (1 + total mentor uses)) paid by the initiator; blend = per-rank regression 0.35 toward the sorted-4d6 rank means + variance, clamped by a **per-rank** ceiling (`+max_bonus_points`, default 1) → +4.5% DPS edge (sim-verified < 5%), multi-gen convergent (no snowball); `!train`/`!accept`/`!decline` in chat; cross-platform pairs allowed; lineage recorded (`trained_by_a/b`, generation). Migration 0006. See `docs/R4_R6_plan.md`.
12. ~~Tier cadence.~~ **RESOLVED 2026-07-09** — escalating ladder: tier starts at I, climbs one tier per team victory (caps at V), resets to I on team defeat; ladder state persists in DB, voided rounds don't move it; every Nth round is a monster battle (`[monsters].every_n`, proposal 4); announced one round ahead. See `docs/R4_R6_plan.md`.
13. ~~R2 round-shape band (90 s / 8 slots).~~ **RESOLVED 2026-07-09.** Owner ratified: apply 90 s / 8 slots live and keep the band widths, re-centered on the 8-slot fair share of 12.5%. `sim.band_for(engine, cfg)` now derives the band from `fair_share = 100/fighters_per_round`. **Both engines ended up at ±0.7 → 11.8–13.2**: the ratified classic ±0.5 turned out too tight (its measured max-of-8 spread is ~0.9pp, failing ~1 seed in 4), so `CLASSIC_BAND_HALF` was widened 0.5→0.7 to match moore — **flagged in sim.py for owner review** (revert to 0.5 if you'd rather accept the occasional graze). Both engines re-tuned and pass every seed (see `docs/R1_combat_math.md` §8).
