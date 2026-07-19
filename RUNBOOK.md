# MooreDnD unified portal — RUNBOOK

Local dev + what still needs your hands. Covers the Phase 0 shell (homepage +
proxy) and the Phase 1 identity backend. The authoritative design is
[`PLAN.md`](PLAN.md); the prod deployment recipe is [`deploy/README.md`](deploy/README.md).

```
unifiedweb/
├── frontend/   MooreDnD SPA (homepage + Satchemon pages under /satchemon/*)
├── backend/    portal API (Phase 1 auth rework; fork of newweb/backend)
├── arena/      arena server (fork of dndbattle) — accepts the portal JWT (PLAN §8)
└── deploy/     reverse-proxy + systemd (path routing per PLAN §4)
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

## 5. Phase 2 status & what remains

Done: Satchemon pages ported under `/satchemon/*` (DnD Adventure at
`/satchemon/progress/*`); the portal JWT carries `twitch_uid`; the arena fork
accepts that JWT for authed actions.

Still open in Phase 2:
- **dndbattle pages in the SPA** (`/dndbattle/*`): port the arena read pages
  (live arena, leaderboards, Hall of Fame — public JSON through the proxy) and
  the authed pages (roster/sheet/shop) using the portal Bearer token. The
  homepage DnD Battle tile still links out until these land.
- **Account UI**: extend AccountPage for Discord link/unlink (the backend already
  supports it) and add a signed-in affordance on the homepage for did-less users.

Later phases (per PLAN §10): **bot hardening** (`createUser` upsert), the
**admin merge tool**, and the **`/link` bot command** are Phases 3–4. At launch,
conflicting links are refused with the PLAN §7 guidance message (no merge tool).
