# CLAUDE.md — NeighbourGood Codebase Guide

> For AI assistants working on this repository. Read this before making any changes.

---

## Model Usage Policy

Token efficiency matters. Use the right model for the right task:

| Model | When to use | Examples |
|-------|-------------|---------|
| **Haiku** `claude-haiku-4-5-20251001` | Quick, cheap tasks — default starting point | File searches, single-line fixes, reading docs, grepping for a symbol, status checks, typo corrections, explaining a short function |
| **Sonnet** `claude-sonnet-4-6` | Standard coding work | New features, bug fixes, multi-file refactors, writing tests, schema changes, adding endpoints |
| **Opus** `claude-opus-4-6` | Save for the hardest problems only | Architecture decisions, complex security analysis, orchestrating multi-agent plans, debugging tricky async/concurrency/race-condition bugs, analysing attack surfaces |

**Default to Haiku.** Escalate to Sonnet when a task clearly spans multiple files or requires system-wide reasoning. Reserve Opus for genuine deep-thinking — it is expensive and slow. Never use Opus for searches, reads, or anything grep can answer in one shot.

---

## Project Overview

**NeighbourGood v1.9.5.1** — a self-hostable, federation-ready community resource-sharing platform with a **dual-state architecture**:

- **Blue Sky Mode** (normal operation): resource library, skill exchange, calendar bookings, reputation/trust scores, community feed, direct messaging
- **Red Sky Mode** (crisis operation): per-community crisis toggle or 60%-threshold community vote, emergency ticketing (request / offer / ping), neighbourhood leader roles, cross-instance Red Sky alerts

Each instance exposes `/instance/info` so instances can discover and federate with each other.

Current test count: **418 tests** across 28 test files (all backend, pytest + in-memory SQLite).

---

## Tech Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| Backend | Python 3.12 + FastAPI 0.115 | Async-capable, served by Uvicorn |
| ORM | SQLAlchemy 2.0 | `Mapped[type]` + `mapped_column()` style only |
| Validation | Pydantic v2 + pydantic-settings | All schemas; `pydantic[email]` for `EmailStr` |
| Database | PostgreSQL 16 (prod) / SQLite (dev + tests) | Switched via `NG_DATABASE_URL` |
| Migrations | Alembic 1.14 | `render_as_batch=True` for SQLite compat |
| Auth | Custom HS256 JWT (stdlib) + bcrypt via passlib | No third-party JWT library on purpose |
| Frontend | SvelteKit 2 + Svelte 5 + TypeScript | Node adapter in Docker; static adapter option |
| Build tool | Vite 6 | Dev proxy rewrites `/api` → backend |
| i18n | svelte-i18n | 7 languages (en, ar, fr, es, sw, id, uk) + RTL |
| Deployment | Docker Compose | 3 services: `db` (pg), `backend`, `frontend` |

---

## Repository Structure

```
neighbourgood/
├── CLAUDE.md               # This file
├── README.md               # User-facing docs and quick start
├── CHANGELOG.md            # Full version history (v0.1.0 → v1.1.0)
├── PLAN.md                 # Security hardening roadmap (phases 4a–5a)
├── PLAN_DESIGN.md          # UI/UX redesign plan
├── PLAN_I18N.md            # Internationalization plan
├── API_ENDPOINTS.md        # Full endpoint reference
├── SECURITY.md             # Security policy and vulnerability reporting
├── CONTRIBUTING.md         # Contribution guidelines
├── CODE_OF_CONDUCT.md      # Community code of conduct
├── .env.example            # Config template — copy to .env before running
├── .github/                # GitHub Actions workflows
├── docker-compose.yml      # Production-style 3-service stack
│
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── alembic/
│   │   ├── env.py              # Reads NG_DATABASE_URL; imports all models
│   │   └── versions/           # One migration file per schema change
│   ├── app/
│   │   ├── main.py             # FastAPI app + middleware registration + lifespan
│   │   ├── config.py           # pydantic-settings (NG_ prefix); startup key validation
│   │   ├── database.py         # Engine + SessionLocal + Base
│   │   ├── dependencies.py     # get_current_user() auth dependency
│   │   ├── models/             # SQLAlchemy ORM models (one file per domain)
│   │   ├── routers/            # Route handlers (one file per domain)
│   │   ├── schemas/            # Pydantic request/response schemas
│   │   └── services/           # auth, notifications, activity, telegram, webhooks
│   └── tests/
│       ├── conftest.py         # In-memory SQLite fixtures + auth_headers
│       └── test_*.py           # 21 test files, one per router/domain
│
└── frontend/
    ├── Dockerfile
    ├── package.json
    └── src/
        ├── app.html            # HTML shell
        ├── app.css             # Global CSS + Blue/Red Sky CSS custom properties
        ├── hooks.server.ts     # Server-side /api proxy → backend
        ├── service-worker.ts   # PWA offline caching + background sync
        ├── lib/
        │   ├── api.ts          # api() and apiUpload() fetch wrappers
        │   ├── types.ts        # Shared TS interfaces mirroring backend schemas
        │   ├── i18n/           # Internationalisation
        │   │   ├── index.ts        # svelte-i18n setup + locale detection
        │   │   └── locales/        # en, ar, fr, es, sw, id, uk JSON files
        │   └── stores/
        │       ├── auth.ts     # token, user, isLoggedIn, logout()
        │       ├── theme.ts    # light/dark toggle, localStorage persistence
        │       ├── locale.ts   # currentLocale, isRTL, setLocale(), hydrateLocale()
        │       └── offline.ts  # isOnline, offlineQueue, enqueueRequest(), flushQueue()
        └── routes/             # SvelteKit file-based routing
            ├── +layout.svelte
            ├── +page.svelte          # Home / landing page
            ├── dashboard/            # User dashboard (v1.0.0)
            ├── login/
            ├── register/
            ├── onboarding/           # 3-step wizard (search / join / create community)
            ├── resources/[id]/
            ├── bookings/
            ├── messages/
            ├── skills/
            │   └── [id]/             # Skill detail + messaging
            ├── communities/[id]/
            ├── explore/              # Public map (Leaflet / OSM) for guests
            ├── invites/[code]/       # Invite acceptance
            ├── triage/               # Crisis dashboard (v0.9.8)
            │   └── [id]/             # Emergency ticket detail + discussion
            └── settings/             # User settings — theme & language (v1.1.0)
```

---

## Development Workflows

### Local dev (no Docker)

```bash
# Backend — uses SQLite by default
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
NG_DEBUG=true uvicorn app.main:app --reload --port 8300

# Frontend — separate terminal
cd frontend
npm install
npm run dev          # Vite dev server on :5173; /api proxy → :8300
```

### Docker (recommended for integration testing)

```bash
cp .env.example .env
echo "NG_SECRET_KEY=$(openssl rand -hex 32)" >> .env
docker compose up --build
# Frontend:       http://localhost:3800
# Backend API:    http://localhost:8300
# Swagger docs:   http://localhost:8300/docs
```

### Database migrations

```bash
cd backend
# After changing a model:
alembic revision --autogenerate -m "short description"
alembic upgrade head

# In Docker the app auto-creates tables via Base.metadata.create_all().
# The lifespan handler also auto-adds missing columns on startup (for iterative dev).
# For schema changes on a running container, exec into it and run alembic upgrade head.
```

### Running tests

```bash
cd backend
pytest                          # full suite (~200 tests, ~5 s)
pytest tests/test_auth.py -v    # single file
pytest --tb=short               # compact tracebacks
```

Tests use an in-memory SQLite database — no real DB needed. `NG_DEBUG=true` is set automatically in `conftest.py` so the default secret key is accepted.

### Frontend type checking

```bash
cd frontend
npm run check        # svelte-check + TypeScript
```

---

## Environment Variables

All prefixed `NG_`. The app reads from `.env` via pydantic-settings.

| Variable | Required | Default | Notes |
|----------|----------|---------|-------|
| `NG_SECRET_KEY` | **Yes (prod)** | (default rejected) | JWT signing key, ≥ 32 chars; generate with `openssl rand -hex 32` |
| `NG_DATABASE_URL` | No | `sqlite:///./neighbourgood.db` | Set to postgres URL in production |
| `NG_DEBUG` | No | `false` | `true` for local dev — relaxes key check, HSTS, CSP |
| `NG_PLATFORM_MODE` | No | `blue` | `blue` or `red` (global default; per-community mode overrides this) |
| `NG_CORS_ORIGINS` | No | `["http://localhost:3800","http://localhost:5173"]` | JSON array |
| `NG_SMTP_HOST/PORT/TLS/USER/PASSWORD/FROM` | No | unset | Logs emails to console when unconfigured |
| `NG_FRONTEND_URL` | No | `http://localhost:3800` | Used in notification email links |
| `NG_INSTANCE_NAME/DESCRIPTION/REGION/URL` | No | — | Federation identity shown at `/instance/info` |
| `NG_ADMIN_NAME/ADMIN_CONTACT` | No | — | Federation accountability metadata |
| `NG_TELEGRAM_BOT_TOKEN` | No | unset | Telegram Bot API token; disables integration when unset |

---

## Backend Conventions

### Models (`app/models/`)

- **One file per domain.** All inherit from `app.database.Base`.
- Use SQLAlchemy 2.0 **`Mapped[type]` + `mapped_column()`** — never the old `Column()` style.
- Add `index=True` to all foreign key columns (performance; established pattern since v0.5.0).
- Register new models in **three places**: `app/models/__init__.py`, `app/main.py` top-level imports, and `alembic/env.py` imports.

```python
# Correct pattern
class MyModel(Base):
    __tablename__ = "my_models"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
```

### Schemas (`app/schemas/`)

- Pydantic v2. Naming convention: `XxxCreate` (POST body), `XxxOut` (response), `XxxUpdate` (PATCH body).
- **All user-facing string fields must have `max_length`** (enforced since v0.8.0):
  - `display_name` / `neighbourhood`: 100 chars
  - `title`: 200 chars
  - `description` / `body` / `message`: 5000 chars
- Use `pydantic.EmailStr` for email fields.
- Password validation (in `schemas/auth.py`): min 8 chars, ≥ 1 uppercase, ≥ 1 lowercase, ≥ 1 digit.

### Routers (`app/routers/`)

- One file per domain. Register in `main.py` with `app.include_router(...)`.
- Always inject: `db: Session = Depends(get_db)` and (when auth required) `current_user: User = Depends(get_current_user)`.
- Always declare `response_model=` on every route decorator.
- Return Pydantic schema objects — never raw SQLAlchemy model instances.

```python
@router.get("/{id}", response_model=MyOut)
def get_item(id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    item = db.query(MyModel).filter(MyModel.id == id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    return item
```

### Services (`app/services/`)

| Service | Key exports |
|---------|-------------|
| `auth.py` | `hash_password()`, `verify_password()`, `create_access_token()`, `decode_access_token()` |
| `notifications.py` | `send_notification()` — logs to console when SMTP unconfigured |
| `activity.py` | `log_activity()` — call after writes to generate community feed entries |
| `telegram.py` | `send_message()`, `is_configured()`, `set_webhook()` — Telegram Bot API client |
| `webhooks.py` | Outbound webhook delivery, HMAC-SHA256 signature verification, event broadcasting |

### Configuration (`app/config.py`)

- `settings` is a module-level singleton — import and use; do not instantiate `Settings()` again.
- `settings.debug = True` relaxes: default secret key acceptance, HSTS header, strict CSP.
- Startup guards (cannot be bypassed without `debug=True`): default secret key rejected, key < 32 chars rejected.

### Lifespan & Auto-migration (`app/main.py`)

The lifespan context manager runs at startup:
1. Creates all tables via `Base.metadata.create_all()`.
2. Applies additive column migrations for iterative development (adds missing columns without Alembic).

Do not rely on this for production schema changes — always write a proper Alembic migration.

---

## Frontend Conventions

### API client (`src/lib/api.ts`)

Always use these wrappers — never raw `fetch()` in route files.

```typescript
// Authenticated GET
const items = await api<Resource[]>('/resources', { auth: true });

// POST with JSON body
await api('/bookings', { method: 'POST', body: { resource_id: 1 }, auth: true });

// File upload (multipart)
const result = await apiUpload<{ image_url: string }>('/resources/1/image', file);
```

All paths are relative to `/api` (e.g. `/resources`, not `/api/resources`).

### Stores (`src/lib/stores/`)

| Store | Exports | Persistence |
|-------|---------|-------------|
| `auth.ts` | `token`, `user`, `isLoggedIn`, `logout()` | `localStorage` key `ng_token` |
| `theme.ts` | `theme` (`'light'\|'dark'`), `toggleTheme()` | `localStorage` key `ng_theme`; sets `data-theme` on `<html>` |
| `locale.ts` | `currentLocale`, `isRTL`, `setLocale(code)`, `hydrateLocale(code)`, `AVAILABLE_LOCALES` | `localStorage`; syncs to user profile |
| `offline.ts` | `isOnline`, `offlineQueue`, `queueCount`, `enqueueRequest(req)`, `removeFromQueue(id)`, `flushQueue()`, `initOfflineTracking()` | In-memory; replayed on reconnect |

### Internationalisation (`src/lib/i18n/`)

- Uses `svelte-i18n`. Setup and locale detection in `i18n/index.ts`.
- 7 supported languages: `en`, `ar`, `fr`, `es`, `sw`, `id`, `uk`.
- Arabic (`ar`) requires RTL layout — check `$isRTL` from `locale.ts` to apply `dir="rtl"` where needed.
- Translation strings live in `i18n/locales/<lang>.json`; always add a key to all 7 files when adding new UI text.
- Graceful fallback to English if a key is missing in a locale.

### Offline / PWA (`src/service-worker.ts`)

- Caches static assets and resource browse responses for offline access.
- `offline.ts` tracks `navigator.onLine` and queues state-changing API calls made while offline.
- Call `initOfflineTracking()` once in the root layout `onMount` to register event listeners.
- When back online, `flushQueue()` replays queued requests in order.

### Types (`src/lib/types.ts`)

Shared TypeScript interfaces that mirror backend Pydantic schemas. Always import from `$lib/types` — do not redefine locally. Includes `statusColor(status)` utility for mapping booking statuses to CSS variable strings.

### Routing

- SvelteKit file-based. Dynamic params via `$page.params` (e.g. `[id]`, `[code]`).
- All authenticated pages must check `$isLoggedIn` and call `goto('/login')` if false.
- Use `goto()` from `$app/navigation` for programmatic navigation.

### Theming

- Blue Sky / Red Sky themes are CSS custom-property sets in `app.css`.
- Available variables: `--color-primary`, `--color-bg`, `--color-surface`, `--color-text`, `--color-text-muted`, `--color-success`, `--color-warning`, `--color-error`.
- Always use CSS variables — never hardcode hex colors in components (regression from v0.5.0).

---

## Domain Model Summary

| Model | Key fields | Notes |
|-------|-----------|-------|
| `User` | id, email, hashed_password, display_name, neighbourhood, role, is_active, telegram_chat_id, preferred_language | roles: `member`, `admin` |
| `Resource` | id, title, category, condition, image_url, is_available, owner_id, community_id | community_id nullable (personal items) |
| `Booking` | id, resource_id, borrower_id, start_date, end_date, status, message | statuses: pending → approved/rejected → completed/cancelled |
| `Message` | id, sender_id, recipient_id, booking_id, body, is_read | only between users sharing a community |
| `Community` | id, name, postal_code, city, country_code, mode, latitude, longitude, merged_into_id, is_active | mode: blue/red |
| `CommunityMember` | id, community_id, user_id, role | roles: member, leader, admin |
| `Skill` | id, user_id, community_id, title, category, skill_type, description | skill_type: offer/request; 10 categories |
| `Activity` | id, community_id, user_id, action_type, object_type, object_id, summary | auto-generated feed entries |
| `EmergencyTicket` | id, community_id, author_id, ticket_type, title, status, priority | types: request/offer/ping; ping = Red Sky only |
| `TicketComment` | id, ticket_id, author_id, body | Discussion thread on emergency tickets |
| `CrisisVote` | id, community_id, user_id, vote | 60% threshold auto-switches mode |
| `Invite` | id, community_id, created_by_id, code, max_uses, uses, expires_at | URL-safe codes |
| `Review` | id, booking_id, reviewer_id, reviewee_id, rating, comment | 1–5 stars, per completed booking |
| `KnownInstance` | id, instance_url, name, region, last_seen_at | federation directory |
| `RedSkyAlert` | id, source_instance_url, title, body, severity, expires_at | cross-instance crisis alerts |
| `Webhook` | id, owner_id, url, secret, events, is_active | outbound webhook subscriptions |
| `TelegramLinkToken` | id, user_id, token, expires_at | one-time tokens for Telegram account linking |

---

## API Endpoint Map

Full reference: `API_ENDPOINTS.md`. Interactive: `http://localhost:8300/docs`.

| Prefix | Router file | Description |
|--------|-------------|-------------|
| `/status` | status.py | Platform mode and version |
| `/auth` | auth.py | register, login |
| `/users` | users.py | profile, reputation score |
| `/resources` | resources.py | CRUD, image upload, search, categories |
| `/bookings` | bookings.py | create, approve/reject, complete, cancel, calendar |
| `/messages` | messages.py | conversations, send, mark read, contacts |
| `/communities` | communities.py | CRUD, join/leave, members, merge, map |
| `/crisis` | crisis.py | toggle, vote, tickets, leader management |
| `/skills` | skills.py | offer/request listings, search |
| `/activity` | activity.py | community feed |
| `/invites` | invites.py | generate and redeem codes |
| `/reviews` | reviews.py | booking reviews and user averages |
| `/instance/info` | instance.py | public metadata for federation crawlers |
| `/federation` | federation.py | instance directory, Red Sky alert broadcast |
| `/webhooks` | webhooks.py | CRUD outbound webhooks + inbound handler |
| `/matching` | matching.py | Smart suggestions, unmet needs, AI status |
| `/users/me/telegram` | telegram.py | link/unlink Telegram account |

---

## Security State (from PLAN.md)

### Phase 4a — Implemented in v0.8.0 ✅

- Password strength validation (min 8 chars, upper + lower + digit) — `schemas/auth.py`
- Email format validation via `EmailStr` — `schemas/auth.py`
- Security response headers (X-Content-Type-Options, X-Frame-Options, Referrer-Policy, Permissions-Policy, HSTS in prod, basic CSP) — `SecurityHeadersMiddleware` in `main.py`
- Secret key validation on startup — `config.py`
- File upload hardening: magic byte check + extension allowlist (`.jpg/.jpeg/.png/.webp/.gif`) + double-extension strip — `routers/resources.py`
- Input `max_length` on all user-facing schema fields — `schemas/*.py`

### Phase 4b — Pending (next priority) ⏳

- **Rate limiting** on auth endpoints (`/auth/login`, `/auth/register`): 5 req/min per IP; general API: 60 req/min; uploads: 10 req/min. New file: `app/middleware/rate_limit.py` (in-memory sliding window, no external dep). Return `429` with `Retry-After` header.
- **Account lockout**: track failed login attempts per email; lock for 15 min after 5 failures in 15 min. In-memory store with TTL. New logic in `routers/auth.py`.
- **CSRF protection** for state-changing operations.
- **Session invalidation** on password change.
- **Audit logging** for admin actions — new `app/services/audit.py`, structured JSON logs to `logs/security.log`.
- **Hardened auth responses**: unify error messages to always return `"Invalid credentials"` (prevent user enumeration via timing or message differences).

### Phase 4c / 5a — Future ⏳

- Field-level encryption for sensitive data (email, messages)
- Automated encrypted database backups
- PII anonymisation for deleted accounts
- CSP tuning per route
- Dependency vulnerability scanning (pip-audit in CI)
- TLS automation (Let's Encrypt), container image scanning, secrets management (Vault)

**Do not regress any Phase 4a items.** When adding new schemas, always include `max_length`. When adding new endpoints, always use `SecurityHeadersMiddleware` (already applied globally). When adding new upload handlers, apply the same magic byte + extension validation pattern.

---

## Reputation System

Scoring (computed on-the-fly, not stored):

| Action | Points |
|--------|--------|
| Resource shared (listed) | +2 |
| Lending completed | +10 |
| Borrowing completed | +5 |
| Skill offered | +2 |
| Skill requested | +1 |

Levels: **Newcomer** (0–9) → **Neighbour** (10–39) → **Helper** (40–99) → **Trusted** (100–199) → **Pillar** (200+)

---

## Test Fixtures Quick Reference

```python
# conftest.py provides:
client          # FastAPI TestClient with in-memory SQLite DB override
auth_headers    # {"Authorization": "Bearer <token>"} for a registered test user
db              # raw SQLAlchemy session (for direct DB assertions)

# Test user credentials:
# email: test@example.com  password: Testpass123  display_name: Test User
```

Pattern for every test file:

```python
def test_success(client, auth_headers):
    res = client.post("/endpoint", json={...}, headers=auth_headers)
    assert res.status_code == 201

def test_unauthenticated(client):
    res = client.get("/protected-endpoint")
    assert res.status_code == 403   # HTTPBearer returns 403 when no token

def test_not_found(client, auth_headers):
    res = client.get("/resources/99999", headers=auth_headers)
    assert res.status_code == 404
```

Current test files (26): `test_activity`, `test_auth`, `test_bookings`, `test_communities`, `test_crisis`, `test_events`, `test_federation`, `test_federation_sync`, `test_instance`, `test_inventory`, `test_invites`, `test_matching`, `test_mesh_sync`, `test_messages`, `test_notifications`, `test_reputation`, `test_resource_community`, `test_resources`, `test_resources_phase2`, `test_reviews`, `test_skills`, `test_status`, `test_telegram`, `test_triage`, `test_users`, `test_webhooks`.

---

## Version History Summary

| Version | Date | Highlights |
|---------|------|-----------|
| 1.9.5.1 | 2026-03-16 | Fix login 500 (restore additive column auto-migration), move mesh networking to settings toggle (hidden by default), mesh settings store + i18n |
| 1.9.5 | 2026-03-16 | Enhanced BLE mesh networking: 10-phase overhaul (mesh dashboard, auto-sync, resource sharing, check-ins, multi-hop relay, message ACKs, offline triage, E2E encryption, multi-device manager, analytics/diagnostics), improved offline functionality, i18n for offline UI, 20 new tests (418 total) |
| 1.9.0 | 2026-03-15 | Federation explorer UI: instance directory browser, federated resource/skill pages, cross-instance alert banners, enriched instance stats (resource/skill/event/active-user counts), federation router prefix fix, 27 new tests (398 total) |
| 1.8.0 | 2026-03-13 | Hyperlocal community events: create/browse/RSVP events (9 categories, max-attendee cap, upcoming filter, full-text search), activity feed + webhook integration, /events frontend page, nav link, 12-locale i18n, 22 new tests (371 total) |
| 1.7.0 | 2026-03-10 | Security Phase 4b: in-memory rate limiting (5/60/10 req/min), account lockout after 5 failures, CSRF double-submit protection, hardened login error messages, 22 new tests |
| 1.6.0 | 2026-03-08 | AI-powered Telegram bot natural language interface: mode-aware system prompts (Blue Sky warm, Red Sky urgent), intent classification and execution (search/list resources, skills, crisis summary, create emergency requests), group chat crisis keyword responses, comprehensive setup and customisation docs, 13 new tests |
| 1.5.0 | 2026-03-07 | Smart matching engine with optional AI enhancement: rule-based skill/resource matching, unmet emergency needs surfacing, Ollama/OpenAI-compatible LLM re-ranking, 20 new tests |
| 1.4.0 | 2026-03-07 | Decentralized data sync between instances: public snapshot endpoint, pull-based sync from all known peers, incremental cursors, federated resource/skill browsing, 33 new tests |
| 1.3.0 | 2026-03-07 | Frontend refactor: extract CrisisModePanel, MembersList, InviteLinks sub-components; shared ErrorMessage/LoadingSpinner; backend utils (authorization.py, db.py, file_upload.py); remove lifespan auto-migration; lighter desktop heading font weights |
| 1.2.0 | 2026-03-02 | BitChat BLE mesh gateway integration: offline crisis communication via Bluetooth Low Energy, Web Bluetooth connection manager, mesh Svelte store, POST /mesh/sync endpoint, 260 tests |
| 1.1.0 | 2026-03-01 | Phase 5 complete: offline item browsing, request queuing, background sync, data export; Phase 6 start: multi-language support (7 languages + RTL), image upload fixes |
| 1.0.0 | 2026-02-27 | Production release: reputation rebalancing, 3-step onboarding wizard, Telegram bot integration, community activity timeline, skills in messaging, 198+ tests |
| 0.9.9 | 2026-02-26 | PWA support with offline-first service worker, installable web app, dashboard crisis ticket widget, design refinements, enhanced reputation system |
| 0.9.8 | 2026-02-25 | User dashboard, ticket detail page with discussion, global Red Sky awareness, UI redesign (warm palette, Abril Fatface headings, SVG logo), navigation restructuring |
| 0.9.5 | 2026-02-24 | Low-bandwidth mode, triage dashboard, community-filtered resources/skills, eager-loading N+1 fix, enhanced API error handling |
| 0.9.0 | 2026-02-19 | Red Sky mode per community, crisis voting (60%), emergency tickets, leader roles, explore map, 198 tests |
| 0.8.0 | 2026-02-19 | Mobile nav, community-scoped messaging, Security Phase 4a hardening |
| 0.7.0 | 2026-02-18 | Skill exchange, reputation/trust scores, activity feed, invite system, reviews |
| 0.6.0 | 2026-02-18 | Instance identity, federation prep, community-scoped resources, PostgreSQL default |
| 0.5.0 | 2026-02-18 | Community system, onboarding flow, merge suggestions, shared TS types |
| 0.4.0 | 2026-02-17 | In-app messaging, email notifications |
| 0.3.0 | 2026-02-17 | Bookings, image upload, search |
| 0.2.0 | 2026-02-17 | Auth (JWT + bcrypt), resource CRUD, frontend |
| 0.1.0 | 2026-02-17 | Project scaffold, dual-mode /status, Blue/Red Sky CSS, Docker Compose |

---

## Common Task Recipes

### Add a new backend domain

1. Create `app/models/newdomain.py` (inherit `Base`, use `Mapped` style)
2. Create `app/schemas/newdomain.py` (Create / Out / Update; add `max_length` to strings)
3. Create `app/routers/newdomain.py` (use `Depends(get_current_user)` and `Depends(get_db)`)
4. Register in `app/models/__init__.py`, `app/main.py`, and `alembic/env.py`
5. Run `alembic revision --autogenerate -m "add newdomain"` then `alembic upgrade head`
6. Add `tests/test_newdomain.py` (cover success + 401 + 404 + 422 cases)

### Add a new frontend page

1. Create `frontend/src/routes/mypage/+page.svelte`
2. Import `api` from `$lib/api`, types from `$lib/types`, stores from `$lib/stores/auth`
3. Guard with `if (!$isLoggedIn) goto('/login')` in `onMount`
4. Use CSS variables only — no hardcoded colours
5. Add translation keys for any new UI strings to all 7 locale JSON files in `src/lib/i18n/locales/`
6. Add nav link in `+layout.svelte` if needed

### Add a new Alembic migration

```bash
cd backend
# Models must already be updated before running this
alembic revision --autogenerate -m "add foo_column to resources"
# Review the generated file in alembic/versions/ before applying
alembic upgrade head
```

### Add i18n strings

```bash
# Add the key to ALL locale files:
frontend/src/lib/i18n/locales/en.json   # English (authoritative)
frontend/src/lib/i18n/locales/ar.json   # Arabic (RTL)
frontend/src/lib/i18n/locales/fr.json   # French
frontend/src/lib/i18n/locales/es.json   # Spanish
frontend/src/lib/i18n/locales/sw.json   # Swahili
frontend/src/lib/i18n/locales/id.json   # Indonesian
frontend/src/lib/i18n/locales/uk.json   # Ukrainian
```

If you only have the English string, add the key with the English value as a placeholder in the other files and note it needs translation.

---

## What Not To Do

- **Do not** use `allow_origins=["*"]` — always use `NG_CORS_ORIGINS`
- **Do not** use the old `Column()` SQLAlchemy style — use `Mapped[type]` + `mapped_column()`
- **Do not** hardcode colours in Svelte components — use CSS variables
- **Do not** use raw `fetch()` in route files — use `api()` / `apiUpload()`
- **Do not** skip `response_model=` on route decorators
- **Do not** omit `max_length` from new string schema fields
- **Do not** set `NG_DEBUG=true` in Docker production config
- **Do not** add features beyond what was asked — keep changes focused
- **Do not** create abstractions for one-off operations — three similar lines > premature abstraction
- **Do not** add docstrings or comments to code you did not change
- **Do not** hardcode UI strings — use `$t('key')` from svelte-i18n and add to all locale files
- **Do not** rely on the lifespan auto-migration for production schema changes — write a proper Alembic migration

---

## Git Branch Convention

- Feature branches: `claude/<short-description>-<session-id>`
- Always push to the designated branch — never to `master` directly
- Commit messages: present-tense imperative, explain *why* not just *what*
