# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [1.9.0] - 2026-03-15

### Added

- **Federation Explorer UI** — new `/federation` page making the decentralized federation system visible and usable
  - **Instance Directory** — browse known NeighbourGood instances as cards showing name, region, platform mode (blue/red), reachability status, and live stats
  - **Enriched instance stats** — `/instance/info` now exposes `resource_count`, `skill_count`, `event_count`, `active_user_count` (users active in last 30 days)
  - **Add Instance form** — authenticated users can add a peer instance by URL; the system fetches and validates its `/instance/info`
  - **Admin controls** — refresh all instances, trigger sync, remove instances (admin-only)
  - **Federated Resources browser** (`/federation/resources`) — browse resources synced from peer instances with category and source-instance filters
  - **Federated Skills browser** (`/federation/skills`) — browse skills from peers with type (offer/request), category, and source-instance filters
  - **Cross-instance alert banner** — active Red Sky alerts from other instances are shown as a dismissible, severity-colored banner in the global layout (info=blue, warning=yellow, critical=red)
  - **"Network" nav link** added to the main navigation for logged-in users
- **KnownInstance model** — 4 new columns: `resource_count`, `skill_count`, `event_count`, `active_user_count` with Alembic migration
- **`KnownInstance`, `FederatedResource`, `FederatedSkill`, `RedSkyAlertInfo` TypeScript interfaces** added to `src/lib/types.ts`
- **i18n** — `nav.federation` and full `federation.*` namespace (36 keys) added to all 12 locale files
- **27 new tests** in `test_federation.py` covering instance directory CRUD, Red Sky alert lifecycle, data export/import, and enriched instance info (398 tests total, 0 regressions)

### Fixed

- **Federation router prefix** — `federation.py` router was missing its `/federation` prefix, causing endpoints to be mounted at `/directory` instead of `/federation/directory`; all federation endpoints now correctly prefixed
- **Alert broadcast URL** — outbound Red Sky alert broadcast now posts to `/federation/alerts/receive` (was `/alerts/receive` before the prefix fix)

### Changed

- Backend version bumped to 1.9.0
- Frontend version bumped to 1.9.0

## [1.8.0] - 2026-03-13

### Added

- **Community Events** — hyperlocal event scheduling with RSVP, category filtering, and an upcoming-events toggle
  - `Event` model: title, description, category, start/end datetime, location, optional max-attendee cap, organizer, community
  - `EventAttendee` model with unique constraint on (event_id, user_id) — prevents duplicate RSVPs
  - 9 event categories: meetup, workshop, repair\_café, swap, gardening, food, sport, cultural, other
  - Full CRUD at `/events` — create (community members only), get, update and delete (organizer only)
  - `POST /events/{id}/attend` / `DELETE /events/{id}/attend` — RSVP with automatic full-event guard (HTTP 409)
  - `GET /events/categories` — category metadata (label + icon) for frontends
  - List endpoint with filters: `community_id`, `category`, `upcoming=true`, full-text `q` search
  - Auto-scoped to the authenticated user's joined communities when no `community_id` is given
  - Activity feed entry on event creation (`event_created`)
  - Webhook dispatch for `event.created` event type
  - Alembic migrations: `d1e2f3a4b5c6` (merge heads) → `f1a2b3c4d5e6` (create tables)
  - 22 new tests in `test_events.py` covering CRUD, auth guards, RSVP flow, capacity enforcement, and all filters (371 tests total, 0 regressions)
- **Events frontend page** (`/events`)
  - Filter bar: community selector, category dropdown, upcoming-only toggle, free-text search (300 ms debounce)
  - Inline create form with datetime pickers, location, max-attendee input, community selector, and description
  - Event cards showing category emoji, date/time range, location, organizer name, attendee count, and RSVP button
  - RSVP button disabled when the event is at capacity for non-attending users
- **`CommunityEvent` and `EventCategoryInfo` TypeScript interfaces** added to `src/lib/types.ts`
- **Nav link** "Events" added to the main navigation in `+layout.svelte`
- **i18n** — `nav.events` key and full `events.*` namespace (title, subtitle, search, create, filters, RSVP, categories) added to all 12 locale files

### Changed

- Backend version bumped to 1.8.0
- Frontend version bumped to 1.8.0

## [1.7.0] - 2026-03-10

### Added

- **Security Phase 4b — Rate limiting** (`app/middleware/rate_limit.py`)
  - In-memory sliding-window rate limiter with no external dependencies
  - Auth endpoints (`/auth/login`, `/auth/register`): 5 requests / 60 s per IP
  - Upload endpoints (paths ending with `/image`): 10 requests / 60 s per IP
  - All other API paths: 60 requests / 60 s per IP
  - Returns HTTP `429 Too Many Requests` with a `Retry-After` header
  - Middleware is bypassed in debug mode so the test suite is unaffected
- **Security Phase 4b — Account lockout** (`app/services/lockout.py`)
  - In-memory per-email failure tracker with a 15-minute sliding window
  - After 5 failed login attempts the account is locked for 15 minutes
  - Successful login clears the failure counter
  - Returns HTTP `429` with a `Retry-After` header and a clear message when locked
  - Email matching is case-insensitive
- **Security Phase 4b — CSRF protection** (`app/middleware/csrf.py`)
  - Double-submit token + Origin header validation for state-changing requests
  - Bearer-authenticated requests are exempt (browsers cannot forge the `Authorization` header cross-origin without a CORS preflight)
  - Machine-to-machine endpoints (Telegram webhook, federation receive, mesh sync) are explicitly exempt
  - `GET /auth/csrf-token` endpoint issues HMAC-SHA256-signed tokens valid for 24 hours
  - Middleware is bypassed in debug mode; enforced in production
- **Hardened login error message** — `POST /auth/login` now always returns `"Invalid credentials"` for both unknown email and wrong password, preventing user enumeration (Phase 4b item)
- 22 new tests in `tests/test_security_phase4b.py` covering rate-limit store logic, account lockout (unit + integration), CSRF token generation/validation, and CSRF middleware enforcement in production mode

### Changed

- Backend version bumped to 1.7.0

## [1.6.0] - 2026-03-08

### Added

- **AI-powered Telegram bot natural language interface** — linked users can send plain-text messages to the bot and get instant responses without opening the app
  - Intent classification via LLM (Ollama, OpenAI, or any compatible API)
  - `search_resource`: "Do you have a ladder?" → searches available items in user's community
  - `list_resources`: "What can I borrow?" → lists all available resources
  - `search_skill`: "Who can help with plumbing?" → finds matching skill offers
  - `summarize_crisis`: "What emergency tickets are open?" → Red Sky crisis summary
  - `create_request`: "I need food, no power" → creates emergency request ticket (Red Sky only)
  - **Mode-aware system prompts** — separate Blue Sky (warm, community-building) and Red Sky (direct, urgent) personas
  - Group chat auto-response on crisis keywords (crisis, emergency, ticket, what's happening)
  - Graceful no-AI fallback: returns slash-command help text when AI not configured
  - 13 new tests covering all intents, no-AI fallback, unlinked user guard, group chat, and mode-specific behaviour
- **Comprehensive Telegram setup and customisation documentation**
  - `TELEGRAM_SETUP.md` — end-to-end bot creation via BotFather, environment config, webhook registration, account/group linking, local AI setup
  - **AI model recommendations** — Llama 3.2 3B (default, fast), Phi-4 Mini (excellent JSON, low hallucination), Mistral 7B (best reasoning)
  - OpenAI alternative configuration guide
  - `TELEGRAM_AGENT.md` — developer customisation guide covering system prompts, adding new intents, fallback behaviour, reply formatting
- Backend and frontend versions bumped to 1.6.0

## [1.5.0] - 2026-03-07

### Added

- **Smart matching engine with optional AI enhancement** — rule-based skill/resource matching that works out of the box, with optional LLM re-ranking via Ollama or any OpenAI-compatible API
  - `GET /matching/suggestions` — personalised skill match and resource suggestions based on community membership, booking history, category overlap, keyword similarity, and provider reputation
  - `GET /matching/unmet-needs` — surfaces open emergency requests with few or no matching offers during Red Sky mode (leaders/admins only)
  - `GET /matching/status` — reports whether AI enhancement is available
  - New `AIClient` service (`app/services/ai_client.py`) — generic OpenAI-compatible HTTP client that works with both Ollama (`/v1/chat/completions`) and OpenAI/compatible APIs via a single code path
  - New configuration: `NG_AI_PROVIDER` (ollama/openai), `NG_AI_BASE_URL`, `NG_AI_MODEL`, `NG_AI_API_KEY` — all optional; matching works purely rule-based when unset
  - 20 new backend tests covering skill matching, resource suggestions, unmet needs, AI enhancement (mocked), graceful fallback, auth guards, and edge cases
- Backend and frontend versions bumped to 1.5.0

## [1.4.0] - 2026-03-07

### Added

- **Decentralized data sync between instances** — pull-based federation sync so NeighbourGood instances can discover and cache each other's public resources and skills
  - `GET /federation/sync/snapshot` — public endpoint exposing this instance's available resources and skills for remote peers to pull; supports `?since=` ISO-8601 timestamp for incremental sync
  - `POST /federation/sync/pull` — admin endpoint that pulls snapshots from all reachable known instances, upserts `federated_resources` / `federated_skills` records, and records outcome in `instance_sync_logs`; automatically uses the last successful sync timestamp as a cursor to minimise transfer size
  - `GET /federation/sync/status` — shows last sync result (status, item counts, error) per known instance
  - `GET /federation/federated-resources` — browse resources synced from other instances; filterable by category, source instance, and availability
  - `GET /federation/federated-skills` — browse skills synced from other instances; filterable by category, skill type, and source instance
  - Three new SQLAlchemy models: `FederatedResource`, `FederatedSkill`, `InstanceSyncLog`
  - 33 new backend tests covering snapshot filtering, pull upsert/error/cursor logic, sync status, and browse filtering

## [1.3.0] - 2026-03-07

### Changed

- **Frontend refactor** — reduce `communities/[id]/+page.svelte` from ~1,730 to ~600 LOC by extracting three dedicated sub-components:
  - `CrisisModePanel.svelte` — crisis toggle, voting UI, and Red Sky status
  - `MembersList.svelte` — member roster with role badges and leader management actions
  - `InviteLinks.svelte` — invite code generation and display
- **Shared UI components** — added `ErrorMessage.svelte` and `LoadingSpinner.svelte` to `src/lib/components/` for consistent error and loading states across pages
- **Shared types** — added `CrisisStatus`, `InviteOut`, `TicketList`, and `ResourceItem` interfaces to `src/lib/types.ts`; removed local redefinitions
- **Backend utilities** — added `app/utils/authorization.py` (ownership/membership guards) and `app/utils/db.py` (common query helpers) to reduce router boilerplate
- **File upload service** — extracted image magic-byte + extension validation from `routers/resources.py` into `app/services/file_upload.py`; no behaviour change
- **Removed lifespan auto-migration** — deleted the additive column-migration code from `app/main.py`; schema changes must now use proper Alembic migrations
- **Heading font weights** — reduced desktop heading weights to match the lighter mobile feel:
  - `h2` section headings: 600 → 500
  - `h3` card headings: 600–700 → 500
  - `h1` on explore and onboarding pages: 700 → 400
  - Global `h3`–`h6` baseline (500) added to `app.css`
- Backend and frontend versions bumped to 1.3.0

## [1.2.0] - 2026-03-02

### Added

- **BitChat BLE Mesh Gateway** — offline crisis communication via Bluetooth Low Energy
  - Web Bluetooth connection manager (`src/lib/bluetooth/connection.ts`) — scan, connect, and exchange binary data with a nearby native BitChat node using the GATT characteristic `A1B2C3D4-E5F6-4A5B-8C9D-0E1F2A3B4C5D`
  - BitChat protocol codec (`src/lib/bluetooth/protocol.ts`) — encodes NeighbourGood crisis data as JSON inside standard BitChat broadcast messages so native nodes relay them without modification; supports `emergency_ticket`, `ticket_comment`, `crisis_vote`, `crisis_status`, `direct_message`, and `heartbeat` message types
  - Mesh Svelte store (`src/lib/stores/mesh.ts`) — reactive stores for connection state, peer tracking, and per-community message deduplication (sliding window of last 500 IDs)
  - `POST /mesh/sync` backend endpoint — idempotent batch sync of mesh-received messages to the server; creates emergency tickets and records crisis votes; skips duplicates by mesh message UUID
  - `MeshSyncedMessage` SQLAlchemy model for deduplication tracking
  - 10 new backend tests: auth, empty sync, ticket creation, deduplication, crisis vote, non-member rejection, invalid type validation, heartbeat acknowledgement, missing-title error, batch sync
- **Triage dashboard mesh panel** (Red Sky mode only, Chrome/Edge)
  - "Connect to Mesh" button — triggers Chrome device picker for nearby BitChat nodes
  - Status indicator: pulsing dot (scanning), green (connected), grey (offline)
  - Live peer count from heartbeat messages
  - Mesh-received tickets rendered with amber "via mesh" badges
  - Ticket form switches to "Broadcast via Mesh" when offline + mesh connected
  - One-click sync button appears when internet returns and unsent mesh messages exist
- **Mesh-aware offline queue** — `QueuedRequest` now tracks `meshSent` flag; mesh-broadcast tickets also enqueued for server sync when internet returns
- **i18n strings** for mesh UI in all 10 supported locales (en, ar, de, el, es, fr, id, nl, sw, uk)

### Changed

- Backend version bumped to 1.2.0
- Frontend version bumped to 1.2.0
- `frontend/src/lib/types.ts` — added `NGMeshMessage`, `MeshTicketData`, `MeshVoteData`, `MeshSyncResult` interfaces
- Phase 6 roadmap item "Mesh networking preparation (bitchat API integration)" marked complete
- Total test count: 260 (up from 250)

## [1.1.0] - 2026-03-01

### Added

- **Offline item browsing and request queuing** – Full Phase 5 offline-first capabilities
  - Browse resources and skills without internet connectivity
  - Queue booking requests while offline, auto-sync when connection restored
  - Service worker background sync for seamless reconnection experience
  - Offline-aware UI indicators showing sync status
- **Multi-language support (i18n)** – Comprehensive internationalization foundation
  - 7 languages supported: English, French, German, Spanish, Italian, Portuguese, Dutch
  - Right-to-left (RTL) text direction support for future language expansion
  - Language selection interface in user settings
  - Automatic language detection based on browser preferences
  - All UI text translatable with centralized message catalogs
- **Data export and backup tools** – User privacy and data portability
  - Export personal profile data as JSON
  - One-click community data backup
  - Import functionality for instance migration
- **Image upload reliability improvements** – Fixed SSR hydration issues
  - Resolved auth token sync from localStorage after server-side rendering
  - Disabled SvelteKit CSRF origin validation for direct API requests
  - Improved upload success rates on first-time users

### Changed

- Backend version bumped to 1.1.0
- Frontend version bumped to 1.1.0
- Phase 5 (Offline & Resilience) now fully complete
- Phase 6 (Advanced Features) multi-language support complete

### Fixed

- Image upload failing due to token not syncing after SSR hydration
- CSRF origin check blocking legitimate image uploads
- Language preference persistence across sessions

## [1.0.0] - 2026-02-27

### Added

- **Reputation system rebalancing** (#50) – Fine-tuned scoring weights and tier thresholds for more meaningful progression
  - Updated point allocations for different community contributions
  - Adjusted tier breakpoints to better reflect user engagement levels
  - Improved visibility of reputation impact on platform credibility
- **3-step onboarding wizard** (#49) – Enhanced initial setup with skills and items discovery
  - Step 1: Community selection and creation
  - Step 2: Resources (items) offering discovery
  - Step 3: Skills offering and requesting
  - Improved user engagement during first-time setup
- **Community activity timeline** (#43) – Overview tab now displays chronological community history
  - Activity events for resources, bookings, skills, and crisis mode changes
  - Better community context and member discovery through activity
- **Telegram integration documentation** (#48) – Comprehensive setup guide and bot command reference
  - Step-by-step webhook configuration instructions
  - Bot command examples and event mapping
- **Skill context in messaging** (#44) – Messages linked to skills so both parties understand conversation context
  - Messages reference the skill offer/request that triggered the conversation
  - Both sides have context about what skill is being discussed
- **Full production release** – v1.0.0 marks the stable release of the NeighbourGood platform
  - All core features implemented and tested
  - Security Phase 4a hardening complete
  - PWA support with offline capability
  - Telegram bot integration ready for production
  - 198+ backend tests covering all domains

### Changed

- Backend version bumped to 1.0.0
- Frontend version bumped to 1.0.0
- Onboarding flow now 3-step wizard instead of single-page search
- Reputation scoring model updated for clearer tier progression

### Fixed

- Communities page full-width layout (#41) – Removed artificial width constraints
- Consistent page widths across all sections
- Improved mobile responsiveness

## [0.9.9] - 2026-02-26

### Added

- **Progressive Web App (PWA) support** – Full offline-first capability with service worker caching
  - Service worker precaches all SvelteKit build chunks and static files on install
  - Cache-first strategy for hashed build assets (zero network for repeat visits)
  - Network-first with stale cache fallback for API GET requests
  - Branded offline fallback page with retry button (dark-mode aware)
  - Automatic service worker updates with in-app notification banner
- **PWA installation and manifest** – Full web app manifest with icons and shortcuts
  - Installable on Android, desktop Chrome, and iOS (via web.app)
  - SVG + 192/512px PNG icons with automated generation
  - Shortcuts for quick access to Messages, Resources, and Communities
  - Correct theme colors matching current warm palette (#c95d1b)
  - No new npm dependencies required
- **Dashboard crisis ticket widget** – Quick access to assigned emergency tickets (Red Sky only)
  - New "Your assigned tickets" section shows tickets assigned to current user
  - Only visible when user has open assigned tickets in crisis communities
  - Each ticket links directly to ticket detail/discussion page for quick action
- **Design refinements and fixes** – Improved visual consistency across all pages
  - Standardized heading sizes and font weights on triage pages
  - Removed width alignment inconsistencies in detail pages
  - Better visual hierarchy across emergency and resource sections
- **Enhanced reputation system UI** – Improved visibility and browsing of resource/skill lists
  - Better display of reputation levels and user stats on profile
  - Improved resource and skill card designs for better scannability
  - Enhanced filtering and sorting on resource/skill browsing pages

### Fixed

- **Design width inconsistencies** – Fixed double-centering in community pages, triage, and emergency sections
- **Heading standardization** – Consistent font sizes and weights across all triage pages
- **Orphan page padding** – Removed duplicate padding in triage detail page

### Changed

- Backend version bumped to 0.9.9
- Frontend now PWA-enabled with full offline support
- Dashboard UI enhanced with crisis-mode awareness

## [0.9.8] - 2026-02-25

### Added

- **User dashboard** – Personalized dashboard showing user stats, recent activity, and quick actions
  - Profile summary with reputation score and member status
  - Recent bookings, messages, and activity feed
  - Quick access to create resources, post skills, and manage communities
- **Ticket detail page** – Comprehensive view for emergency tickets in Red Sky mode
  - Discussion thread for ticket comments and updates
  - Assignment controls for leaders and admins to assign tickets to members
  - Real-time updates and status tracking
- **Global Red Sky mode awareness** – Users now see Red Sky mode activated if they are members of any crisis community
  - Platform-wide UI indicator showing active crisis status
  - Quick access to crisis-mode communities from dashboard
- **UI redesign and branding refresh** – Complete visual refresh with improved usability
  - Warm colour palette for better visual hierarchy
  - Abril Fatface typography for headings (custom branding)
  - SVG logo replacing bitmap version (better scalability)
  - Active navigation state indicators for clarity
  - Consistent widths across all pages (improved alignment)
- **Navigation restructuring** – Improved user flows and information architecture
  - Better labeling for Blue Sky vs Red Sky features
  - More intuitive routing between emergency and resource sections
  - Improved mobile navigation usability
- **Hero background improvements** – Landing page visual enhancements
  - Better responsive image handling
  - Improved contrast and accessibility
- **Communities map fixes** – Improved location-based community discovery
  - Better marker placement and clustering
  - Fixed zoom level and centering logic

### Fixed

- **Emergency API improvements** – Better error handling and validation
  - Consistent response format across emergency endpoints
  - Improved field validation for ticket creation
- **Consistent page widths** – Resolved layout shifting issues
  - All pages now maintain consistent max-width and padding
  - Improved visual stability on different screen sizes

### Changed

- Backend version bumped to 0.9.8
- Frontend navigation restructured for clarity between normal and crisis operations
- Dashboard now serves as primary user landing page after login

## [0.9.5] - 2026-02-24

### Added

- **Low-bandwidth mode** – Text-only, image-free UI for reduced data usage
  - Hidden by default in Blue Sky; auto-enabled in Red Sky mode
  - Triage dashboard for managing emergency tickets (Red Sky only)
  - Inventory tracking system for essential resource quantities
- **CLAUDE.md codebase guide** – Comprehensive reference for AI assistants
  - Model usage policy and token efficiency guidelines
  - Project overview, tech stack, and repository structure
  - Development workflows, testing patterns, and common task recipes
  - Security state tracking with pending items and implementation status
- **Community-filtered resources and skills** – Search/filter now respects joined communities
  - API endpoints filter results to only show resources/skills from communities the user has joined
  - Prevents information leakage of resources in other communities
- **Eager-loading for community relationships** – N+1 query fix
  - Communities serialize with members, resources, and skills without extra round-trips
  - Improved API response time and database efficiency
- **Enhanced API error handling** – Better Pydantic validation error messages
  - Detailed field-level error information for easier client-side debugging
  - Consistent error response format across all endpoints

### Fixed

- **Community 500 error** – Fixed serialization issues when accessing community endpoints
- **Community-scoped resource/skill filtering** – Correct community membership checks on queries
- **Other bug fixes** – Stability improvements across multiple endpoints

### Changed

- Backend version bumped to 0.9.5
- **Red Sky Mode improvements** – Low-bandwidth mode now defaults to on when crisis mode is active
- Low-bandwidth and triage features are production-ready and integrated into crisis workflow

## [0.9.0] - 2026-02-19

### Added

- **Per-community crisis mode** – Communities can switch between Blue Sky (normal) and Red Sky (crisis) modes
- **Admin crisis toggle** – Community admins can force-toggle crisis mode via `POST /communities/{id}/crisis/toggle`
- **Community vote mechanism** – Members can vote to activate/deactivate crisis mode; auto-switches at 60% threshold
- **Crisis mode status** – `GET /communities/{id}/crisis/status` shows current mode, vote counts, and threshold
- **Emergency ticketing system** – Create request, offer, and emergency ping tickets within communities
  - Emergency pings restricted to Red Sky mode only
  - Ticket CRUD with type/status/urgency filters
  - Authors, leaders, and admins can update tickets
- **Neighbourhood leader roles** – Admins can promote members to "leader" role, leaders can manage tickets
  - `POST /communities/{id}/leaders/{user_id}` to promote
  - `DELETE /communities/{id}/leaders/{user_id}` to demote
  - `GET /communities/{id}/leaders` to list leaders
- **Explore page (landing for guests)** – Map-based community discovery using Leaflet/OpenStreetMap
  - Browser geolocation to center map on user's position
  - Community markers with member count badges
  - Community list cards with crisis mode indicators
  - Register CTA for unregistered users
- **Public map endpoint** – `GET /communities/map` returns lightweight community data (no auth required)
- **Community coordinates** – Optional latitude/longitude fields on communities for map placement
- **Guest-friendly navigation** – Logged-out users see "Explore" instead of Resources/Skills
- **Crisis mode UI** – Community detail page shows crisis status, vote buttons, emergency tickets, and leader management
- **198 tests** – Added 32 tests for crisis toggle, voting, tickets, leaders, and map endpoint

### Changed

- Community model extended with `mode` (blue/red), `latitude`, and `longitude` fields
- CommunityMember role now supports "member", "leader", and "admin"
- CommunityOut schema includes `mode`, `latitude`, `longitude` fields
- Navigation hides Resources/Skills for logged-out users, shows Explore link instead
- Activity event types expanded: `crisis_mode_changed`, `ticket_created`, `leader_promoted`, `leader_demoted`
- Backend version bumped to 0.9.0

## [0.8.0] - 2026-02-19

### Added

- **Mobile navigation** – Hamburger menu with slide-down nav for screens ≤768px, overlay backdrop, animated open/close
- **Community-scoped messaging** – Messages restricted to users who share at least one community (403 if no shared community)
- **New Message button** – Contact picker modal on messages page; lists community members with search filter
- **Messageable contacts endpoint** – `GET /messages/contacts` returns all users sharing a community with the current user
- **Security Phase 1 (4a)** – First security hardening pass:
  - Password strength validation (min 8 chars, uppercase + lowercase + digit required)
  - Email format validation via `EmailStr` on register and login
  - Security response headers (X-Content-Type-Options, X-Frame-Options, Referrer-Policy, Permissions-Policy, HSTS, CSP)
  - Secret key validation (rejects default key in production, requires 32+ chars)
  - File upload hardening (magic byte validation, extension sanitisation, allowed-list enforcement)
  - Input length limits on all user-facing schemas (titles, descriptions, messages, names)
- **Security roadmap** – Three security phases mapped to main phases 4 and 5 in README
- **166 tests** – Added 3 tests for community-scoped messaging and messageable contacts

### Changed

- Navigation header is fully responsive with hamburger menu on mobile
- Messages page header uses flexbox layout with "New Message" action button
- `pydantic[email]` added to backend requirements for `EmailStr` support
- Backend version bumped to 0.8.0

## [0.7.0] - 2026-02-18

### Added

- **Skill exchange listings** – Offer or request skills with 10 categories (tutoring, repairs, cooking, languages, music, gardening, tech, crafts, fitness, other)
- **Full skills CRUD** – `/skills` endpoints with search, category/type filters, and community scoping
- **Skills frontend page** – Browse, search, filter, and create skill listings with offer/request badges
- **Reputation/trust score system** – Computed score from sharing activity: resources shared (5pts), lending completed (10pts), borrowing completed (3pts), skills offered (5pts), skills requested (2pts)
- **5 reputation levels** – Newcomer → Neighbour → Helper → Trusted → Pillar
- **Reputation endpoints** – `GET /users/me/reputation` (auth), `GET /users/{id}/reputation` (public)
- **Community activity feed** – Auto-generated timeline from resource sharing, bookings, skills, and member joins
- **Activity endpoints** – `GET /activity` (public, filter by community), `GET /activity/my` (auth)
- **Invite system** – Generate URL-safe invite codes for communities with optional max_uses and expiry
- **Invite CRUD** – Create, list, redeem, and revoke invite codes
- **Rating and review system** – 1-5 star reviews on completed bookings for both borrower and lender
- **Review summary** – Average rating and total review count per user
- **163 tests** – Added 70 tests for skills, reputation, activity, invites, and reviews

### Changed

- Skills nav link added to main navigation (visible to all users)
- Activity events auto-recorded when resources are shared, bookings created/completed, skills posted, and members join communities
- Homepage: 6-box feature grid, GitHub social preview image, bright mode default
- Backend version bumped to 0.7.0

## [0.6.0] - 2026-02-18

### Added

- **Instance identity** – Configurable instance metadata (name, region, admin contact) for federation readiness
- **`/instance/info` endpoint** – Public metadata endpoint for federation directory crawling
- **Community-scoped resources** – Resources can belong to a community via `community_id` (nullable for personal items)
- **Community resource filter** – `GET /resources?community_id=` filters resources by community
- **Community resources view** – Community detail page shows resources shared within that community
- **Community selector on create** – Resource creation form lets users assign resources to their communities
- **PostgreSQL production default** – Docker Compose now runs PostgreSQL 16; SQLite remains for local dev
- **101 tests** – Added 8 tests for instance info, community-scoped resource CRUD and filtering

### Changed

- Docker Compose uses PostgreSQL with dedicated `pg-data` volume instead of SQLite
- `.env.example` expanded with instance identity and admin contact fields
- `psycopg2-binary` added to backend requirements
- Alembic `env.py` now imports all models for complete migration generation

## [0.5.0] - 2026-02-18

### Added

- **Community system** – PLZ-based neighbourhood groups with custom names
- **Community CRUD** – Create, search, join, leave, update communities
- **Community merge** – Merge smaller communities into larger ones (admin only)
- **Merge suggestions** – Auto-suggest merge candidates by same postal code or city
- **Onboarding flow** – Post-registration search for community by city/name/PLZ, join or create
- **Community frontend** – My Communities list, community detail with members, merge UI for admins
- **Alembic migration** – Communities and community_members tables
- **93 tests** – Added 24 tests for community CRUD, membership, merge, suggestions, and search

### Changed

- **Shared frontend types** – Centralized TypeScript interfaces in `$lib/types.ts`, replacing duplicated local definitions
- **CSS utility classes** – Global alert, tag, badge, empty-state, and loading classes in `app.css`
- **Hardcoded colors removed** – All frontend pages now use CSS variables for dark mode compatibility
- **N+1 query fix** – Bulk-fetch conversation partners in messages endpoint
- **FK indexes** – Added `index=True` to all foreign key columns across models for query performance
- **Configurable frontend URL** – Notification emails use `frontend_url` setting instead of hardcoded localhost
- **Removed redundant schema** – Eliminated `CommunitySearch` (duplicate of `CommunityList`)
- Registration now redirects to `/onboarding` instead of `/resources`

## [0.4.0] - 2026-02-17

### Added

- **In-app messaging** – Direct messages between users with conversation threads
- **Conversation list** – Overview of all conversations with last message preview and unread badges
- **Unread tracking** – Per-message and per-conversation read status, unread count endpoint
- **Booking-linked messages** – Attach messages to specific booking requests for context
- **Mark as read** – Mark individual messages or entire conversations as read
- **Email notifications** – SMTP-based notifications for new messages, booking requests, and status changes
- **Graceful fallback** – Logs notifications to console when SMTP is not configured
- **Messages frontend** – Conversation list with chat-style message thread and compose input
- **Nav update** – Messages link in navigation bar for logged-in users
- **Alembic migration** – Messages table with sender/recipient/booking foreign keys
- **69 tests** – Added 18 tests for messaging, conversations, read status, and notification service

## [0.3.0] - 2026-02-17

### Added

- **Calendar-based booking system** – Request to borrow resources with date ranges, conflict detection
- **Booking status workflow** – Pending → Approved/Rejected (owner), Cancelled (borrower), Completed
- **Resource search** – Full-text search across titles and descriptions (case-insensitive)
- **Image upload** – Upload images for resources with type/size validation (JPEG, PNG, WebP, GIF)
- **Category metadata** – Categories endpoint with labels and icon names
- **Availability filter** – Filter resources by availability status
- **Bookings management page** – Frontend page with role/status filters, approve/reject/cancel/complete actions
- **Resource calendar view** – API endpoint for month-based booking calendar per resource
- **Booking form** – Request-to-borrow form on resource detail page with date range and message
- **Alembic migration** – Bookings table and image_path column for resources
- **51 tests** – Added 34 tests for search, image upload, categories, bookings CRUD, status transitions, calendar

## [0.2.0] - 2026-02-17

### Added

- **User authentication** – Register and login with email/password, JWT-based sessions
- **User profiles** – View and update display name, neighbourhood assignment
- **Resource CRUD** – Create, read, update, and delete shared resources
- **Resource categories** – tool, vehicle, electronics, furniture, food, clothing, skill, other
- **Category filtering** – Filter resource listings by category
- **Resource detail page** – View full resource info with owner details
- **Owner actions** – Toggle availability, delete own resources
- **Frontend auth flow** – Registration, login, and logout with persistent JWT storage
- **Frontend resource pages** – Resource listing with create form, detail view with owner controls
- **Navigation bar** – Global nav with auth-aware links
- **API client** – Reusable fetch wrapper with auth header injection
- **Alembic migrations** – Database schema versioning for users and resources tables
- **Test suite** – 17 tests covering status, auth, users, and resource endpoints

## [0.1.0] - 2026-02-17

### Added

- Initial project scaffold with FastAPI backend and SvelteKit frontend
- `/status` health-check endpoint with dual-mode indicator (blue/red)
- Blue Sky / Red Sky CSS theme system using CSS custom properties
- SQLAlchemy database setup with SQLite default and PostgreSQL option
- Pydantic-settings configuration with `NG_` prefixed environment variables
- Docker Compose single-command deployment
- PWA manifest for offline-first preparation
- README with project vision, architecture documentation, and 6-phase roadmap
