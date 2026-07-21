# Deploying the MooreDnD portal on CentOS (bare metal, no Docker)

Single origin (PLAN §4): a reverse proxy serves the unified SPA and path-routes
the two backends. One JWT + one refresh cookie work everywhere.

```
                 reverse proxy (Apache httpd-moorednd.conf OR nginx.conf)
  browser ──────►  /            -> unified SPA  (/opt/moorednd/frontend/dist)
                   /api/arena/  -> dndbattle arena server (127.0.0.1:8090)  [Phase 2]
                   /api/        -> portal backend         (127.0.0.1:8080)

/opt/moorednd/
├── backend/          # this repo's backend/ (fork of newweb/backend)
│   ├── .venv/
│   ├── .env          # real secrets (0600) incl. JWT_*_KEY_PATH
│   ├── keys/         # RS256 PEM key pair (0600; never committed)
│   └── deploy/       # gunicorn.conf.py
├── frontend/
│   └── dist/         # vite build output
└── satchemon-bot/    # this repo's satchemon-bot/ (Discord bot, Phase 3)
    ├── .venv/
    └── config.yml    # bot token + Postgres creds (0600; never committed)
```

Services: **`moorednd-api`** (portal backend, §1), the **unified SPA** (§2), the
**arena** upstream on `/api/arena/` (Phase 2; run per `arena/README.md`), and the
**`moorednd-bot`** Discord bot (§4, Phase 3). The bot and arena are independent
processes — only the SPA and the portal/arena HTTP upstreams sit behind the
reverse proxy; the bot connects out to Discord and listens on no port.

## 0. Prerequisites

```bash
sudo dnf install -y python3.12 python3.12-devel gcc httpd    # or nginx
curl -fsSL https://rpm.nodesource.com/setup_20.x | sudo bash -
sudo dnf install -y nodejs
sudo useradd --system --home /opt/moorednd --shell /sbin/nologin moorednd
```

## 1. Backend (portal)

```bash
sudo mkdir -p /opt/moorednd && sudo chown moorednd:moorednd /opt/moorednd
# copy the repo's backend/ to /opt/moorednd/backend, then:
cd /opt/moorednd/backend
python3.12 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install .          # installs from pyproject.toml
.venv/bin/pip install gunicorn uvicorn[standard]

cp .env.example .env             # then edit (see below)
chmod 600 .env
```

### JWT signing keys (RS256)

The portal signs tokens with an RSA private key; in Phase 2 the arena verifies
with the public key only. Generate a dev/prod pair and point `.env` at them:

```bash
mkdir -p /opt/moorednd/backend/keys && chmod 700 /opt/moorednd/backend/keys
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 \
  -out /opt/moorednd/backend/keys/jwt_private.pem
openssl rsa -in /opt/moorednd/backend/keys/jwt_private.pem -pubout \
  -out /opt/moorednd/backend/keys/jwt_public.pem
chmod 600 /opt/moorednd/backend/keys/*.pem
```

Then in `.env`:

```
JWT_ALGORITHM=RS256
JWT_PRIVATE_KEY_PATH=/opt/moorednd/backend/keys/jwt_private.pem
JWT_PUBLIC_KEY_PATH=/opt/moorednd/backend/keys/jwt_public.pem
# Grace window only: the OLD newweb HS256 secret, so existing browser sessions
# keep working until the 7-day refresh window drains. Remove afterward.
JWT_LEGACY_SECRET=<the previous newweb JWT_SECRET>
```

Also set `DATABASE_URL`, the three `*_CLIENT_ID/SECRET` pairs, `FRONTEND_ORIGIN`,
and `COOKIE_SECURE=true` behind TLS.

### Database (existing — do NOT mutate)

The schema already exists and is populated. Alembic is restricted to the web-app
tables (`env.py`). Stamp the baseline, then apply the additive Phase-1 migration:

```bash
.venv/bin/alembic stamp 0003_linked_accounts   # if not already at 0003
.venv/bin/alembic upgrade head                 # applies 0004 + 0005 (see below)
```

`0004` only adds two nullable, web-owned columns to `users`; `0005` creates the
new web-owned `link_codes` table backing the bot's `/link` command (Phase 4).
Neither touches bot-owned tables. **Test on a DB copy first** (PLAN §10, Phase 1
risk note).

### Service

```bash
sudo cp deploy/moorednd-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now moorednd-api
curl -s http://127.0.0.1:8080/api/health      # {"status":"ok"}
```

## 2. Frontend (unified SPA)

```bash
cd frontend
cp .env.example .env             # set VITE_SATCHEMON_URL / VITE_DNDBATTLE_URL
npm ci
npm run build                    # -> dist/
sudo rsync -a dist/ /opt/moorednd/frontend/dist/
```

(For the dev-server-behind-proxy workflow instead, use
`deploy/moorednd-frontend.service`.)

## 3. Reverse proxy

Apache:

```bash
sudo cp deploy/httpd-moorednd.conf /etc/httpd/conf.d/moorednd.conf
sudo setsebool -P httpd_can_network_connect 1
sudo apachectl configtest && sudo systemctl enable --now httpd && sudo systemctl reload httpd
```

nginx:

```bash
sudo cp deploy/nginx.conf /etc/nginx/conf.d/moorednd.conf
sudo setsebool -P httpd_can_network_connect 1
sudo nginx -t && sudo systemctl enable --now nginx && sudo systemctl reload nginx
```

Open the firewall: `sudo firewall-cmd --permanent --add-service=http && sudo firewall-cmd --reload`

Both proxy configs also carry the **Phase 5** old-URL redirects (see §6): the old
newweb root paths (`/search`, `/me`, `/user/:did`, `/dnd/*`, …) 301 to their new
`/satchemon/*` homes, so existing bookmarks and links survive the cutover.

## 4. Satchemon Discord bot (Phase 3)

The bot is a standalone long-running process (a Discord gateway client) — no
port, not behind the proxy. It talks to the **satchemon** Postgres directly.

```bash
# copy the repo's satchemon-bot/ to /opt/moorednd/satchemon-bot, then:
cd /opt/moorednd/satchemon-bot
python3.12 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

cp config.yml.samle config.yml    # fill in bot token + Postgres creds
chmod 600 config.yml
```

`config.yml` is the only secret (no `.env` for the bot). It carries the Discord
bot token and the same Postgres connection the portal uses. `bot.py` also has
two host paths near the top — `Collections` (CSV export dir) and `Images` (card
art) — that default to `/home/bramsel/pybot/*`; point them at real dirs the
`moorednd` user can read/write (see the `ProtectHome` note in the unit file).

The Phase-3 hardening is DB-only (`createUser` is now an idempotent
resolve-or-create) and needs no schema change — the `undid` unique constraint it
relies on already exists. Verify the fork before enabling the service:

```bash
.venv/bin/pip install pytest
.venv/bin/python -m pytest -q      # 8 passing (test_createuser + test_linkcode)
```

The bot's `/link` command (Phase 4) writes the web-owned `link_codes` table
(created by migration `0005`, §1) — the only portal-read table the bot touches;
the user redeems the code on `/account`. No bot-owned schema changes.

Service:

```bash
sudo cp deploy/moorednd-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now moorednd-bot
sudo journalctl -u moorednd-bot -f
```

To cut over from the old bot deployment, stop the old process first (only one
bot may hold the Discord gateway connection for a given token).

## 5. OAuth redirect URIs

Each of the three OAuth apps (Discord, Google, Twitch) needs
`FRONTEND_ORIGIN/auth/callback` registered as a redirect URI. The production
origin is **`https://www.moorednd.com`** (PLAN §11 #5), so:

```
FRONTEND_ORIGIN=https://www.moorednd.com
COOKIE_SECURE=true
```

and register `https://www.moorednd.com/auth/callback` on all three OAuth apps.

## 6. Decommission the old sites (Phase 5)

Do this only once the unified portal is validated in prod. Each fork replaces its
predecessor; the old folders are **archived, not deleted** (PLAN §9) until the
whole cutover is confirmed. Order matters — turn on the redirects before stopping
the old backends so no link 404s in the gap.

1. **Old URLs → new (already in the configs).** The reverse proxy 301s the old
   newweb root paths to `/satchemon/*`. Verify after reload:

   ```bash
   curl -sI http://<host>/search      | grep -i location   # -> /satchemon/search
   curl -sI http://<host>/user/123    | grep -i location   # -> /satchemon/user/123
   curl -sI http://<host>/dnd/worldboss | grep -i location # -> /satchemon/progress/worldboss
   ```

   For the standalone **dndbattle** site (a separate origin — see the commented
   `server`/`VirtualHost` block at the bottom of the proxy config), fill in its
   real old hostname (PLAN §11 #5), enable the block, and confirm
   `/roster`, `/shop`, `/characters/:id` redirect under `/dndbattle/*`.

2. **Retire the old backends/frontends.** Stop and disable the old newweb and
   standalone-dndbattle services (whatever their unit names were), leaving the
   unified `moorednd-api`, the arena upstream, and the SPA serving everything.
   The **grace window** matters: keep `JWT_LEGACY_SECRET` set (§1) until the
   7-day refresh window drains, then remove it so old HS256 tokens stop being
   accepted.

3. **Cut over the bot.** Only one process may hold the Discord gateway per token,
   so stop the old bot before enabling `moorednd-bot` (§4) — already covered
   there; just confirm the old one is down.

4. **Archive, don't delete.** Once traffic to the old origins is zero for a full
   refresh window and the leaderboards/collections look right, archive the old
   repos (`bot/`, `dndbattle/`, `newweb/` — `dndadventure/` is unchanged and its
   DB is still read read-only by the portal). Keep the archives until you are
   confident no rollback is needed.

The merge tool (PLAN §7) is intentionally **not** built yet; account-link 409s
are logged as `ACCOUNT_LINK_CONFLICT` so real demand can be counted first:

```bash
journalctl -u moorednd-api | grep -c ACCOUNT_LINK_CONFLICT
```

## Health & logs

```bash
journalctl -u moorednd-api -f
curl -s http://127.0.0.1:8080/api/health
# OpenAPI docs: http://<host>/api/docs
```
