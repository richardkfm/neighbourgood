# Internationalisation (i18n) Plan — NeighbourGood

> **Archived plan.** Kept for history; parts of it are outdated. Current status and open work: [docs/roadmap.md](../roadmap.md).

> **Strategic context:** NeighbourGood is a crisis-capable community platform. The communities
> that need it most are often those where people speak languages other than English — disaster-
> prone archipelagos, refugee-host cities, conflict-affected regions, and the Global South.
> This plan ensures the platform speaks people's languages before the crisis hits.

---

## Why This Matters

| Region / Context | Language gap today |
|---|---|
| MENA crisis zones (Syria, Yemen, Sudan) + diaspora | Arabic entirely absent |
| Sub-Saharan Africa (200M Swahili speakers, 100M Hausa) | All absent |
| Francophone Africa (29 countries) + Haiti | French absent |
| Latin America / Caribbean | Spanish absent |
| Southeast Asia (Indonesia = world's most disaster-prone country) | Indonesian absent |
| South Asia (Bangladesh floods, Pakistan floods) | Bengali, Urdu absent |
| Active displacement (Ukraine, Afghanistan) | Ukrainian, Dari/Pashto absent |
| Refugee host cities (Türkiye, Jordan, Germany) | Turkish absent |

All of these communities face the same barrier: an English-only interface.

---

## Design Principles

1. **Locale follows the user, not the community.** Each user chooses their own language.
   A Syrian refugee and a German host in the same community each see their own language.
2. **RTL is a first-class citizen.** Arabic, Urdu, Hebrew, Farsi layout must be correct from
   day one — not patched in later.
3. **Works offline.** Translation bundles are part of the PWA cache (the app already has a
   service worker). No extra round-trips.
4. **Graceful degradation.** If a string is missing in the active locale, fall back to English,
   never show a raw translation key.
5. **Low-bandwidth friendly.** Locale files are split per language (lazy-loaded where possible)
   so users only download what they need.
6. **Community can signal its primary language.** This surfaces on the Explore map and in
   the join flow so people find the right community.

---

## Priority Language Tiers

### Tier 1 — Phase 1 (this branch)

| Code | Language | Speakers | Key communities |
|------|----------|----------|-----------------|
| `en` | English | 1.5 B | Baseline |
| `ar` | Arabic | 420 M | MENA, Levant refugees, Sahel |
| `fr` | French | 320 M | West/Central/North Africa, Haiti, Maghreb |
| `es` | Spanish | 560 M | Latin America, Caribbean, Central America |
| `sw` | Swahili | 200 M | East Africa (Kenya, Tanzania, DRC, Uganda) |
| `id` | Indonesian | 270 M | Disaster-prone archipelago (earthquakes, tsunamis, floods) |
| `uk` | Ukrainian | 45 M | Active displacement (2022–present) |

### Tier 2 — Phase 2 (next sprint)

| Code | Language | Why critical |
|------|----------|--------------|
| `hi` | Hindi | India disasters, 600 M speakers |
| `bn` | Bengali | Bangladesh floods, 250 M speakers |
| `tr` | Turkish | World's largest refugee host country |
| `tl` | Tagalog/Filipino | Philippines typhoon corridor |
| `pt` | Portuguese | Brazil, Mozambique, Angola, 260 M speakers |
| `ha` | Hausa | Nigeria/Niger/Chad, 100 M speakers |
| `am` | Amharic | Ethiopia/Horn of Africa, 60 M speakers |
| `ne` | Nepali | Nepal earthquake country |
| `ur` | Urdu (RTL) | Pakistan floods, Afghan diaspora |
| `fa` | Farsi/Dari (RTL) | Afghan diaspora, Iran |

### Tier 3 — Phase 3 (future)

- Tigrinya (Eritrea/Ethiopia), Somali, Pashto, Rohingya (Hanifi script), Burmese,
  Haitian Creole, Kinyarwanda, Lingala, Wolof, Azerbaijani, Georgian

---

## Architecture

### Frontend

```
frontend/src/lib/i18n/
├── index.ts                  ← init: load locale from user profile → localStorage → browser
└── locales/
    ├── en.json               ← English (canonical, all keys must exist here)
    ├── ar.json               ← Arabic (RTL)
    ├── fr.json               ← French
    ├── es.json               ← Spanish
    ├── sw.json               ← Swahili
    ├── id.json               ← Indonesian
    └── uk.json               ← Ukrainian
```

**Library:** `svelte-i18n`
- Standard for SvelteKit; supports ICU message format (plurals, gender, interpolation)
- Named interpolation: `{name}`, `{count, plural, one {# item} other {# items}}`
- Locale is a Svelte store — reactive, no page reload required

**Locale resolution order:**
1. User profile `language_code` (authenticated users)
2. `localStorage` key `ng_locale`
3. Browser `navigator.language` (automatic on first visit)
4. Fall back to `'en'`

**RTL support:**
- `<html dir="rtl">` set reactively when locale is Arabic, Urdu, Hebrew, Farsi
- CSS logical properties (`margin-inline-start`, `padding-inline-end`) used in new styles
- `[dir='rtl']` overrides in `app.css` for nav, flex direction, text alignment
- RTL locales list: `['ar', 'ur', 'he', 'fa']`

### Backend

**User model** — new field:
```python
language_code: Mapped[str] = mapped_column(String(10), default="en", nullable=False)
```

**Community model** — new field:
```python
primary_language: Mapped[str | None] = mapped_column(String(10), nullable=True)
```

**Schemas updated:**
- `UserRegister` + `UserProfileUpdate`: optional `language_code` field (BCP 47, max 10)
- `UserProfile` (response): includes `language_code`
- `CommunityCreate`: optional `primary_language`
- `CommunityOut` + `CommunityMapItem`: includes `primary_language`

**Alembic migration:** `add_language_code_to_users_and_communities`

**Backend error messages:** Backend continues to return English error strings. The frontend
owns locale. A future phase will add structured error codes so the frontend can translate
API errors too.

---

## Translation Key Structure (`en.json`)

```
nav.*         navigation links, aria labels, install prompt
auth.*        login, register, logout forms
common.*      shared UI words (save, cancel, loading, error, etc.)
home.*        dashboard page
resources.*   resource library
bookings.*    booking flow
messages.*    messaging
communities.* community pages
crisis.*      Red Sky / emergency UI
skills.*      skill exchange
settings.*    settings page (includes language picker)
explore.*     public map page
```

---

## Language Selector UX

- Globe icon button in the nav bar (desktop: right of theme toggle; mobile: in menu)
- Dropdown lists languages in their own script: "العربية", "Français", "Español", etc.
- Selection persists to `localStorage` and (if logged in) syncs to user profile via PATCH `/users/me`
- Changing language applies instantly (no reload) — Svelte reactive stores

---

## Phase Roadmap

### Phase 1 — Foundation (this branch) ✅
- [x] `language_code` on User model + Alembic migration
- [x] `primary_language` on Community model + migration
- [x] Updated schemas
- [x] svelte-i18n installed and initialized
- [x] Locale store with 4-step resolution order
- [x] `en`, `ar`, `fr`, `es`, `sw`, `id`, `uk` locale files
- [x] RTL CSS foundation
- [x] `+layout.svelte` using `$t()` — nav, banners, aria labels
- [x] Language selector in nav
- [x] `language_code` in `UserProfile` interface
- [x] `primary_language` in `CommunityOut` interface

### Phase 2 — Full Page Coverage (next sprint)
- [ ] Translate all route pages (login, register, resources, bookings, messages, communities, triage, settings, explore)
- [ ] Tier 2 language bundles (hi, bn, tr, tl, pt, ha, am, ne, ur, fa)
- [ ] Urdu/Farsi RTL support (additional RTL locales)
- [ ] Structured backend error codes → frontend translation
- [ ] Email notification templates in user's language
- [ ] Community creation: language displayed on Explore map

### Phase 3 — Polish & Content (future)
- [ ] Community admins can add multi-language descriptions
- [ ] ICU pluralization for dynamic counts
- [ ] Date/time/number formatting per locale (`Intl` API)
- [ ] Translation contributor guide (community-driven translations via Weblate or similar)
- [ ] `gettext`-style scan to catch any hardcoded strings that slipped through
- [ ] Tier 3 language bundles
- [ ] Right-to-left layout audit (complex components: modals, cards, forms)

---

## What We Are NOT Doing (Yet)

- Machine-translating user-generated content (resource titles, community descriptions)
  — privacy and quality concerns; mark with `lang` attribute and let the browser/OS translate
- Translating backend admin-facing logs or error codes for operators
- Adding a full translation management system (Weblate, Lokalise) in Phase 1 — flat JSON files
  are sufficient until community contributors are onboarded

---

## Testing i18n

```bash
# Switch to Arabic via localStorage and verify RTL layout
# In browser DevTools console:
localStorage.setItem('ng_locale', 'ar'); location.reload();

# Switch back to English
localStorage.setItem('ng_locale', 'en'); location.reload();

# Verify language_code is persisted for logged-in users
# POST /auth/register with { ..., "language_code": "sw" }
# GET /users/me → should return language_code: "sw"
```

---

*Added: 2026-02-28 | Branch: claude/plan-i18n-feature-1j271*
