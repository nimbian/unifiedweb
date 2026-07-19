# Satchemon API (FastAPI)

Backend for the Satchemon card-collection tracker, migrated from Flask.

## Stack
FastAPI · Pydantic v2 · SQLAlchemy 2.0 · Alembic · python-jose (JWT) · Discord OAuth · Python 3.12

## Layout
```
app/
├── api/
│   ├── routers/         # auth, users, collections, sets, drive
│   └── dependencies/    # DI providers + auth guards
├── core/                # config, database, security, logging
├── models/              # SQLAlchemy 2.0 models (7 web-app tables)
├── schemas/             # Pydantic v2 request/response models
├── repositories/        # data access (ports sqlhelper.py)
├── services/            # business logic (ports api.py)
└── main.py
alembic/                 # baseline = no-op (existing DB)
tests/                   # pytest (in-memory SQLite)
```

## Local dev
```bash
python3.12 -m venv .venv && . .venv/Scripts/activate   # (Windows: .venv\Scripts\activate)
pip install -e ".[dev]"
cp .env.example .env        # fill in DATABASE_URL, JWT_SECRET, DISCORD_*, GOOGLE_*
uvicorn app.main:app --reload --port 8080
```
Docs: http://localhost:8080/api/docs

## Tests
```bash
pip install -e ".[dev]"
pytest                      # 16 tests, in-memory SQLite, no external services
```

## Architecture notes
- **Layering**: router → service → repository → model. Routers do no SQL and no
  business logic; services own transforms (e.g. `holo` int→bool, empty `ed`→
  "Unlimited"); repositories own queries (faithful ports of `sqlhelper.py`).
- **DI**: `app/api/dependencies/services.py` is the composition root using
  FastAPI `Depends`; no global singletons except the stateless `DriveService`.
- **Auth**: Discord OAuth (scope `identify`) → our JWT access (15 min, header) +
  refresh (7 day, httpOnly cookie). The legacy `sessions` table is unused.
- **Alembic**: baseline is a no-op against the live DB; `env.py` only manages the
  seven web-app tables, never the Discord-bot tables.
