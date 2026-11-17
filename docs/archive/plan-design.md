# Design & Layout Redesign Plan

> **Archived plan.** Kept for history; parts of it are outdated. Current status and open work: [docs/roadmap.md](../roadmap.md).

**Goal:** Improve the overall visual identity of NeighbourGood — original logo, better typography, consistent layout, fully responsive.

---

## Summary of Changes

### 1. Typography — `frontend/src/app.html` + `frontend/src/app.css`

- **Add Google Fonts**: `Plus Jakarta Sans` (friendly, rounded, professional — for headings) loaded alongside `Inter` (body text)
- Add `--font-heading` and `--font-body` CSS custom properties
- Apply `--font-heading` globally to `h1`–`h4` and branding elements
- Tighten heading letter-spacing and line-height for a polished look

### 2. New SVG Logo — `frontend/src/routes/+layout.svelte`

Replace the plain "N" letter box with a purpose-built inline SVG icon:
- Two overlapping/connected house outlines (neighbourhood concept)
- Small shared circle/heart connecting them (goodness/sharing concept)
- Uses `currentColor` / CSS variables so it works in light, dark, and Red Sky modes
- "NeighbourGood" wordmark rendered in `--font-heading` with two-tone treatment: "Neighbour" in normal weight, "Good" in bold accent color

### 3. Design Token Refinements — `frontend/src/app.css`

- Slightly warm the primary color from `#4f46e5` → `#5965f5` (more approachable, less harsh)
- Add `--color-brand-gradient`: used on the logo bg and hero section
- Improve card hover: add `transform: translateY(-2px)` and a more prominent shadow
- Standardize `--radius-card`, `--radius-input`, `--radius-button` as named tokens
- Add two shared layout utility classes:
  - `.page-header` — flex row with `h1` on the left and action button(s) on the right, with bottom border separator
  - `.page-section` — consistent section spacing/grouping within a page
- Add `.card-grid` and `.card` canonical classes so every listing page uses the same grid + card style

### 4. Navigation Polish — `frontend/src/routes/+layout.svelte`

- Active link indicator: colored bottom border + slightly bolder weight on the currently active route
- Tighten nav item spacing; replace text-only logout with an icon-text combo
- Mobile menu: add a slide-in transition (currently no animation on open/close)
- Nav bar: increase height slightly from current to give more breathing room
- Separate "primary" nav links (Dashboard, Resources, Skills) from "secondary" (Communities, Bookings, Messages) with a subtle divider on desktop

### 5. Home Page Polish — `frontend/src/routes/+page.svelte`

- Use `--font-heading` for the hero headline
- Add a subtle SVG background pattern (dots/grid, very low opacity) behind the hero
- Improve feature card icons: replace emoji with inline SVG icons (consistent sizing/style)
- Add a fourth row of value-prop text ("Trusted by communities around the world") between features and footer

### 6. Consistent Page Headers — All Route Pages

Apply the new `.page-header` class to all page top sections. Files to update:

- `frontend/src/routes/resources/+page.svelte`
- `frontend/src/routes/communities/+page.svelte`
- `frontend/src/routes/skills/+page.svelte`
- `frontend/src/routes/bookings/+page.svelte`
- `frontend/src/routes/messages/+page.svelte`
- `frontend/src/routes/dashboard/+page.svelte`

Each page currently defines its own heading style inline — unify these to the shared `.page-header` pattern.

### 7. Responsive Audit — All Route Pages

- Verify each page's card grid collapses correctly at 480px and 360px
- Fix any `min-width` on inputs that causes horizontal overflow on small screens
- Ensure the nav logo + wordmark don't overflow at narrow widths (add `overflow: hidden; text-overflow: ellipsis` where needed)
- Standardize the single-column breakpoint to `640px` across all pages (currently some use 600px, some 640px)
- Check bookings and messages pages for table/list overflow on mobile

---

## File Change List

| File | Change |
|------|--------|
| `frontend/src/app.html` | Add Google Fonts `<link>` for Plus Jakarta Sans |
| `frontend/src/app.css` | Font variables, refined tokens, `.page-header`, `.card`, `.card-grid`, responsive fixes |
| `frontend/src/routes/+layout.svelte` | New SVG logo, nav active state, mobile slide-in, two-tone wordmark |
| `frontend/src/routes/+page.svelte` | Hero font, SVG icons in feature cards, subtle background pattern |
| `frontend/src/routes/resources/+page.svelte` | `.page-header` adoption, responsive audit |
| `frontend/src/routes/communities/+page.svelte` | `.page-header` adoption, responsive audit |
| `frontend/src/routes/skills/+page.svelte` | `.page-header` adoption, responsive audit |
| `frontend/src/routes/bookings/+page.svelte` | `.page-header` adoption, responsive audit |
| `frontend/src/routes/messages/+page.svelte` | `.page-header` adoption, responsive audit |
| `frontend/src/routes/dashboard/+page.svelte` | `.page-header` adoption, responsive audit |

---

## Out of Scope

- No backend changes
- No new pages
- No changes to auth/register/login pages (they are already minimal and centered)
- No changes to Red Sky crisis-specific styling (keeping that intentionally stark)
- No dependency changes (loading fonts from Google CDN only)
