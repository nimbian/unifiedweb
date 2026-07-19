# Godot Client (renderer)

Godot 4.x / GDScript. A **dumb renderer**: it holds no persistent state and no
game logic. It connects to the server's WebSocket, receives a `sync` snapshot to
join mid-round, and renders the server's event stream (`round_start`, `attack`,
`round_end`, `countdown`, `panel`). All randomness happens on the server.

## Files

```
project.godot               autoloads `Net`; main scene = scenes/Main.tscn
scenes/Main.tscn            minimal root; the arena is built in GDScript
scripts/network_client.gd  `Net` autoload — WebSocket transport, JSON -> signals
scripts/main.gd            arena controller: layout, damage bars, countdown, ticker
scripts/fighter.gd         one fighter's visuals (LPC sprite or placeholder fallback)
scripts/layered_sprite.gd  LPC layered "paper-doll" stack (shared frame grid)
assets/sprites/            drop LPC sheets here to activate sprites (see its README)
```

## Phase 1 status — sprite scaffold in, art pending

The data pipeline (connect → sync → round_start → per-swing attacks → ticker →
standings) is fully wired, and the LPC layered "paper-doll" sprite stack
(PLAN.md §7, Option A) is now scaffolded in `fighter.gd` + `layered_sprite.gd`.
It's **fail-soft**: with no art present, fighters/dummies/d20 rolls render as
colored placeholder shapes (as before); the moment you drop correctly-named LPC
sheets into [`assets/sprites/`](assets/sprites/README.md) they render as sprites
with **no code change**. The circle layout, floating damage, event ticker with
platform badges, and the left-edge damage-race bars are all in place.

Signature abilities (Phase 2, PLAN.md §4.2) arrive as `{"type":"ability"}`
messages; `fighter.gd` plays a placeholder "big animation" (body pop + the
ability name flashing above the head). Swap in per-ability effect
spritesheets/particles later — the event wiring is done.

## How to run and verify

1. Start the server's renderer feed (no Twitch/DB needed):
   ```bash
   python -m server.app --memory --no-twitch
   ```
   This runs the round loop and serves the WebSocket on `ws://127.0.0.1:8765/ws`.
   With nobody entering via chat, rounds fill entirely with `[NPC]` fighters —
   perfect for eyeballing the overlay. (Needs `pip install fastapi uvicorn`.)

2. Open `client/` in Godot 4.x and press **Play** (F5).

   **Remote server?** Copy `overlay.cfg.example` → `overlay.cfg` (gitignored)
   and set the `wss://` URL + the shared token (matches the server's
   `WS_AUTH_TOKEN`); the overlay sends it as an `Authorization: Bearer`
   handshake header. Without the file, it connects to `ws://127.0.0.1:8765/ws`
   with no token. `insecure_tls = true` is for self-signed dev certs only.
   Server-side setup (Apache proxy, TLS, token) is in the root README's
   "Remote deployment" section.

3. **What to verify visually** (I can't see rendered output — please check and
   send a screenshot):
   - Top-left status flips from `connecting...` to green **LIVE**.
   - Ten fighters appear on a circle (colored diamonds) with name/owner labels
     and small dummy posts; `[NPC]` fill is labelled.
   - During combat: numbers float up from fighters; a d20 value shows above each
     head — **red on a 1, yellow on a 20**, white otherwise; crits pop + show
     `N!` in yellow.
   - Left-edge **damage-race bars** grow as totals climb, longest = current leader.
   - Countdown label shows `INTERMISSION`/`ROSTER_LOCK`/`RESULTS` with seconds.
   - At round end the winner's diamond turns gold and pulses; the label shows
     `WINNER: <name> (<total>)`.
   - Kill the server, confirm status shows `reconnecting...`, restart it, and
     confirm the overlay reconnects and resyncs on the next round.

If a Godot version mismatch prompt appears on open, let the editor update
`config/features`. Report anything that doesn't match the above and I'll adjust
the GDScript from your screenshot/description.

## Activating LPC sprites

1. Source LPC body sheets (e.g. from the Universal LPC generator / OpenGameArt),
   64×64 frame grid. Save them as `assets/sprites/body/<sprite_set>.png` using
   the names the server sends — see [`assets/sprites/README.md`](assets/sprites/README.md)
   for the exact filename list and sheet-format contract.
2. Record each layer's author + license in [`../assets/CREDITS.md`](../assets/CREDITS.md).
3. Tune `CLIPS` / `FRAME` / `DISPLAY_HEIGHT` at the top of `layered_sprite.gd` to
   your sheet's row layout and cell size, press Play, and send a screenshot —
   I'll adjust the animation rows/scale from what you see.

## Later (Phase 1 polish → Phase 3)

- Attack/impact effect spritesheets + `GPUParticles2D` for crit bursts (§7).
- Phase 3 equipment layers compose onto the same grid via `LayeredSprite.set_layer`.
- Intermission info panels driven by server `panel` messages (PLAN.md §8).
- Dummies as an inner ring facing each fighter; per-round background art.
