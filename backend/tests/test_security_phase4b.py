"""Tests for Security Phase 4b — rate limiting, account lockout, and CSRF protection."""

import time


# ── Rate limiting (unit-level — tests the store directly) ────────────────────


def test_rate_limit_store_allows_within_limit():
    from app.middleware.rate_limit import RateLimitStore

    store = RateLimitStore()
    for _ in range(5):
        allowed, _ = store.check_and_record("1.2.3.4", "/auth/login")
        assert allowed


def test_rate_limit_store_rejects_over_auth_limit():
    from app.middleware.rate_limit import RateLimitStore

    store = RateLimitStore()
    for _ in range(5):
        store.check_and_record("1.2.3.4", "/auth/login")
    allowed, retry_after = store.check_and_record("1.2.3.4", "/auth/login")
    assert not allowed
    assert retry_after > 0


def test_rate_limit_store_different_ips_are_independent():
    from app.middleware.rate_limit import RateLimitStore

    store = RateLimitStore()
    for _ in range(5):
        store.check_and_record("1.1.1.1", "/auth/login")
    # Different IP should still be allowed
    allowed, _ = store.check_and_record("2.2.2.2", "/auth/login")
    assert allowed


def test_rate_limit_store_different_buckets_are_independent():
    from app.middleware.rate_limit import RateLimitStore

    store = RateLimitStore()
    # Exhaust auth bucket
    for _ in range(5):
        store.check_and_record("1.2.3.4", "/auth/login")
    # General bucket for same IP is unaffected
    allowed, _ = store.check_and_record("1.2.3.4", "/resources")
    assert allowed


def test_rate_limit_store_upload_bucket():
    from app.middleware.rate_limit import RateLimitStore

    store = RateLimitStore()
    for _ in range(10):
        allowed, _ = store.check_and_record("1.2.3.4", "/resources/1/image")
        assert allowed
    # 11th request should be rejected
    allowed, retry_after = store.check_and_record("1.2.3.4", "/resources/1/image")
    assert not allowed
    assert retry_after > 0


def test_rate_limit_store_general_bucket_allows_60():
    from app.middleware.rate_limit import RateLimitStore

    store = RateLimitStore()
    for _ in range(60):
        allowed, _ = store.check_and_record("1.2.3.4", "/resources")
        assert allowed
    allowed, _ = store.check_and_record("1.2.3.4", "/resources")
    assert not allowed


# ── Account lockout (unit-level) ─────────────────────────────────────────────


def test_lockout_not_triggered_initially():
    from app.services.lockout import check_lockout, clear_failures

    clear_failures("fresh@example.com")
    locked, _ = check_lockout("fresh@example.com")
    assert not locked


def test_lockout_triggered_after_five_failures():
    from app.services.lockout import check_lockout, clear_failures, record_failure

    email = "brute@example.com"
    clear_failures(email)
    for _ in range(5):
        record_failure(email)
    locked, retry_after = check_lockout(email)
    assert locked
    assert retry_after > 0


def test_lockout_cleared_after_success():
    from app.services.lockout import check_lockout, clear_failures, record_failure

    email = "cleared@example.com"
    clear_failures(email)
    for _ in range(5):
        record_failure(email)
    assert check_lockout(email)[0]
    clear_failures(email)
    locked, _ = check_lockout(email)
    assert not locked


def test_lockout_case_insensitive():
    from app.services.lockout import check_lockout, clear_failures, record_failure

    clear_failures("CASE@example.com")
    for _ in range(5):
        record_failure("CASE@example.com")
    locked, _ = check_lockout("case@example.com")
    assert locked


# ── Account lockout (integration — through the API) ─────────────────────────


def test_login_records_failure_and_locks(client):
    """Five wrong-password attempts should lock the account."""
    from app.services.lockout import clear_failures

    email = "lockme@example.com"
    clear_failures(email)

    # Register the account
    client.post(
        "/auth/register",
        json={"email": email, "password": "Correct123", "display_name": "Lock Me"},
    )

    # 5 failed attempts
    for _ in range(5):
        res = client.post("/auth/login", json={"email": email, "password": "Wrong123!"})
        assert res.status_code == 401

    # 6th attempt should be locked
    res = client.post("/auth/login", json={"email": email, "password": "Correct123"})
    assert res.status_code == 429
    assert "Retry-After" in res.headers
    assert "locked" in res.json()["detail"].lower()

    # Cleanup
    clear_failures(email)


def test_successful_login_clears_failures(client):
    """A successful login should reset the failure counter."""
    from app.services.lockout import check_lockout, clear_failures

    email = "recover@example.com"
    clear_failures(email)

    client.post(
        "/auth/register",
        json={"email": email, "password": "Correct123", "display_name": "Recover"},
    )

    # 4 failures (not yet locked)
    for _ in range(4):
        client.post("/auth/login", json={"email": email, "password": "Wrong123!"})

    # Successful login
    res = client.post("/auth/login", json={"email": email, "password": "Correct123"})
    assert res.status_code == 200

    # Counter should be reset
    locked, _ = check_lockout(email)
    assert not locked

    clear_failures(email)


def test_login_unified_error_message(client):
    """Both wrong-email and wrong-password should return the same error message."""
    res_no_user = client.post(
        "/auth/login", json={"email": "ghost@example.com", "password": "Password123"}
    )
    assert res_no_user.status_code == 401
    assert res_no_user.json()["detail"] == "Invalid credentials"


# ── CSRF token endpoint ───────────────────────────────────────────────────────


def test_get_csrf_token_returns_token(client):
    res = client.get("/auth/csrf-token")
    assert res.status_code == 200
    data = res.json()
    assert "csrf_token" in data
    assert len(data["csrf_token"]) > 20


def test_csrf_token_validate(client):
    from app.middleware.csrf import generate_csrf_token, validate_csrf_token

    token = generate_csrf_token()
    assert validate_csrf_token(token)


def test_csrf_token_reject_tampered():
    from app.middleware.csrf import validate_csrf_token

    assert not validate_csrf_token("tampered.12345.badsig")


def test_csrf_token_reject_empty():
    from app.middleware.csrf import validate_csrf_token

    assert not validate_csrf_token("")


def test_csrf_token_reject_expired():
    from app.middleware.csrf import _sign, validate_csrf_token

    nonce = "abc123"
    old_ts = str(int(time.time()) - 90_000)  # 25 hours ago
    sig = _sign(nonce, old_ts)
    expired_token = f"{nonce}.{old_ts}.{sig}"
    assert not validate_csrf_token(expired_token)


# ── CSRF middleware (production mode) ────────────────────────────────────────


def test_csrf_middleware_allows_json_post_without_token(client, monkeypatch):
    """JSON requests are exempt — Content-Type: application/json triggers a CORS
    preflight in real browsers, so CSRF is mitigated by CORS itself."""
    import app.config as cfg

    monkeypatch.setattr(cfg.settings, "debug", False)
    res = client.post(
        "/auth/register",
        json={"email": "jsonok@example.com", "password": "Abc12345", "display_name": "X"},
    )
    # Should reach the handler, not be blocked by CSRF
    assert res.status_code != 403


def test_csrf_middleware_blocks_form_post_without_token(client, monkeypatch):
    """Form-encoded POST without CSRF token must be rejected in production."""
    import app.config as cfg

    monkeypatch.setattr(cfg.settings, "debug", False)
    res = client.post(
        "/auth/login",
        data={"email": "x@example.com", "password": "Abc12345"},
        headers={"Origin": "http://localhost:5173"},
    )
    assert res.status_code == 403
    assert "CSRF" in res.json()["detail"]


def test_csrf_middleware_allows_bearer_post_without_token(client, auth_headers, monkeypatch):
    """In production mode, Bearer-authenticated requests bypass CSRF."""
    import app.config as cfg

    monkeypatch.setattr(cfg.settings, "debug", False)
    res = client.get("/resources", headers=auth_headers)
    assert res.status_code == 200


def test_csrf_middleware_allows_form_post_with_valid_token(client, monkeypatch):
    """In production mode, CSRF token + matching Origin allows form submissions."""
    import app.config as cfg
    from app.middleware.csrf import generate_csrf_token

    monkeypatch.setattr(cfg.settings, "debug", False)
    token = generate_csrf_token()
    res = client.post(
        "/auth/login",
        data={"email": "valid@example.com", "password": "Valid123!"},
        headers={
            "Origin": "http://localhost:5173",
            "X-CSRF-Token": token,
        },
    )
    # Should reach the handler (401 for bad credentials, but not 403 CSRF)
    assert res.status_code != 403


def test_csrf_middleware_blocks_wrong_origin(client, monkeypatch):
    """In production mode, a non-allowed Origin is rejected for form submissions."""
    import app.config as cfg
    from app.middleware.csrf import generate_csrf_token

    monkeypatch.setattr(cfg.settings, "debug", False)
    token = generate_csrf_token()
    res = client.post(
        "/auth/login",
        data={"email": "evil@attacker.com", "password": "Evil123!"},
        headers={
            "Origin": "http://evil.attacker.com",
            "X-CSRF-Token": token,
        },
    )
    assert res.status_code == 403
    assert "Origin" in res.json()["detail"]
