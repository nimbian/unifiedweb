# Deploying Satchemon on CentOS (bare metal, no Docker)

Target layout: everything under `/opt/satchemon`, served by **nginx**, backend run
as a **systemd** unit (Gunicorn + Uvicorn workers), against the **existing**
PostgreSQL database (untouched).

```
/opt/satchemon/
├── backend/      # this repo's backend/
│   ├── .venv/    # python venv
│   ├── .env      # real secrets (0600)
│   └── deploy/   # gunicorn.conf.py
└── frontend/
    └── dist/     # vite build output
```

## 0. Prerequisites

```bash
sudo dnf install -y python3.12 python3.12-devel gcc nginx
# Node 20+ for the frontend build (via nodesource or nvm)
curl -fsSL https://rpm.nodesource.com/setup_20.x | sudo bash -
sudo dnf install -y nodejs
sudo useradd --system --home /opt/satchemon --shell /sbin/nologin satchemon
```

## 1. Backend

```bash
sudo mkdir -p /opt/satchemon && sudo chown satchemon:satchemon /opt/satchemon
# copy the repo's backend/ to /opt/satchemon/backend, then:
cd /opt/satchemon/backend
python3.12 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install .          # installs from pyproject.toml
.venv/bin/pip install gunicorn uvicorn[standard]

cp .env.example .env             # then edit: DATABASE_URL, JWT_SECRET, DISCORD_*, GOOGLE_*
chmod 600 .env
openssl rand -hex 32             # -> paste into JWT_SECRET
```

### Database (existing — do NOT mutate)

The schema already exists and is populated. Mark the Alembic baseline without
issuing any DDL:

```bash
.venv/bin/alembic stamp 0001_baseline
```

`env.py` restricts Alembic to the seven web-app tables, so future
`alembic revision --autogenerate` will never touch the Discord-bot tables.

### Service

```bash
sudo cp deploy/satchemon-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now satchemon-api
sudo systemctl status satchemon-api
curl -s http://127.0.0.1:8080/api/health      # {"status":"ok"}
```

## 2. Frontend

Two options — pick one:

### 2a. Static build (recommended for production)

```bash
# build locally or on the box:
cd frontend
cp .env.example .env             # VITE_API_BASE_URL=/api
npm ci
npm run build                    # -> dist/
# deploy the output:
sudo rsync -a dist/ /opt/satchemon/frontend/dist/
```

Apache serves `dist/` directly (section 3) and there is **no frontend daemon** —
only `satchemon-api` runs.

### 2b. Vite dev server as a daemon

If you instead run the Vite dev server behind Apache (the dev workflow — note
`allowedHosts` in `vite.config.ts`), install it as a systemd unit so it survives
reboots:

```bash
cd /opt/satchemon/frontend
npm ci                           # node_modules must exist on the box
sudo cp deploy/satchemon-frontend.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now satchemon-frontend
sudo systemctl status satchemon-frontend
curl -s -H 'Host: new.moorednd.com' http://127.0.0.1:5173/ | head    # serves the SPA
```

Point Apache's `ProxyPass /` at `http://127.0.0.1:5173/` (the unit file's header
has the full vhost snippet). The Vite dev server is not hardened for production —
prefer 2a unless you specifically need it.

## 3. nginx

```bash
sudo cp deploy/nginx.conf /etc/nginx/conf.d/satchemon.conf
# SELinux: allow nginx to proxy to the backend port
sudo setsebool -P httpd_can_network_connect 1
sudo nginx -t && sudo systemctl enable --now nginx && sudo systemctl reload nginx
```

Open the firewall:

```bash
sudo firewall-cmd --permanent --add-service=http && sudo firewall-cmd --reload
```

## 4. Discord OAuth

In the Discord developer portal, add the redirect URI matching
`DISCORD_REDIRECT_URI` (e.g. `http://satchemon.local/auth/callback`). Set
`FRONTEND_ORIGIN` to the same host. For production, terminate TLS at nginx and
set `COOKIE_SECURE=true`.

## 5. Updating

```bash
# backend
sudo -u satchemon /opt/satchemon/backend/.venv/bin/pip install .
sudo systemctl restart satchemon-api
# frontend
npm run build && sudo rsync -a --delete dist/ /opt/satchemon/frontend/dist/
```

## Health & logs

```bash
journalctl -u satchemon-api -f          # backend logs
journalctl -u satchemon-frontend -f     # frontend logs (only if running 2b)
curl -s http://127.0.0.1:8080/api/health
# OpenAPI docs: http://satchemon.local/api/docs
```
