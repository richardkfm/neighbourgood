# Translation status

`en.json` is the source. Every locale has exactly the same keys; `npm run check:i18n` fails the build check when a key is missing or a `$t()` key does not exist.

## AI-translated in v2.4.0 — native review wanted

In v2.4.0 all locales other than English were completed by AI translation (about 4,800 strings, plus fixes to existing ones). Every message parses as ICU, placeholders match the English source, and plurals use each language's CLDR categories, but **no native speaker has reviewed them yet**. Corrections are very welcome — edit the locale JSON and open a PR.

| Locale | Form of address | Review first |
|--------|-----------------|--------------|
| `ar` | neutral imperatives | Ticket term (تذكرة), ping wording, `onboarding.done_summary` |
| `de` | du | "Gemeinschaft" for community, "Leitung" for the leader role, "Roter-Himmel-Modus" |
| `el` | εσύ | Συντονιστής for leader, κόμβος for instance |
| `es` | tú | "líder", "Cielo Azul / Cielo Rojo", crisis texts |
| `fa` | شما | رهبر for leader (political ring; هماهنگ‌کننده may be better), جامعه for community |
| `fr` | vous | "Responsable" for leader, crisis texts, missing `many` plural form |
| `id` | Anda | crisis texts |
| `nl` | je/jij | "Coördinator", "item" for resource ("spullen"?), "Rode lucht" |
| `su` | anjeun | Whole file — lowest confidence; especially `trust.*` badge names and `review.*` |
| `sw` | wewe | "Anga Jekundu" agreement, `mesh.offline_triage` |
| `uk` | Ви | заявка for ticket, `onboarding.done_summary` |

Terms kept in Latin script everywhere: NeighbourGood, Telegram, Bluetooth, BitChat, Mesh, webhook event names (`booking.created` …) and URLs.
