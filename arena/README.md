# D&D Arena — Twitch Chat Battle Game

Viewers create persistent D&D characters via Twitch chat and enter them into
recurring 60-second damage-race arena rounds rendered in a Godot 2D overlay.
The Python game server is authoritative; Godot is a dumb renderer; PostgreSQL
is the store.

**New here?** [`docs/GAME_GUIDE.md`](docs/GAME_GUIDE.md) describes how the game
plays — every class, race, personality, the arenas, arena events, and the
economy. **`docs/PLAN.md` is the authoritative spec.** `CLAUDE.md` has the
working rules.

## Layout

```
server/            authoritative Python game server
  rules.py         game rules: stat gen, damage formula, XP/levels (pure, unit-tested)
  config.py        hot-reloadable TOML config loader
  sim.py           headless balance simulator (`python -m server.sim`)
tests/             pytest suite (game rules must be tested before integration)
config/game.toml   timings, XP tables, class coefficients, asset lists
db/migrations/     ordered SQL migrations (server is the ONLY writer)
client/            Godot 4.x project (renderer; no game logic)
assets/            LPC layered sprite sets + CREDITS.md (per-layer licenses)
```

## Development status

**Phase 1 (Streamable MVP) and Phase 2 (Identity & Engagement): feature-complete,
pending live integration test.**
Built and unit-tested: schema + migrations, game-rules module, headless simulator
with tuned class coefficients (13 classes), the round state machine (phase loop,
matchmaking/queue, NPC fill, combat runner, results/XP/retirement, void + pause),
the chat command layer, the platform-adapter boundary (`adapters.py`: normalized
`InboundMessage` + `MessageRouter` that emits the overlay event ticker as the
primary feedback channel), and the chat announcer — all decoupled behind
`Store`/`EventSink` interfaces and covered by the test suite with an in-memory
store. Users are keyed on `(platform, platform_user_id)`, so the same person on
two platforms is two independent accounts (no linking).

Phase 2 adds: the 10 races + passives (PLAN.md §4.3), per-class signature
abilities (§4.2), monthly seasons + all-time Hall of Fame (`!hof`), pari-mutuel
chat betting + gold economy (`!bet`/`!gold`), personality traits, and Twitch
EventSub reward hooks (`rewards.py`: channel points → extra slot / stat reroll /
priority queue; subs + bits → gold; idempotent via `processed_events`).

Integration edges are written but not yet run against live services (they need
the optional deps + real Postgres/Twitch): the FastAPI WebSocket feed (`ws.py`),
the asyncpg store (`pgstore.py`), the migration runner (`migrate.py`), the
Twitch platform adapter (`twitch_bot.py`) and EventSub adapter (`eventsub.py`)
— verify their twitchio surface against your installed version — the app
entrypoint (`app.py`), and the Godot overlay client (`client/`, placeholder
visuals — see `client/README.md`).

Next: stand up Postgres via `docker-compose`, run a live `python -m server.app`
smoke test end-to-end, then swap the Godot placeholder shapes for LPC sprites.

## Quick start (rules, simulator, round loop — stdlib only)

The rules module, simulator, and round loop use only the Python stdlib (3.12+);
no install needed to run them:

```bash
python -m pytest                       # unit tests (rules + config + round loop)
python -m server.sim --rounds 100000   # balance sim; prints per-class win-rate table
python -m server.sim --tune --write    # re-tune class coefficients into the 9.5-10.5% band
python -m server.demo_round --rounds 3  # headless round-loop demo (lineups + standings)
```

The full server (chat + DB + websocket) additionally needs the runtime deps:

```bash
pip install -e ".[dev]"
cp .env.example .env                  # then fill in Twitch + Postgres creds
```

## Local dev without Twitch (console mode)

Drive the game from your terminal — no Twitch creds, no DB — to watch commands
land on the overlay ticker end to end. `--console` adds a stdin
[chat adapter](server/console_adapter.py) alongside (or instead of) Twitch:

```bash
python -m server.app --memory --no-twitch --console
```

Then type commands (`!create barbarian orc Thorak`, `!enter`, `!roster`, …) —
you're a moderator, so `!pause`/`!banplayer` work too. **The arena boots closed
(no rounds): type `!start` to open it** (`!close` idles it again after the
current round; set `[arena].open_on_launch = true` in `config/game.toml` to
skip this in dev). Replies print to the terminal; tickers and round events
stream to any Godot client connected to `ws://127.0.0.1:8765/ws`. (Commands are
still rate-limited: 3s global, 30s on `!create`.)

## Live integration (Postgres + Twitch)

1. **Database** — `docker compose up -d`, then apply migrations:
   `python -m server.migrate` (uses `$DATABASE_URL` from `.env`). The server is
   the only writer.
2. **Twitch app registration** — at <https://dev.twitch.tv/console/apps> register
   an application (OAuth redirect `http://localhost` is fine for a local token
   flow) to get `TWITCH_CLIENT_ID` / `TWITCH_CLIENT_SECRET`. Use a **separate bot
   account**, grant it **moderator** in your channel (relaxes chat rate limits),
   and mint a user access token for it with the `chat:read` + `chat:edit` scopes
   (add `channel:read:redemptions`, `bits:read`, `channel:read:subscriptions` now
   if you want EventSub-ready creds for Phase 2). Put the bot's numeric user id in
   `TWITCH_BOT_ID` and the token/refresh token in `.env`. twitchio refreshes the
   token as it runs.
3. **EventSub rewards (optional)** — set `TWITCH_BROADCASTER_ID` (the channel
   owner's numeric user id) to enable channel-point hooks. Create three rewards
   in your Twitch dashboard and map their titles in `config/game.toml`
   `[rewards.titles]` to `extra_slot` / `stat_reroll` / `priority_queue`; subs +
   bits grant gold. The EventSub edge (`eventsub.py`) is version-specific to
   twitchio and needs live verification — the reward logic itself is tested.
4. **Run** — `python -m server.app` (add `--console` to also drive it from the
   terminal). Open the Godot project in `client/` and press Play; it connects to
   the WebSocket feed and renders the live rounds.

## Player website (React SPA + /api)

Players log in with Twitch and manage their characters at the game's website:
roster + character sheets, self-service rename, gear shop with a real
inventory (buy / equip / unequip — replaced items go to the bag), retire with
confirmation, public leaderboards + Hall of Fame, and a live arena page. The
API runs **inside the game server process** (same FastAPI app as the overlay
feed) so the server stays the only Postgres writer; every web action emits an
overlay ticker suffixed "(web)".

Dev quick-start:

```bash
# terminal 1 — the game server (API on :8765)
python -m server.app --memory --no-twitch --console
# terminal 2 — the React dev server (proxies /api to :8765)
cd web && npm install && npm run dev     # http://localhost:5173
```

Twitch login needs three things in `.env`: `WEB_BASE_URL` (dev:
`http://localhost:5173`), `WEB_SESSION_SECRET` (see `.env.example` for the
generator one-liner), and the existing `TWITCH_CLIENT_ID`/`SECRET` app with
`<WEB_BASE_URL>/api/auth/callback` added to its OAuth Redirect URLs (empty
scope — identity only; Twitch tokens are discarded after login). Sessions are
signed cookies; logout is client-side, and rotating `WEB_SESSION_SECRET`
invalidates all outstanding sessions.

Production: `cd web && npm run build`, and the server serves `web/dist`
automatically (`WEB_DIST` overrides the location; missing dir = API-only).

## Remote deployment (internet + reverse proxy)

When the overlay and the server are on different networks, put the server
behind an **Apache httpd reverse proxy** and gate the feed with a shared token.
The model: uvicorn keeps binding loopback (`WS_HOST=127.0.0.1` — never a public
interface); Apache is the only public listener, terminating TLS on 443 and
proxying `wss://` to the local socket; `WS_AUTH_TOKEN` rejects any client that
doesn't present the token.

1. **Token** — generate and put in the server's `.env`:

   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   # .env:  WS_AUTH_TOKEN=<paste>
   ```

2. **Apache vhost** (needs `mod_proxy`, `mod_proxy_wstunnel`, and a real cert —
   certbot/Let's Encrypt):

   ```apache
   <VirtualHost *:443>
     ServerName arena.example.com
     SSLEngine on
     # SSLCertificateFile / SSLCertificateKeyFile — certbot-managed

     ProxyPass        /ws ws://127.0.0.1:8765/ws upgrade=websocket
     ProxyPassReverse /ws ws://127.0.0.1:8765/ws
     ProxyTimeout 90

     # Player website: API + SPA ride the same process (keep AFTER /ws).
     ProxyPreserveHost On
     ProxyPass        / http://127.0.0.1:8765/
     ProxyPassReverse / http://127.0.0.1:8765/
   </VirtualHost>
   ```

   `upgrade=websocket` needs Apache ≥ 2.4.47; on older versions use the
   `RewriteCond %{HTTP:Upgrade}` + `RewriteRule ... ws://...` `mod_rewrite`
   pattern instead. uvicorn sends protocol-level pings every 20 s, so idle
   tunnels (e.g. arena closed overnight) survive `ProxyTimeout`. Don't proxy
   `/healthz` publicly — it's unauthenticated (curl it locally for monitoring).

3. **Client** — in `client/`, copy `overlay.cfg.example` → `overlay.cfg`
   (gitignored) and fill in:

   ```ini
   [server]
   url = "wss://arena.example.com/ws"
   token = "<the same token>"
   ```

   The overlay sends the token as an `Authorization: Bearer` handshake header
   and verifies the cert against system CAs (`insecure_tls = true` only for
   self-signed dev certs).

4. **Firewall** — inbound 80/443 only. Twitch chat + EventSub are outbound
   connections; Postgres stays local to the server box.

## Balance gate

After any change to rules, classes, races, abilities, or coefficients, run the
simulator over 100,000 rounds of level-matched characters. Every class's win
rate must stay within 9.5%–10.5% (fair share = 10%). Damage accumulates
internally as floats and is scaled (`[damage].display_scale`) and rounded only
at display/persistence.

The **authoritative gate is the WITH-races table** — every real character has a
race, so class coefficients are tuned on the uniform-race baseline
(`python -m server.sim --tune --tune-races --write`) and verified with
`python -m server.sim --rounds 100000 --races`. That command also reports
per-race DPS impact (target ≤ ~5% vs neutral). The raceless table printed first
is a reference baseline only — it is expected to drift slightly out of band.
