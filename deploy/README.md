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
└── frontend/
    └── dist/         # vite build output
```

Only `moorednd-api` (the portal backend) is deployed here in Phase 0/1. The
arena upstream (`/api/arena/`) is wired in the proxy now but the arena fork that
accepts the portal JWT lands in **Phase 2** — until then that route has no
listener (harmless: the homepage tiles link to the existing sites, and no SPA
page calls `/api/arena` yet).

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
.venv/bin/alembic upgrade head                 # applies 0004 (users.created_at/created_via)
```

`0004` only adds two nullable, web-owned columns to `users`; it never touches
bot-owned tables. **Test on a DB copy first** (PLAN §10, Phase 1 risk note).

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

## 4. OAuth redirect URIs

Each of the three OAuth apps (Discord, Google, Twitch) needs
`FRONTEND_ORIGIN/auth/callback` registered as a redirect URI. Set
`FRONTEND_ORIGIN` to the public hostname and, behind TLS, `COOKIE_SECURE=true`.

## Health & logs

```bash
journalctl -u moorednd-api -f
curl -s http://127.0.0.1:8080/api/health
# OpenAPI docs: http://<host>/api/docs
```
