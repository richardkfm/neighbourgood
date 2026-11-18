# NeighbourGood Security Hardening Plan

> **Archived plan.** Kept for history; parts of it are outdated. Current status and open work: [docs/roadmap.md](../roadmap.md).

## Current State Summary

The platform (FastAPI + SvelteKit, v0.7.0) has **solid fundamentals**:
- JWT auth with bcrypt password hashing
- Role-based + ownership-based authorization
- Pydantic input validation & SQLAlchemy (no SQL injection)
- File upload MIME type & size checks
- Configurable CORS whitelist

**Key gaps** that need addressing:

| Gap                     | Risk Level |
|-------------------------|------------|
| No password strength rules | High |
| No rate limiting         | High |
| No security headers      | High |
| No account lockout       | High |
| Default insecure secret key accepted | High |
| No email format validation | Medium |
| No audit/security logging | Medium |
| File upload extension bypass possible | Medium |
| No CSRF protection       | Medium |
| No email verification    | Low (for now) |

---

## Phase 1 — Foundation (Critical Hardening)

Immediate, high-impact changes that close the most dangerous gaps.

### 1.1 Password Strength Validation
- **File:** `backend/app/schemas/auth.py`
- Add Pydantic validator: min 8 chars, at least 1 digit, 1 uppercase, 1 lowercase
- Return clear error messages on registration

### 1.2 Email Format Validation
- **File:** `backend/app/schemas/auth.py`
- Use `pydantic.EmailStr` (add `email-validator` to deps) for proper RFC-compliant email validation

### 1.3 Security Headers Middleware
- **File:** `backend/app/main.py` (new middleware)
- Add response headers on every request:
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY`
  - `X-XSS-Protection: 0` (modern best practice — rely on CSP instead)
  - `Strict-Transport-Security: max-age=63072000; includeSubDomains` (when not debug)
  - `Content-Security-Policy: default-src 'self'` (basic policy)
  - `Referrer-Policy: strict-origin-when-cross-origin`
  - `Permissions-Policy: camera=(), microphone=(), geolocation=()`

### 1.4 Secret Key Validation on Startup
- **File:** `backend/app/config.py`
- Add a `model_validator` that **refuses to start** if `secret_key` is the default value or shorter than 32 chars when `debug=False`

### 1.5 Stronger File Upload Validation
- **File:** `backend/app/routers/resources.py`
- Validate file extension against an allowlist (`.jpg`, `.jpeg`, `.png`, `.webp`, `.gif`)
- Cross-check extension against MIME type to prevent mismatches
- Sanitize the extension (strip double extensions like `.php.jpg`)

### 1.6 Input Length Limits on Text Fields
- **Files:** `backend/app/schemas/*.py`
- Add `max_length` constraints to all free-text string fields:
  - `display_name`: max 100
  - `title`: max 200
  - `description`: max 5000
  - `message`: max 2000
  - `neighbourhood`: max 200

---

## Phase 2 — Active Defense (Brute-Force & Abuse Protection)

Protect against automated attacks and abuse patterns.

### 2.1 Rate Limiting Middleware ✅ — implemented in v1.7.0
- **File:** `backend/app/middleware/rate_limit.py`
- In-memory sliding-window rate limiter (no external dependency)
- Limits per IP address:
  - **Auth endpoints** (`/auth/login`, `/auth/register`): 5 requests / minute
  - **General API**: 60 requests / minute
  - **File uploads** (paths ending with `/image`): 10 requests / minute
- Returns `429 Too Many Requests` with `Retry-After` header
- Bypassed in debug mode to avoid interfering with the test suite

### 2.2 Account Lockout / Login Throttling ✅ — implemented in v1.7.0
- **File:** `backend/app/services/lockout.py` (new); `backend/app/routers/auth.py` updated
- Tracks failed login attempts per email (in-memory, 15-minute sliding window)
- After 5 failed attempts → lock account for 15 minutes
- Successful login clears the failure counter
- Returns `429` with `Retry-After` header; email matching is case-insensitive

### 2.3 Security Event Audit Logger
- **File:** `backend/app/services/audit.py` (new)
- Log security-relevant events to structured log:
  - Login success / failure (with IP)
  - Account lockout triggered
  - Password change
  - Admin actions (alert send, federation broadcast)
  - Rate limit hits
- Use Python `logging` with JSON formatter
- Log to file: `logs/security.log`

### 2.4 Harden Auth Responses ✅ — implemented in v1.7.0
- **File:** `backend/app/routers/auth.py`
- Login failure always returns `"Invalid credentials"` (never distinguishes unknown email from wrong password)
- Prevents user enumeration via differing error messages

---

## Phase 3 — Defense in Depth (Hardening & Monitoring)

Additional layers for production readiness.

### 3.1 Request ID & Correlation
- **File:** `backend/app/middleware/request_id.py` (new)
- Generate UUID per request, attach to response header `X-Request-ID`
- Include in all log entries for traceability

### 3.1b CSRF Protection ✅ — implemented in v1.7.0
- **File:** `backend/app/middleware/csrf.py`
- Double-submit token + Origin header validation for unauthenticated state-changing requests
- Bearer-authenticated requests are exempt (browsers cannot forge the `Authorization` header cross-origin)
- Machine-to-machine endpoints (Telegram webhook, federation receive, mesh sync) explicitly exempt
- `GET /auth/csrf-token` issues HMAC-SHA256-signed tokens valid for 24 hours
- Bypassed in debug mode; enforced in production

### 3.2 CORS Tightening
- **File:** `backend/app/main.py`
- Change `allow_methods=["*"]` → explicit list: `["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]`
- Change `allow_headers=["*"]` → explicit list: `["Authorization", "Content-Type", "X-Request-ID"]`

### 3.3 JWT Improvements
- **File:** `backend/app/services/auth.py`
- Add `iat` (issued-at) claim to tokens
- Add `jti` (JWT ID) claim for future token revocation
- Add issuer (`iss`) claim matching instance name

### 3.4 Secure Cookie Settings (for future session support)
- **File:** `backend/app/config.py`
- Add cookie configuration: `HttpOnly`, `Secure`, `SameSite=Lax`
- Prepare for potential session-based auth alongside JWT

### 3.5 Federation Authentication
- **File:** `backend/app/routers/federation.py`
- Add shared-secret HMAC verification for incoming federation requests
- Sign outgoing federation broadcasts
- Validate `instance_url` against known peers before accepting data

### 3.6 Dependency Security Check
- **File:** `pyproject.toml` / CI config
- Add `pip-audit` as dev dependency for known-vulnerability scanning
- Add a `make security-check` target

---

## Implementation Summary

| Phase | Focus | Files Changed | New Files | Scope |
|-------|-------|---------------|-----------|-------|
| **1** | Critical Hardening | 4 | 0 | Validation, headers, config |
| **2** | Abuse Protection | 2 | 2 | Rate limit, lockout, audit log |
| **3** | Defense in Depth | 4 | 1 | JWT, CORS, federation, tooling |

**Total: ~10 files changed, ~3 new files**

Each phase is independently valuable — Phase 1 alone closes the most critical gaps. Phases build on each other but can be deployed incrementally.
