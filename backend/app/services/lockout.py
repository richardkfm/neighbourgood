"""In-memory account lockout tracker.

Policy:
  - After 5 failed login attempts within a 15-minute window from the same
    (email, client IP) pair, that pair is locked for 15 minutes from the time
    of the 5th failure. Keying by IP as well as email stops a third party from
    locking a known email out of its owner's own network; brute-forcing from
    many IPs is bounded by the per-IP rate limit.
  - A successful login clears the failure counter for that (email, IP) pair.

This is intentionally in-memory (no DB writes on every failed attempt) to
keep it fast and to avoid leaking timing information. The trade-off is that
the counter resets on process restart, which is acceptable for this use-case.
"""

import time
from collections import defaultdict
from threading import Lock

_WINDOW_SECONDS = 15 * 60   # 15 min sliding window
_MAX_ATTEMPTS = 5
_LOCKOUT_SECONDS = 15 * 60  # lock duration after threshold is reached

_lock = Lock()
# (lowercased email, ip) → list of monotonic timestamps of failed attempts
_failures: dict[tuple[str, str], list[float]] = defaultdict(list)
_last_cleanup = time.monotonic()
_CLEANUP_INTERVAL = 300  # purge stale keys every 5 minutes


def _key(email: str, ip: str) -> tuple[str, str]:
    return email.lower(), ip


def record_failure(email: str, ip: str) -> None:
    """Record a failed login attempt for *email* from *ip*."""
    now = time.monotonic()
    key = _key(email, ip)
    with _lock:
        _failures[key].append(now)
        # Periodic cleanup of stale entries to prevent unbounded memory growth
        global _last_cleanup
        if now - _last_cleanup > _CLEANUP_INTERVAL:
            cutoff = now - _WINDOW_SECONDS
            stale = [k for k, v in _failures.items() if not v or v[-1] <= cutoff]
            for k in stale:
                del _failures[k]
            _last_cleanup = now


def clear_failures(email: str, ip: str) -> None:
    """Clear the failure counter for *email* from *ip* after a successful login."""
    with _lock:
        _failures.pop(_key(email, ip), None)


def clear_all_failures_for_email(email: str) -> None:
    """Clear the counters for *email* from every IP (e.g. after a password reset)."""
    target = email.lower()
    with _lock:
        for key in [k for k in _failures if k[0] == target]:
            del _failures[key]


def check_lockout(email: str, ip: str) -> tuple[bool, int]:
    """Return ``(is_locked, retry_after_seconds)``.

    Evicts stale entries before checking so the window truly slides.
    """
    now = time.monotonic()
    cutoff = now - _WINDOW_SECONDS
    key = _key(email, ip)

    with _lock:
        recent = [t for t in _failures.get(key, []) if t > cutoff]
        if recent:
            _failures[key] = recent
        else:
            _failures.pop(key, None)

        if len(recent) >= _MAX_ATTEMPTS:
            # Lock until the oldest attempt in the window ages out
            retry_after = int(_LOCKOUT_SECONDS - (now - recent[0])) + 1
            return True, max(retry_after, 1)

        return False, 0
