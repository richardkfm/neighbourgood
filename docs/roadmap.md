# Roadmap

Where NeighbourGood stands (v2.8.3, November 2026) and what is still open. The detailed release history is in [CHANGELOG.md](../CHANGELOG.md); older planning documents are kept in [archive/](archive/).

## What's done

| Area | Status |
|------|--------|
| **Sharing** | Resource library with images, categories, search and quantity-based inventory; calendar bookings with request/approve; skill exchange (offers and requests); community events with RSVP |
| **Community** | Communities by postcode with map, onboarding wizard, invites, merge suggestions, activity feed, direct messages between members |
| **Trust** | Reputation points and levels, booking and skill reviews, trust badges, public profiles |
| **Red Sky** | Per-community crisis toggle and 60 % vote, instance-wide Red Sky (`NG_PLATFORM_MODE=red`), emergency tickets (request / offer / ping) with urgency triage, leader roles, low-bandwidth UI, a dedicated Emergency page |
| **Offline** | Installable PWA, offline browsing, queued requests replayed on reconnect, BitChat BLE mesh with signed messages, fragmentation, check-ins and replay protection |
| **Federation** | `/instance/info`, instance directory, pull-based sync of resources and skills, verified cross-instance Red Sky alerts with expiry |
| **Integrations** | Telegram bot (notifications, group alerts, commands, natural-language assistant), smart matching with optional Ollama/OpenAI re-ranking, signed outbound webhooks |
| **Languages** | 12 languages incl. right-to-left Arabic and Farsi, enforced key parity across all locales |
| **Accounts and privacy** | Password reset, session invalidation on password/email change, data export, account deletion with anonymisation |
| **Security** | Password rules, security headers, upload validation, input length limits, rate limiting, per-(email, IP) lockout, CSRF protection, webhook SSRF guard, request body limits |

## Open

### Features

- [ ] Admin dashboard with usage analytics for instance and community admins
- [ ] Signal integration
- [ ] Matrix integration

### Languages

- [ ] Notification emails in each member's own language (they are English-only today)
- [ ] More languages (candidates: Hindi, Bengali, Turkish, Portuguese, Hausa, Amharic, Urdu)
- [ ] A translation workflow for community translators (e.g. Weblate) and a contributor guide
- [ ] Multi-language community descriptions

### Security and operations

- [ ] Audit log for admin and security events (logins, lockouts, crisis toggles, alert broadcasts)
- [ ] Request IDs in responses and logs
- [ ] Tighter CORS (explicit methods and headers instead of `*`)
- [ ] Additional JWT claims (`iat`, `jti`, `iss`)
- [ ] Content Security Policy tuned per route
- [ ] Field-level encryption for sensitive data (email, messages)
- [ ] Automated, encrypted database backups
- [ ] Continuous integration: run the test suites and dependency vulnerability scanning (`pip-audit`, `npm audit`) on every pull request
- [ ] Container image scanning and hardening
- [ ] Network segmentation between backend and database
- [ ] TLS automation guide (Let's Encrypt) and secrets management
- [ ] Incident response runbook for instance admins

Ideas and feedback are welcome as GitHub issues; see [CONTRIBUTING.md](../CONTRIBUTING.md).
