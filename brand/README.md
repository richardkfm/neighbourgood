# NeighbourGood Brand Kit

The logo, wordmark and colours for NeighbourGood, introduced in v2.5.0 (website v1.3.0).
Use these files instead of redrawing the logo.

```
brand/
├── svg/   vector sources: use these wherever possible
└── png/   rendered with transparent backgrounds
```

## The logo

A house on a rounded violet tile. The door is an arch, which keeps the house
readable down to 16 px. The wordmark is **Neighbour** in the text colour and
**Good** in the brand violet, set in Fraunces (72 pt optical size, Regular). In
these files the wordmark is converted to outlines, so no font is needed.

| File | Use it for |
|---|---|
| `svg/logo.svg` | The default horizontal logo on light backgrounds |
| `svg/logo-dark.svg` | Dark backgrounds (dark mode) |
| `svg/logo-redsky.svg` | Red Sky (crisis) material: light tile with a dark house, on a dark background |
| `svg/logo-black.svg`, `svg/logo-white.svg` | One-colour printing, stamps, engraving |
| `svg/mark.svg` (+ `-dark`, `-redsky`, `-black`, `-white`) | Square spaces: avatars, app icons, stickers |
| `svg/wordmark.svg` (+ variants) | Where the mark already appears nearby |
| `svg/glyph-house-black.svg`, `svg/glyph-house-white.svg` | The house alone, for very small or embossed uses |
| `svg/app-icon-maskable.svg` | Full-bleed square for Android and iOS home-screen icons |

PNG files follow the same names. Marks come in 16–1024 px (`mark-<size>.png`).
Logos and wordmarks are named by height (`logo-256h.png` is 256 px tall).

### Clear space and minimum size

- Keep clear space around the logo of at least **half the tile's width** on every side.
- Smallest size for the horizontal logo: **24 px tall** on screen, **8 mm** in print.
- The mark alone works down to **16 px** (favicon).

### Don'ts

- Don't recolour the tile with anything other than the colours below, and never in orange.
- Don't put the wordmark in another typeface, or squeeze, stretch or outline it.
- Don't put the light logo on a busy photo. Use the white or black version on a solid area.
- Don't add shadows, gradients or the old heart/dot inside the door.

## Colours

| Name | Light | Dark | Used for |
|---|---|---|---|
| Brand violet | `#4f46e5` | `#818cf8` | Logo tile, primary buttons, links, Blue Sky mode |
| On violet | `#ffffff` | `#0f0f1a` | The house on the tile, text on buttons |
| Ink | `#2d1b0e` | `#e8e8ed` | "Neighbour" and body text |
| Cream | `#fdf8f3` | `#0f0f1a` | Page background |
| Warm brown | `#7a5c47` | `#c9b8a6` | Small labels and kickers, mesh hub nodes |
| Warning | `#6b4a33` on `#f3e7da` | `#d4bc9f` on `#2e241b` | Pending bookings, offline notices, "high" urgency, warning alerts |
| Rating | `#4f46e5` | `#818cf8` | Star ratings (same as the link violet) |
| Red Sky red | `#dc2626` | `#dc2626` | Primary actions in crisis mode (the only colour in Red Sky) |
| Red Sky surfaces | `#170f0f` / `#231818` | same | Background and cards in crisis mode; the logo tile there is `#f7eeee` with a `#170f0f` house |

The app reads these from CSS custom properties in `frontend/src/app.css`
(`--color-primary`, `--color-logo`, `--color-accent`, …). In Red Sky mode
the nav logo switches to the light tile automatically, because it uses `--color-logo`.

## Typefaces

| Role | Typeface | Source |
|---|---|---|
| Wordmark and headings | Fraunces | Google Fonts, SIL Open Font License |
| Interface and body | Inter | Google Fonts, SIL Open Font License |
| Code and labels | JetBrains Mono | Google Fonts, SIL Open Font License |

## App icons in this repository

`frontend/static/` holds copies used by the PWA: `icon.svg`, `favicon.png` (32),
`icon-192.png`, `icon-512.png`, `icon-512-maskable.png` and
`apple-touch-icon.png` (180, full-bleed). If the logo changes, update them from
this folder.
