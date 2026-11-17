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
