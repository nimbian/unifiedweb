# Sprite assets (LPC layered "paper-doll")

Drop art here and fighters render as sprites automatically — no code change.
Until then, [`fighter.gd`](../../scripts/fighter.gd) falls back to colored
placeholder shapes, so the overlay always runs. Loading + animation live in
[`layered_sprite.gd`](../../scripts/layered_sprite.gd).

**Record every layer's author + license in [`assets/CREDITS.md`](../../../assets/CREDITS.md)
(repo root). This is a licensing requirement, not optional** (LPC layers are
CC-BY-SA / GPL / OGA-BY per the source).

## Folder layout

```
client/assets/sprites/
  body/    <sprite_set>.png     # the fighter body (Phase 1)
  dummy/   <dummy_sprite>.png    # the target dummy (optional; placeholder if absent)
  # Phase 3 equipment layers, same 64×64 grid, composited on top of body:
  boots/ legs/ torso/ arms/ hair/ helmet/ weapon/   <item>.png
  monster/ tier1.png .. tier5.png   # R4 monster body per ladder tier
  effects/ <key>.png                # hit-effect overlays (see below)
```

Fighter+dummy pairs stand on a circle facing inward: each fighter is BESIDE
its dummy, and fighters on the right half of the circle are mirrored/flipped
via per-layer `flip_h`. Body sheets should therefore face **right**; the
client flips them for right-side fighters.

## Hit-effect overlays (`effects/`)

When a fighter lands a hit, the target (dummy or monster) plays an overlay
from `effects/<key>.png`, where `<key>` is the attacker's equipped weapon
item_id, falling back to `class_<class>` when ungeared/NPC
([`hit_effect.gd`](../../scripts/hit_effect.gd)):

```
iron_sword.png steel_sword.png mithril_blade.png     # weapon-keyed (shop items)
class_barbarian.png class_fighter.png ... class_sorcerer.png   # 13 class fallbacks
```

Format: a **single-row strip of 64×64 frames**, played one-shot at ~15 fps
(crits render gold-tinted and larger). Missing files fall back to a procedural
slash + flash, so effects art is optional per key.

Names come straight from the server's event stream (config-driven, selected
server-side). For the current [`config/game.toml`](../../../config/game.toml) you
need these **body** files:

```
barb_01 barb_02  fighter_01 fighter_02  rogue_01 rogue_02  monk_01 monk_02
paladin_01 paladin_02  ranger_01 ranger_02  warlock_01 warlock_02  wizard_01 wizard_02
```

and optional **dummy** files `dummy_01`..`dummy_04`. (Backgrounds are separate —
`main.gd`'s `_background`.)

## Sheet format the loader expects

- Each PNG is a grid of **64×64** frame cells. Columns = `width / 64`, rows =
  `height / 64`. All layers of one character MUST share the same grid so they
  animate in lockstep.
- Animation clips map to **rows**. Defaults in `layered_sprite.gd` `CLIPS`:
  `idle` = row 0, `attack` = row 1 (6 frames), `hurt` = row 2, `victory` = row 0.
  A full Universal LPC sheet has 4 direction rows per action — point these rows
  at the single facing you want and set the frame counts to match your sheet.
- If your sheet uses a different cell size or layout, adjust `FRAME` / `CLIPS` /
  `DISPLAY_HEIGHT` at the top of `layered_sprite.gd`.
