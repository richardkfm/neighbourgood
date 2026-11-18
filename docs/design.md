# Brand and design

The logo is a house on a rounded violet tile; its door is an arch, so it stays readable at favicon size. The wordmark is **Neighbour** in the text colour and **Good** in violet, set in Fraunces. There is no orange or amber anywhere in the palette: warnings use a warm brown, and star ratings use the brand violet.

| Mode | Look |
|---|---|
| Blue Sky, light | Warm cream background, violet (`#4f46e5`) for actions, links and the logo tile, warm brown for small labels |
| Blue Sky, dark | Deep night blue, lighter violet (`#818cf8`) |
| Red Sky | Always dark, warm near-black surfaces, red (`#dc2626`) as the only colour; the logo becomes a light tile with a dark house |

Typefaces: Fraunces for headings and the wordmark, Inter for the interface, JetBrains Mono for labels and code (all SIL Open Font License).

**Brand kit:** [`brand/`](../brand/) holds the logo, mark, wordmark and app icons as SVG and PNG for light, dark, Red Sky, black and white, with a usage and colour guide in [`brand/README.md`](../brand/README.md). All colours in the app come from CSS custom properties in [`frontend/src/app.css`](../frontend/src/app.css). The website's design rules are in [neighbourgood/ng-website `DESIGN.md`](https://github.com/neighbourgood/ng-website/blob/main/DESIGN.md).


## Design rules in the app

- All colours come from CSS custom properties (`--color-primary`, `--color-bg`, `--color-surface`, `--color-text`, `--color-warning`, `--color-rating`, `--color-logo`, …). Never hard-code colours in components.
- No amber or orange anywhere. Warnings use warm brown, star ratings use `--color-rating` (violet; rose-red in Red Sky).
- Red Sky has one hue, red. Urgency is shown with a text label (CRITICAL, HIGH, MEDIUM, LOW, OFFER) plus lightness via the `--urgency-*` tokens, never by colour alone.
- Right-to-left layouts (Arabic, Farsi) must keep working; check with `dir="rtl"`.

## Layout rules (design A, since 2.8.0)

- **Calm by default.** Secondary text is smaller and uses `--color-text-subtle`. Section titles are quiet Fraunces (`.section-title`), never uppercase. A small mono `.kicker` may sit above a page title.
- **One loud button per area.** Only the main action is a filled `.btn-primary`. Everything else is `.btn-secondary`, a quiet text button that darkens on hover (`.btn-outline` if it must stand alone).
- **More info when needed.** Lists use the `ExpandableItem` component: closed it shows an icon, the title, one line of meta and a status; opened (click, Enter or Space) it shows the details and actions in place. Cards go in an `.item-grid` (3 columns on desktop, 2 on tablets, 1 on phones), rows go in a `.list-panel`.
- **Status as text.** Available/unavailable is a dot plus a word (`.status-text`); only exceptions get a tinted pill.
- **Navigation.** On desktop the active page is underlined in violet; on phones the bottom tab bar highlights the active tab.
- **Dashboard.** Community and member count, a time-of-day greeting and *Share something*; then *Needs you* (borrow requests with inline Approve/Reject, your pending requests, unread messages), *Coming up* (next event) and *New nearby* (newest items from neighbours), a one-line summary, and reputation folded into one row.
