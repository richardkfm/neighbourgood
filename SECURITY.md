# Security Policy

## Reporting a Vulnerability

**Do NOT create a public GitHub issue for security vulnerabilities.** Instead, please report security issues privately.

### Reporting Process

1. **Email:** Send details to **security@neighbourgood.eu**
   - Include a clear description of the vulnerability
   - Provide steps to reproduce (if applicable)
   - Include any relevant code snippets or configuration
   - Attach proof-of-concept code only if necessary for clarity

2. **What to expect:**
   - We will acknowledge receipt within 48 hours
   - We will investigate and provide an initial assessment within 5 business days
   - We will work with you on a fix and responsible disclosure timeline
   - We will credit you in security advisories (unless you prefer to remain anonymous)

### Response Timeline

- **Critical** (CVSS 9.0+): Fix within 24-48 hours, patch release within 1 week
- **High** (CVSS 7.0-8.9): Fix within 1 week, patch release within 2 weeks
- **Medium** (CVSS 4.0-6.9): Fix within 2 weeks, included in next release
- **Low** (CVSS 0.1-3.9): Fix included in next scheduled release

## Security Features

### Phase 4a — Implemented ✅

- **Password strength validation** – Min 8 chars, uppercase + lowercase + digit required
- **Email validation** – RFC-compliant validation via `EmailStr`
- **Security headers** – X-Content-Type-Options, X-Frame-Options, Referrer-Policy, Permissions-Policy, HSTS (prod), CSP
- **Secret key validation** – Rejects default key and requires 32+ characters
- **File upload hardening** – Magic byte validation, extension allowlist, double-extension strip
- **Input validation** – `max_length` on all user-facing string fields

### Phase 4b — In Progress ⏳

- Rate limiting (5 req/min auth endpoints, 60 req/min general, 10 req/min uploads)
- Account lockout (5 failures in 15 min → 15 min lockout)
- CSRF protection for state-changing operations
- Session invalidation on password change
- Audit logging for admin actions

### Phase 5 — Planned ⏳

- Field-level encryption for sensitive data (email, messages)
- Encrypted database backups
- PII anonymisation for deleted accounts
- CSP tuning per route
- Automated dependency vulnerability scanning
- Container image scanning
- Secrets management integration

## Known Security Considerations

### Authentication & Authorization

- JWT-based auth using stdlib `jwt` + bcrypt via `passlib`
- No third-party JWT library used (reduces attack surface)
- All protected endpoints require `Authorization: Bearer <token>` header
- 401 returned for missing/invalid tokens, 403 for insufficient permissions

### Data Privacy

- Community-scoped messaging prevents cross-community message leaks
- Resource/skill filtering respects community membership
- User profiles do not expose email addresses publicly
- Messages tied to booking context to prevent information leakage

### Crisis Mode Security

- Red Sky mode requires explicit admin toggle or 60% community vote
- Emergency tickets restricted to crisis communities
- Leader/admin roles enforced at database level
- Cross-instance alerts do not expose sensitive instance data

### Database Security

- **Production:** PostgreSQL 16 required with encrypted connections
- **Development:** SQLite with in-memory option for tests
- Alembic migrations applied automatically on startup
- Foreign keys enforced with `index=True` for query performance
- No hardcoded credentials in code (all via environment variables)

### API Security

- CORS restricted to configured origins (default: localhost only)
- All user input validated against Pydantic schemas
- File uploads limited by size (check `MAX_UPLOAD_SIZE` in config)
- Rate limiting on auth endpoints (pending Phase 4b)
- SQL injection prevented by SQLAlchemy ORM parameterization

### Frontend Security

- SvelteKit CSP headers in production
- No hardcoded API keys or secrets in frontend code
- JWT stored in localStorage with domain-specific scope
- XSS protection via SvelteKit's auto-escaping
- No eval() or dynamic script execution

## Dependency Management

### Regular Updates

- Dependencies updated monthly
- Security advisories reviewed weekly
- Critical patches applied immediately
- Changelog documents major version updates

### Vulnerable Dependency Response

1. Check if usage is affected by vulnerability
2. If affected, immediately plan upgrade or workaround
3. Release patch version with fix
4. Notify users via GitHub Security Advisories

### Verified Dependencies

**Python (Backend):**
- `fastapi` 0.115+ (ASGI framework)
- `sqlalchemy` 2.0+ (ORM, no SQL injection risk)
- `pydantic` v2+ (input validation)
- `passlib` + `bcrypt` (password hashing)
- `alembic` 1.14+ (migrations)

**JavaScript (Frontend):**
- `sveltekit` 2+ (full-stack framework)
- `svelte` 5+ (component framework)
- `typescript` 5+ (type safety)
- `vite` 6+ (build tool)

## Compliance

- **OWASP Top 10:** Phase 4a defenses cover most vectors; Phase 4b/5 completes coverage
- **Data Protection:** GDPR-ready (user anonymisation, data export support planned)
- **Industry Standards:** Follows self-hosted application best practices

## Incident Response

If a security incident is discovered:

1. **Immediate:** Stop further exposure, assess scope
2. **Within 24h:** Notify affected users via email if data exposed
3. **Within 48h:** Publish security advisory with CVE (if applicable)
4. **Within 1 week:** Release patched version
5. **Ongoing:** Post-incident analysis and preventative measures

## Security Testing

### Regular Testing

- Static code analysis (manual reviews)
- Dependency vulnerability scanning (manual checks)
- Automated test suite (198+ tests covering security scenarios)
- Manual penetration testing (quarterly for critical deployments)

### Before Release

- All pull requests reviewed for security implications
- Tests pass against both SQLite (dev) and PostgreSQL (prod-like)
- Security headers verified in production builds
- Dependency audit completed

## Questions?

For security questions or to discuss potential issues privately:
- **Email:** security@neighbourgood.eu
- **Response SLA:** 48 hours for all reports

---

**Last Updated:** 2026-02-27
**Version:** 1.0.0
**Next Review:** 2026-05-27
