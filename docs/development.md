# Development

How the code is organised and how to work on it. Code conventions are described in detail in [CLAUDE.md](../CLAUDE.md); the contribution process is in [CONTRIBUTING.md](../CONTRIBUTING.md).

## Tech stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| Backend | Python 3.12, FastAPI, Uvicorn | SQLAlchemy 2.0 ORM, Pydantic v2 schemas |
| Database | PostgreSQL 16 (production) / SQLite (development and tests) | Alembic migrations; missing columns are also added on startup |
| Auth | Own HS256 JWT implementation + bcrypt | Token version claim for session invalidation |
| Frontend | SvelteKit 2, Svelte 5, TypeScript, Vite 6 | Node adapter in Docker |
| Maps | MapLibre GL + OpenFreeMap | Free vector tiles, no API key, light and dark style |
| Offline | Service worker + Web Bluetooth | PWA caching, offline request queue, BitChat BLE mesh gateway |
| Languages | svelte-i18n | 12 languages, including right-to-left Arabic and Farsi |
| Deployment | Docker Compose | `db`, `backend`, `frontend` |

## Local development without Docker

The backend uses SQLite by default, so you don't need PostgreSQL.

**Backend** (http://localhost:8300):

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
NG_DEBUG=true uvicorn app.main:app --reload --port 8300
```

`NG_DEBUG=true` accepts the default secret key; never use it in production.

**Frontend** (http://localhost:5173), in a second terminal:

```bash
cd frontend
npm install
npm run dev
```

The Vite dev server proxies `/api/*` to the backend on port 8300, so open http://localhost:5173. Interactive API docs are at http://localhost:8300/docs.

## Checks before a pull request

```bash
cd backend && pytest
```

```bash
cd frontend && npm run check
```

```bash
cd frontend && npm test
```

```bash
cd frontend && npm run check:i18n
```

`pytest` runs the backend suite (711 tests, in-memory SQLite, no database needed). `npm run check` runs svelte-check and TypeScript, `npm test` the frontend unit tests, and `check:i18n` makes sure every UI string exists in all 12 languages.

## Database migrations

After changing a model:

```bash
cd backend
alembic revision --autogenerate -m "short description"
alembic upgrade head
```

Review the generated file before applying it. Give new columns a scalar `default=` or make them nullable, because self-hosted instances add missing columns on startup and backfill that default.

## Project structure

```
neighbourgood/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI app, middleware, startup (tables + missing columns)
│   │   ├── config.py        # Settings (NG_ environment variables)
│   │   ├── models/          # SQLAlchemy models, one file per domain
│   │   ├── routers/         # API routes, one file per domain
│   │   ├── schemas/         # Pydantic request/response schemas
│   │   ├── services/        # Auth, notifications, Telegram, AI, mesh signing, webhooks, …
│   │   └── middleware/      # Rate limiting, CSRF, body size limit
│   ├── alembic/             # Database migrations
│   └── tests/               # pytest suite
├── frontend/
│   ├── src/
│   │   ├── routes/          # SvelteKit pages
│   │   ├── lib/             # API client, stores, components, i18n (12 locales)
│   │   ├── app.css          # Global styles and Blue/Red Sky themes
│   │   └── service-worker.ts
│   └── static/              # Static assets and PWA manifest
├── brand/                   # Logo, marks, wordmarks, app icons
├── docs/                    # Documentation (you are here)
├── docker-compose.yml
├── install.sh               # One-line installer
└── .env.example             # Configuration template
```

## API

The full endpoint reference is in [api.md](api.md). With the backend running, interactive docs are at `/docs` (Swagger) and `/redoc`.
