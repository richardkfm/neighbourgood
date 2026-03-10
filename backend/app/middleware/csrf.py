"""CSRF protection middleware.

Strategy
--------
NeighbourGood is a JSON API with Bearer-token auth, so three layers already
mitigate CSRF for the vast majority of requests:

1. **Bearer tokens** — the ``Authorization: Bearer …`` header cannot be
   attached by a browser in a cross-origin request without triggering a CORS
   preflight.  All authenticated endpoints are therefore inherently safe.

2. **JSON Content-Type** — ``Content-Type: application/json`` is *not* a
   `CORS-safelisted request-header value`_, so a cross-origin POST with a
   JSON body also triggers a preflight.  Because the CORS middleware only
   allows configured origins, the browser blocks the request before it
   reaches the handler.

3. **Origin / Referer validation** — as a defence-in-depth layer for any
   remaining form-encoded (``application/x-www-form-urlencoded`` or
   ``multipart/form-data``) requests that do *not* carry a Bearer token, we
   verify the ``Origin`` (or ``Referer``) against the configured CORS origins
   and require a valid ``X-CSRF-Token`` header.

Exemptions
----------
- ``GET``, ``HEAD``, ``OPTIONS`` — safe / idempotent; never checked.
- ``Authorization: Bearer …`` — preflight-protected; exempt.
- ``Content-Type: application/json`` — preflight-protected; exempt.
- Machine-to-machine endpoints (federation, Telegram webhook, mesh sync) —
  use their own auth mechanisms; exempt.
- Debug mode — all checks skipped for local development.

.. _CORS-safelisted request-header value:
   https://fetch.spec.whatwg.org/#cors-safelisted-request-header
"""

import hashlib
import hmac
import secrets
import time
from urllib.parse import urlparse

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings

# HMAC-signed token valid for 24 hours
_TOKEN_TTL_SECONDS = 86_400
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


# ── Token helpers ─────────────────────────────────────────────────────────────

def generate_csrf_token() -> str:
    """Return a signed CSRF token of the form ``<nonce>.<timestamp>.<signature>``."""
    nonce = secrets.token_hex(16)
    ts = str(int(time.time()))
    sig = _sign(nonce, ts)
    return f"{nonce}.{ts}.{sig}"


def validate_csrf_token(token: str) -> bool:
    """Return ``True`` if *token* is a valid, unexpired CSRF token."""
    try:
        nonce, ts_str, sig = token.split(".", 2)
    except ValueError:
        return False

    # Check expiry
    try:
        issued_at = int(ts_str)
    except ValueError:
        return False
    if time.time() - issued_at > _TOKEN_TTL_SECONDS:
        return False

    # Constant-time MAC verification
    expected = _sign(nonce, ts_str)
    return hmac.compare_digest(sig, expected)


def _sign(nonce: str, ts: str) -> str:
    key = settings.secret_key.encode()
    msg = f"{nonce}.{ts}".encode()
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


# ── Origin helpers ────────────────────────────────────────────────────────────

def _allowed_origins() -> frozenset[str]:
    origins = set(settings.cors_origins)
    # Always allow localhost in debug mode
    if settings.debug:
        origins.update({"http://localhost", "http://127.0.0.1"})
    return frozenset(origins)


def _origin_matches(request: Request) -> bool:
    """Return True if the request Origin/Referer is in the allowed set."""
    allowed = _allowed_origins()

    origin = request.headers.get("origin")
    if origin:
        return origin.rstrip("/") in allowed

    referer = request.headers.get("referer")
    if referer:
        parsed = urlparse(referer)
        base = f"{parsed.scheme}://{parsed.netloc}"
        return base.rstrip("/") in allowed

    # No origin information — only allow in debug mode
    return settings.debug


# ── Middleware ────────────────────────────────────────────────────────────────

# Machine-to-machine endpoints that use their own auth mechanisms (e.g. webhook
# secrets, federation tokens) and are never called from a browser form.
_M2M_EXEMPT_PATHS: frozenset[str] = frozenset({
    "/telegram/webhook",
    "/federation/alerts/receive",
    "/federation/migrate/import",
    "/mesh/sync",
    "/webhooks/inbound",
})


class CsrfMiddleware(BaseHTTPMiddleware):
    """Reject state-changing requests that lack a valid CSRF proof.

    Skipped when ``NG_DEBUG=true`` so the test suite and local development are
    not interrupted.  In production this enforces:

    1. An ``Origin`` / ``Referer`` header matching a configured CORS origin.
    2. A valid ``X-CSRF-Token`` header for requests without a Bearer token.

    Bearer-token requests are exempt because browsers cannot attach an
    ``Authorization: Bearer`` header cross-origin without a CORS preflight.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        from app.config import settings  # local import to avoid circular at module load

        if settings.debug:
            return await call_next(request)

        if request.method in _SAFE_METHODS:
            return await call_next(request)

        # Bearer-authenticated requests are exempt — the browser can't forge
        # the Authorization header in a cross-origin context.
        auth_header = request.headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            return await call_next(request)

        # JSON requests are exempt — Content-Type: application/json is NOT a
        # CORS-safelisted header value, so the browser MUST send a preflight.
        # If CORS doesn't allow the origin, the request never reaches us.
        content_type = (request.headers.get("content-type") or "").lower()
        if "application/json" in content_type:
            return await call_next(request)

        # Machine-to-machine endpoints use their own auth — exempt from CSRF.
        if request.url.path in _M2M_EXEMPT_PATHS:
            return await call_next(request)

        # For form-encoded unauthenticated requests, require:
        #   (a) a matching Origin/Referer, AND
        #   (b) a valid X-CSRF-Token header
        csrf_token = request.headers.get("x-csrf-token", "")

        if not _origin_matches(request):
            return Response(
                content='{"detail":"CSRF check failed: invalid or missing Origin header."}',
                status_code=403,
                headers={"Content-Type": "application/json"},
            )

        if not validate_csrf_token(csrf_token):
            return Response(
                content='{"detail":"CSRF check failed: missing or invalid X-CSRF-Token header."}',
                status_code=403,
                headers={"Content-Type": "application/json"},
            )

        return await call_next(request)
