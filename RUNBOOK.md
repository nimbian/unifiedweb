# MooreDnD unified portal — RUNBOOK

Local dev + what still needs your hands. Covers the Phase 0 shell (homepage +
proxy) and the Phase 1 identity backend. The authoritative design is
[`PLAN.md`](PLAN.md); the prod deployment recipe is [`deploy/README.md`](deploy/README.md).

```
unifiedweb/
├── frontend/       MooreDnD SPA (homepage + Satchemon /satchemon/* + DnD Battle /dndbattle/*)
├── backend/        portal API (Phase 1 auth rework; fork of newweb/backend)
├── arena/          arena server (fork of dndbattle) — accepts the portal JWT (PLAN §8)
├── satchemon-bot/  Discord bot (fork of bot/mooreDnD-Bot) — createUser hardening (Phase 3)
└── deploy/         reverse-proxy + systemd (path routing per PLAN §4)
```

---

## 1. One-time setup

### Backend

```bash
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"     # Windows; use .venv/bin on POSIX

# Generate a DEV RS256 key pair (never commit these — *.pem and keys/ are gitignored):
mkdir keys
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out keys/jwt_private.pem
openssl rsa -in keys/jwt_private.pem -pubout -out keys/jwt_public.pem

cp .env.example .env    # then fill in the values in section 3
```

### Frontend

```bash
cd frontend
npm install
cp .env.example .env    # set VITE_SATCHEMON_URL / VITE_DNDBATTLE_URL to the existing sites
```

---

## 2. Run it (two terminals)

```bash
# Terminal 1 — backend on :8080
cd backend
.venv/Scripts/uvicorn app.main:app --port 8080 --reload

# Terminal 2 — frontend on :5173 (Vite proxies /api -> 127.0.0.1:8080)
cd frontend
npm run dev
```

Open http://localhost:5173 — the MooreDnD homepage with the two game tiles.
`GET http://localhost:8080/api/health` → `{"status":"ok"}`; API docs at
`http://localhost:8080/api/docs`.

### Tests / checks

```bash
# backend
cd backend && .venv/Scripts/python -m pytest -q          # 91 passing
# frontend
cd frontend && npm run typecheck && npm run build
```

The backend tests use in-memory SQLite and an **ephemeral** RSA key pair
generated in `tests/conftest.py`, so they need no `.env`, no PEM files, and
never touch a real database.

---

## 3. `.env` values I need from you

### `backend/.env`

| Key | What / notes |
|---|---|
| `DATABASE_URL` | The **satchemon** Postgres URL. **Use a dev copy, never prod** — Phase 1 adds an INSERT branch and migration `0004`. |
| `JWT_ALGORITHM` | `RS256` (default; leave as-is). |
| `JWT_PRIVATE_KEY_PATH` | `keys/jwt_private.pem` (from the openssl step above). |
| `JWT_PUBLIC_KEY_PATH` | `keys/jwt_public.pem`. |
| `JWT_LEGACY_SECRET` | **Cutover only:** the *old* newweb `JWT_SECRET`, so existing browser sessions keep verifying through the 7-day refresh window. Leave blank for a fresh dev DB. Remove after the window drains. |
| `DISCORD_CLIENT_ID` / `DISCORD_CLIENT_SECRET` | Discord OAuth app. |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Google OAuth app (the "YouTube" sign-in). |
| `TWITCH_CLIENT_ID` / `TWITCH_CLIENT_SECRET` | Twitch OAuth app. |
| `FRONTEND_ORIGIN` | `http://localhost:5173` for dev. Also the base for the OAuth redirect URI. |
| `ROLECALL_API_KEY` | Only if you exercise the `/api/rolecall` endpoints. |
| `GOOGLE_SERVICE_ACCOUNT_FILE` | `gc.json` — only for the Drive slideshow page. Optional for auth work. |

The three `*_REDIRECT_URI` values are **derived** from `FRONTEND_ORIGIN` as
`{FRONTEND_ORIGIN}/auth/callback` — leave them unset unless you need to override
one. Nothing is hardcoded.

### `frontend/.env`

| Key | What |
|---|---|
| `VITE_API_BASE_URL` | `/api` (dev proxy + prod both work). |
| `VITE_SATCHEMON_URL` | URL of the existing Satchemon site (homepage tile). |
| `VITE_DNDBATTLE_URL` | URL of the existing DnD Battle site (homepage tile). |

---

## 3b. Arena server (fork of dndbattle) — portal-JWT bridge

The arena at `unifiedweb/arena/` accepts the portal JWT as
`Authorization: Bearer` and maps its `twitch_uid` claim onto the game's
`(platform='twitch', platform_user_id)` user. It verifies with the portal's
**public** key only — it never holds the private key. Point it at the same
public PEM the portal signs with:

```
# in arena/.env
PORTAL_JWT_PUBLIC_KEY_PATH=/abs/path/to/backend/keys/jwt_public.pem
```

Unset = portal auth off (the arena's own Twitch-cookie login still works). The
reverse proxy strips `/api/arena` → the arena's native `/api/*` (see the deploy
configs), so no arena route changes are needed. Its own stack (Godot client,
Postgres, Twitch chat) is unchanged; run/test it per `arena/README.md`. The
portal-bridge tests need only `fastapi httpx pyjwt[crypto] pytest`:

```bash
cd arena && python -m venv .venv
.venv/Scripts/python -m pip install fastapi httpx "pyjwt[crypto]" pytest
.venv/Scripts/python -m pytest -q          # 357 passed
```

## 4. What stays manual (yours to do)

1. **OAuth redirect URIs.** In each of the Discord, Google and Twitch OAuth apps,
   register the dev redirect URI **`http://localhost:5173/auth/callback`** (and
   the prod one when you deploy). You said you'd handle this — the backend builds
   the redirect from `FRONTEND_ORIGIN`, so just keep them in sync.
2. **Fill the real secrets** in `backend/.env` (table above). They are never
   committed (`.gitignore` covers `.env`, `*.pem`, `gc.json`).
3. **Database migration.** Against a **copy** of the satchemon DB, from `backend/`:
   `.venv/Scripts/alembic stamp 0003_linked_accounts` (if not already at 0003)
   then `.venv/Scripts/alembic upgrade head` — this applies `0004` (adds the two
   nullable `users.created_at` / `users.created_via` columns; touches no
   bot-owned tables).
4. **Prod deploy** — follow [`deploy/README.md`](deploy/README.md) (single-origin
   reverse proxy, RS256 keys, `COOKIE_SECURE=true` behind TLS).

---

## 5. satchemon-bot fork (Phase 3 — bot hardening)

`unifiedweb/satchemon-bot/` is a fork of `bot/mooreDnD-Bot` (the git-tracked
tree only — the real `config.yml`, the local `virt/` venv and the large
untracked `images/` dir are **not** copied; restore them at deploy). The single
behavioral change is PLAN §6.1: `createUser` is now an idempotent
**resolve-or-create**.

- `sqlhelper.createUser(name, did)` does `INSERT … ON CONFLICT (did) DO NOTHING`
  (backed by the `undid` unique constraint) and then re-selects, **returning the
  rwid** — so a repeat call, or a row the bot didn't know already existed (a
  web-first account that later linked Discord), is a harmless no-op instead of a
  unique-constraint crash, and never clobbers that row's data.
- All four call sites now use that return value; this also fixes two latent
  crashes in the upstream code (the `/promo` handler referenced an undefined
  `user`; `giveawayEntries` called `createUser` with the wrong arity).
- `mydb.py` now connects **lazily** (psycopg2/yaml imported on first DB use, not
  at import), so the helpers can be unit-tested without a live database.

This does **not** fix the two-row case (the bot can't know a web-first row A
exists when it inserts row B) — that stays a policy matter (PLAN §7): conflicting
links are refused at launch with the guidance message; the admin merge tool and
`/link` command are Phase 4.

### Setup / run / test

```bash
cd satchemon-bot
cp config.yml.samle config.yml     # then fill in bot token + Postgres creds
python -m venv virt
virt/Scripts/python -m pip install -r requirements.txt   # POSIX: virt/bin
virt/Scripts/python bot.py

# Tests — need only pytest (SQLite in-memory; no DB, no config.yml):
python -m pip install pytest
python -m pytest -q                # 4 passing (tests/test_createuser.py)
```

The tests exercise the real `createUser` against in-memory SQLite by
monkeypatching `mydb.db_cursor`; a thin cursor wrapper translates psycopg2's
`%s` placeholders to SQLite's `?` so the helper SQL runs unmodified.

### Deploy note

The prod bot depends on things outside the tracked tree: a filled `config.yml`,
the card-image assets (`Images` path in `bot.py`), and the CSV export dir
(`Collections`). These are host paths, unchanged from the original deployment —
point the fork at the same locations. The bot always has a Discord id in hand,
so did-less web rows never reach it (NULL-did rows also drop out of the
`did`-keyed leaderboard scans — PLAN §2.6).

---

## 6. Phases done / what remains

Done: **Phase 0** (shell), **Phase 1** (identity: rwid subject, resolve-or-create
login, RS256, v1-token grace), **Phase 2** (unified SPA — Satchemon `/satchemon/*`
+ DnD Battle `/dndbattle/*` read + authed pages; arena accepts the portal JWT;
Account link/unlink for all three providers), **Phase 3** (satchemon-bot
`createUser` hardening, above).

Remaining (per PLAN §10):
- **Phase 4 — polish:** the `/link` bot command (one-time code to link Discord
  without OAuth), the **admin merge tool** (build only if the 409 conflict logs
  justify it), and re-keying leaderboards on `rwid`.
- **Phase 5 — decommission:** redirects from the old URLs; retire the standalone
  newweb frontend + dndbattle web; archive the old folders.

At launch, conflicting provider links are refused with the PLAN §7 guidance
message (no merge yet).
