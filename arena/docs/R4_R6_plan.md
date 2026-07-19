# R4–R6 — Monster Battles, Economy Swap, Training (implementation plan)

Plan for the last three milestones of the PLAN.md §13 migration. Design forks
ratified by the owner **2026-07-09**; parameter values marked *(proposal)* are
Opus-designed starting points — sim-validated before shipping, owner may revise.
Where this doc and PLAN.md disagree, PLAN.md §13.1 wins; where §13.1 is silent,
this doc is the spec.

**Sequencing: R4 → R5 → R6**, strictly after the moore engine flip.
- R4 needs Health/AC/to-hit → monster rounds **require** `[combat].engine = "moore"`
  (config-load error if `[monsters].every_n > 0` under classic).
- R5's tier multipliers need R4's tiers (damage races pay ×1.0 until then, so R5
  *could* ship first, but betting/stipend retire at R5 — sequence it after R4 so the
  performance-gold faucet is fully formed when the old faucets close).
- R6 needs R5's gold (training costs gold).

Each milestone lands additively behind a default-off config switch (the R1–R3
pattern), full test coverage before wiring, sim report in the commit message.

---

## R4 — Tiered monster battles

### Ratified (owner, 2026-07-09)
1. **Outcome = Co-op + MVP.** Team goal: kill the monster before the 90 s round
   ends. Placement is still by damage dealt (KO'd fighters keep what they dealt).
   Top damage = **MVP**; on a team victory the MVP takes the round win (win+1,
   others loss+1 — preserving `wins + losses == battles_fought`); on a team defeat
   everyone takes loss+1 and nobody gets the win. Monster battles count toward the
   25-battle lifespan and the 1-level-per-battle (R3) either way.
2. **Tier selection = escalating ladder.** The ladder starts at tier I, climbs one
   tier per team victory (capped at V, stays at V while wins continue), and resets
   to I on a team defeat. Ladder state persists in the DB; voided rounds neither
   advance nor reset it. Every Nth round is a monster battle — `[monsters].every_n`
   *(proposal: 4; 0 = disabled)*.
3. KO is **round-scoped**: at 0 Health a fighter is knocked unconscious and stops
   attacking for the rest of the round; no persistence, no death.

### Round flow
- **Announcement:** during the previous round's results phase, emit a
  `tier_announce` WS event + ticker ("A Tier III monster approaches — next battle!").
  The tier is known at announcement time (ladder state), so roster-lock selection
  can use per-tier priority (below).
- **Roster:** same 8 slots, same queue models, NPC fill applies (house NPCs can
  fight; they earn nothing and can't be MVP for HoF purposes — MVP win still goes
  to the top *real* fighter if an NPC out-damages everyone… *(proposal: MVP = top
  damage among real fighters; flag if you'd rather let NPCs "steal" MVP)*).
- **Combat:** the existing merged-timeline loop gains a 9th combatant. Fighters
  swing at the monster using the standard moore per-swing resolution (d20 + Attack
  Modifier vs **monster AC**; races/abilities/events layer exactly as in damage
  races — arena events modify fighter damage only, never the monster's). The
  monster swings every `attack_interval` at a **uniformly random conscious fighter**
  *(proposal — alternative: aggro top-damage; random is fair, simple, server-side)*:
  d20 + monster attack_mod vs the fighter's Armor Class (`base_ac[class] +
  dnd_modifier(DEX)`, dormant since R1). Fighter Health = `health_base + CON ×
  health_per_con` (config exists; constants tuned here). Monster HP hits 0 →
  **team victory**, round ends early with a victory banner; otherwise the round
  times out at 90 s → team defeat.
- **XP/level:** per R3 — 1 level per completed battle under `per_battle`; under
  `placement` mode placement XP applies by damage placement as usual.

### Monster stat blocks (gap 7 — parametric template, not hand-authored)
One config template, five tier rows; the sim tunes the anchors:

```toml
[monsters]
every_n = 4                    # every Nth round; 0 disables (default until flip)
target_selection = "random"    # random | aggro_top  (proposal: random)

[monsters.tiers.1]             # ...through [monsters.tiers.5]
label = "Giant Rat"            # display name + sprite key per tier
hp_pct_of_team = 0.35          # HP as a fraction of expected 90s team output
ac = 10                        # fighter hit ~90% at tier I -> ~70% at tier V
attack_mod = 3                 # monster hits ~40% (I) -> ~75% (V) vs AC 12-16
attack_interval = 3.0
damage = 250                   # monster AP; +/- damage_variance like any swing
gold_mult = 1.0                # R5 tier multiplier (1.0/1.5/2.0/2.5/3.0 ratified)
```

**Sim-tuned values (2026-07-09, `--monsters`, level-10 reference, in `config/game.toml`):**

| Tier | hp%team | AC | atk+ | dmg | team win% | avg KOs |
|---|---|---|---|---|---|---|
| I Giant Rat | 0.75 | 13 | 4 | 45 | ~98% | 0.3 |
| II Gnoll Pack | 0.79 | 13 | 4 | 60 | ~87% | 0.6 |
| III Ogre | 0.81 | 13 | 4 | 72 | ~72% | 0.8 |
| IV Young Dragon | 0.82 | 13 | 4 | 82 | ~59% | 1.1 |
| V Ancient Wyrm | 0.84 | 13 | 4 | 92 | ~40% | 1.4 |

Two findings drove these away from the first-draft anchors:
- **KO cascade.** Random targeting is positive feedback — once a few fighters drop,
  the rest absorb more hits and the team wipes. The damage needed to hit "~half the
  team KO'd" collapses the win-rate ladder into a cliff (tier V went 0% at dmg 165).
  So **win rate is the primary lethality signal and is tuned first**; damage is kept
  moderate, giving a *gentle* KO curve (0.3→1.4) that rises with tier without wiping.
  AC / attack_mod / interval are held **flat** across tiers so HP alone drives the win
  ladder (mixing them in re-cliffed it).
- **Level dependence.** Monster HP scales with the team's *nominal* output but not its
  hit rate, so lower-level teams (lower hit rate → lower actual output) face
  effectively harder monsters (~0.08 hp-equivalent per 5 levels). The table above is
  the **level-10 reference**; live mixed-level teams run below it. Owner ratifies from
  a live/report review and can nudge hp_pct down for a buffer.

### Balance treatment
The damage-race gate remains the **only** coeff authority — monster rounds are
never used to tune `moore_coeff`. New sim mode `--monsters [--tier N]` reports:
team win rate per tier, KO distribution per class, MVP share per class, expected
ladder tier distribution. **Known identity skew, flagged**: low-AC classes
(warlock/wizard/bard/sorcerer, AC 12) get KO'd more at high tiers, so MVP share
will tilt toward tanky classes there — that's class identity (like rule #11's
HoF stance), reported not equalized. Owner reviews the first report and can
adjust `base_ac` / lethality anchors.

### Per-tier lottery priority (§13.1 clause, deferred from R2) — DONE 2026-07-10
`QueueItem.misses` is now per-key: `{"race": n, "tier1": n, … "tier5": n}`. The
round's kind/tier is decided at the top of `_roster_lock` (before selection), and
the weighted lottery weights each queued character by the bucket matching that
round (`1 + misses[key] * miss_weight`); skipped characters get +1 in that
bucket only, so priority is earned per round type. Fifo path unchanged. When
monsters are off, every round keys `"race"` — identical to the old single
counter. Tests: `test_weighted_lottery_buckets_misses_by_monster_tier`,
`test_weighted_lottery_race_and_tier_buckets_are_independent`.

### Schema — migration `0004_monsters.sql`
- `rounds.kind text default 'race'` ('race' | 'monster'), `rounds.tier int`,
  `rounds.monster_hp_max/remaining int`.
- `entries.was_ko_at real null` (seconds into combat), `entries.is_mvp bool`.
- `game_state` key/value table for the ladder (`monster_ladder_tier`).

### Overlay (Godot — owner verifies visually)
New WS events: `tier_announce`, `monster_spawn {tier,label,hp}`, `monster_attack
{target_slot,damage,ko}`, `monster_hp {remaining}`, `fighter_ko {slot}`,
`team_result {victory}`. Godot: monster sprite + HP bar top-center, KO'd fighters
grey out, victory/defeat banner. Monster sprites per tier from config asset lists.

---

## R5 — Economy swap

### Ratified (owner, 2026-07-09 + §13.1)
1. **Gear dies with the character** (per-character equipment, gone at retirement);
   **gold persists** on the user's account (existing `users.gold` wallet).
2. **Balance gate stays naked** (level-matched, ungeared). Gear power is bounded
   by config caps instead — *(proposal: fully-geared ≤ ~+15% expected DPS)* — so
   the worst-case geared spread stays bounded and the gate stays stable.
3. (§13.1) Gold = `damage_dealt × Loot Bonus% × tier_mult` (I–V = ×1.0/1.5/2.0/
   2.5/3.0; damage races ×1.0). **Betting (§6.6) + presence stipend retire when
   the shop ships** — config kill-switches first (`[economy].betting_enabled =
   false`, `gold_per_round = 0`), code deleted in a later cleanup commit.

**Sim-calibrated (2026-07-09, `--economy`, in `config/game.toml`):** `loot_per_cha
= 0.15` → a non-CHA fighter earns ~224 gold/round (a mid item ~1,200g in **~5.3
rounds**), CHA classes (bard/sorcerer) ~2× (~2.2 rounds — the money stat). Full-gear
DPS delta is **13.5%** (worst class), under the ~15% cap, so the naked gate holds.
Gear is trimmed to keep it there (`max_ap_mult = 0.08`); the slower classes gain the
most from gear (barbarian/warlock/druid ~13.5%, fighter/wizard ~8%) — reported, not
equalized. Owner ratifies from the report.

### Design
- **Accrual:** at results, each real fighter's owner earns
  `round(total_damage × loot_bonus/100 × tier_mult)`. Loot Bonus =
  `loot_base + CHA × loot_per_cha` (R1 CoreStats field, dormant → live here).
  CHA-secondary classes earn more by design (the doc's "money stat").
- **Shop:** config-authored catalog, 3 slots × 3 price tiers *(proposal: 9 items
  v1)*:

```toml
[shop.items.iron_sword]
slot = "weapon"      # weapon | armor | trinket (one item per slot; buying replaces)
name = "Iron Sword"
price = 800
ap_mult = 0.04       # grants: ap_mult / ac_bonus / speed_mult / crit_pp / loot_pp
[shop.caps]          # validated at config load; keeps full gear <= the DPS cap
max_ap_mult = 0.10
max_speed_mult = 0.05
max_ac_bonus = 2
```

- **Commands:** `!shop` (ticker lists items — primary channel per rule #5),
  `!buy <item> [character]`, `!gear [character]`. All outcomes emit tickers.
- **Stats integration:** `derive_core_stats` gains an `equipment` parameter;
  grants apply post-derivation (AP mult after coeff, AC bonus additive, speed
  mult on attack interval). Naked derivation is unchanged → gate untouched.
- **Paper-doll:** gear renders on the LPC layer stack (weapon/armor layers were
  reserved in Phase 1). **Wired 2026-07-10:** the server puts equipped gear in
  `fighter_view` (`"gear": {slot: item_id}`, shop-on + non-NPC only); `fighter.gd`
  maps each slot to a layer (`weapon`→weapon, `armor`→torso; trinket is stat-only)
  and stacks `res://assets/sprites/<layer>/<item_id>.png` via `set_layer`,
  fail-soft. Owner still supplies the LPC art PNGs — the convention path is the
  only mapping (no per-item config keys were needed).
- **Schema — migration `0005_shop.sql`:** `character_equipment (character_id,
  slot, item_id, purchased_at, primary key (character_id, slot))`. Reuses
  `users.gold`.
- **Sim:** `--economy` report — gold/round distribution by class/CHA, rounds-to-
  full-gear curve, geared-vs-naked DPS delta vs the cap.

---

## R6 — Cross-player co-training

### Ratified (owner, 2026-07-09 + §13.1)
1. **Limited mentor uses + rising gold cost.** Each retired character can mentor
   `[training].max_uses` times *(proposal: 3)*; the trainee's owner (initiator)
   pays `base_cost × (1 + mentor's prior uses)` *(proposal: 500 → 1000 → 1500)*.
2. Two RETIRED characters — one yours, one another consenting player's (§13.1);
   cross-platform pairs allowed (character-level pairing; rule #4 safe).

### Blend formula (implemented + sim-validated, 2026-07-09)
The child rolls **no dice for identity, only for variance** — everything server-side.
`E[i]` = the sorted-4d6 rank means, Monte-Carlo'd from the stat config
(`rules.sorted_stat_expectations`; with the reroll-1s rule ≈ 16.3,15.0,14.0,13.0,11.9,10.3):

```
for each sorted rank i:
    parent_mid[i] = (A.sorted_stats[i] + B.sorted_stats[i]) / 2      # parents' FINAL stats
    child[i]      = round(E[i] + regression × (parent_mid[i] − E[i]) + uniform(−var, +var))
    clamp to [3, min(18, round(E[i]) + max_bonus_points)]           # per-RANK ceiling
child stats re-sorted into the CHILD's class priority order (any class allowed).
```

**Key change from the first draft:** the cap is **per-rank, not total**. Parents'
*leveled* stats blow past 18, which would clamp the child's primary to 18 (a +10.6%
edge). A per-rank ceiling of `round(E[i]) + max_bonus_points` with **`max_bonus_points
= 1`** caps the primary at ~17 → a **+4.5% DPS edge** (`--training`, all classes),
under the ≤5% target so the naked gate holds. `regression = 0.35`, `variance = 2`.

Multi-generation lineage **converges** (`--training` gen-1..5 flat at the leveled
primary), so no snowball — the per-rank ceiling is the fixed point regardless of how
strong the ancestors were.

- **Consent flow (chat, v1):** initiator: `!train <myRetired> with <theirChar>` →
  pending request, 5-min TTL, one pending per user → target owner: `!accept` /
  `!decline`. Every step emits a ticker (rule #5); the new character is then
  created via the normal flow with blended stats, `generation = max(parents)+1`,
  lineage "Trained by X & Y" shown at round start and in `!stats`.
- **Schema — migration `0006_training.sql`:** `characters.mentor_uses int default
  0`, `characters.trained_by_a/trained_by_b int null` (character ids; lineage).

---

## Remaining owner touchpoints (small, per milestone)
- **R4 before flip:** ratify sim-tuned tier anchors (HP/AC/lethality table) from
  the first `--monsters` report; MVP-vs-NPC rule; random-vs-aggro targeting.
- **R5 before flip:** ratify catalog contents/prices from the `--economy` report;
  confirm the +15% gear cap; Gnome's retired +XP passive → repurpose to Loot
  Bonus? (R1 doc §5 left this to R5.)
- **R6 before flip:** ratify regression/cap/cost numbers from the `--training`
  report.
