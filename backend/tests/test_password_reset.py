"""Tests for the password reset flow (request + confirm)."""

import datetime

from app.models.password_reset import PasswordResetToken
from app.models.user import User
from app.routers.auth import _hash_reset_token
from app.services import notifications
from app.services.lockout import check_lockout, clear_failures, record_failure

GENERIC_DETAIL = "If an account with that email exists, a password reset link has been sent."


def _capture_emails(monkeypatch):
    sent: list[dict] = []

    def fake_send_email(to, subject, body_text, body_html=None):
        sent.append({"to": to, "subject": subject, "body": body_text})
        return True

    monkeypatch.setattr(notifications, "send_email", fake_send_email)
    return sent


def _token_from_email(sent: list[dict]) -> str:
    body = sent[-1]["body"]
    marker = "/reset-password?token="
    assert marker in body
    return body.split(marker, 1)[1].split()[0]


def _login(client, email, password):
    return client.post("/auth/login", json={"email": email, "password": password})


# ── Request ───────────────────────────────────────────────────────


def test_request_same_response_for_known_and_unknown_email(client, auth_headers, monkeypatch):
    _capture_emails(monkeypatch)
    known = client.post("/auth/password-reset/request", json={"email": "test@example.com"})
    unknown = client.post("/auth/password-reset/request", json={"email": "nobody@example.com"})
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json() == {"detail": GENERIC_DETAIL}


def test_request_sends_email_with_link_for_known_email_only(client, auth_headers, monkeypatch):
    sent = _capture_emails(monkeypatch)
    client.post("/auth/password-reset/request", json={"email": "nobody@example.com"})
    assert sent == []

    client.post("/auth/password-reset/request", json={"email": "test@example.com"})
    assert len(sent) == 1
    assert sent[0]["to"] == "test@example.com"
    assert "/reset-password?token=" in sent[0]["body"]
    assert sent[0]["body"].count("http") == 1


def test_request_email_is_case_insensitive(client, auth_headers, monkeypatch):
    sent = _capture_emails(monkeypatch)
    res = client.post("/auth/password-reset/request", json={"email": "TEST@Example.com"})
    assert res.status_code == 202
    assert len(sent) == 1


def test_request_stores_only_a_hash_and_one_hour_expiry(client, auth_headers, db, monkeypatch):
    sent = _capture_emails(monkeypatch)
    client.post("/auth/password-reset/request", json={"email": "test@example.com"})
    raw = _token_from_email(sent)

    rows = db.query(PasswordResetToken).all()
    assert len(rows) == 1
    row = rows[0]
    assert row.token_hash == _hash_reset_token(raw)
    assert row.token_hash != raw
    assert raw not in row.token_hash
    assert row.used_at is None
    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    assert datetime.timedelta(minutes=59) < row.expires_at - now <= datetime.timedelta(hours=1)


def test_request_unknown_email_creates_no_token(client, db, monkeypatch):
    _capture_emails(monkeypatch)
    client.post("/auth/password-reset/request", json={"email": "nobody@example.com"})
    assert db.query(PasswordResetToken).count() == 0


def test_request_invalid_email_422(client):
    res = client.post("/auth/password-reset/request", json={"email": "not-an-email"})
    assert res.status_code == 422


def test_request_missing_email_422(client):
    res = client.post("/auth/password-reset/request", json={})
    assert res.status_code == 422


def test_request_inactive_account_gets_no_token(client, auth_headers, db, monkeypatch):
    sent = _capture_emails(monkeypatch)
    db.query(User).filter(User.email == "test@example.com").update({User.is_active: False})
    db.commit()
    res = client.post("/auth/password-reset/request", json={"email": "test@example.com"})
    assert res.status_code == 202
    assert res.json() == {"detail": GENERIC_DETAIL}
    assert sent == []
    assert db.query(PasswordResetToken).count() == 0


def test_new_request_supersedes_previous_link(client, auth_headers, monkeypatch):
    sent = _capture_emails(monkeypatch)
    client.post("/auth/password-reset/request", json={"email": "test@example.com"})
    first = _token_from_email(sent)
    client.post("/auth/password-reset/request", json={"email": "test@example.com"})
    second = _token_from_email(sent)
    assert first != second

    stale = client.post(
        "/auth/password-reset/confirm", json={"token": first, "new_password": "Newpass456"}
    )
    assert stale.status_code == 400
    ok = client.post(
        "/auth/password-reset/confirm", json={"token": second, "new_password": "Newpass456"}
    )
    assert ok.status_code == 200


def test_password_reset_endpoints_share_the_auth_rate_limit_bucket():
    from app.middleware.rate_limit import RateLimitStore

    store = RateLimitStore()
    for path in ("/auth/password-reset/request", "/auth/password-reset/confirm"):
        for _ in range(5):
            allowed, _ = store.check_and_record("9.9.9.9", path)
            assert allowed
        allowed, retry_after = store.check_and_record("9.9.9.9", path)
        assert not allowed
        assert retry_after > 0
        store = RateLimitStore()


def test_request_is_rate_limited_outside_debug(client, monkeypatch):
    """Through the real middleware: 5 requests per minute per IP, then 429 + Retry-After."""
    from app.config import settings
    from app.middleware import rate_limit

    monkeypatch.setattr(settings, "debug", False)
    monkeypatch.setattr(rate_limit, "_store", rate_limit.RateLimitStore())
    # CSRF middleware also switches on outside debug; JSON requests are exempt.
    statuses = [
        client.post(
            "/auth/password-reset/request",
            json={"email": "nobody@example.com"},
            headers={"Origin": "http://localhost:3800"},
        ).status_code
        for _ in range(6)
    ]
    assert statuses[:5] == [202] * 5
    assert statuses[5] == 429


# ── Confirm ───────────────────────────────────────────────────────


def _request_token(client, monkeypatch, email="test@example.com") -> str:
    sent = _capture_emails(monkeypatch)
    client.post("/auth/password-reset/request", json={"email": email})
    return _token_from_email(sent)


def test_confirm_sets_new_password(client, auth_headers, monkeypatch):
    raw = _request_token(client, monkeypatch)
    res = client.post(
        "/auth/password-reset/confirm", json={"token": raw, "new_password": "Brandnew789"}
    )
    assert res.status_code == 200
    assert _login(client, "test@example.com", "Brandnew789").status_code == 200
    assert _login(client, "test@example.com", "Testpass123").status_code == 401


def test_confirm_token_is_single_use(client, auth_headers, db, monkeypatch):
    raw = _request_token(client, monkeypatch)
    first = client.post(
        "/auth/password-reset/confirm", json={"token": raw, "new_password": "Brandnew789"}
    )
    assert first.status_code == 200
    assert db.query(PasswordResetToken).one().used_at is not None

    second = client.post(
        "/auth/password-reset/confirm", json={"token": raw, "new_password": "Another789x"}
    )
    assert second.status_code == 400
    assert _login(client, "test@example.com", "Brandnew789").status_code == 200
    assert _login(client, "test@example.com", "Another789x").status_code == 401


def test_confirm_expired_token_400(client, auth_headers, db, monkeypatch):
    raw = _request_token(client, monkeypatch)
    row = db.query(PasswordResetToken).one()
    row.expires_at = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) - datetime.timedelta(
        seconds=1
    )
    db.commit()

    res = client.post(
        "/auth/password-reset/confirm", json={"token": raw, "new_password": "Brandnew789"}
    )
    assert res.status_code == 400
    assert _login(client, "test@example.com", "Testpass123").status_code == 200


def test_confirm_unknown_token_400(client):
    res = client.post(
        "/auth/password-reset/confirm", json={"token": "nope", "new_password": "Brandnew789"}
    )
    assert res.status_code == 400
    assert res.json()["detail"] == "Invalid or expired reset token"


def test_confirm_applies_password_strength_rules(client, auth_headers, db, monkeypatch):
    raw = _request_token(client, monkeypatch)
    for weak in ("short1A", "alllowercase1", "ALLUPPERCASE1", "NoDigitsHere"):
        res = client.post(
            "/auth/password-reset/confirm", json={"token": raw, "new_password": weak}
        )
        assert res.status_code == 422, weak
    # A rejected password must not burn the token
    assert db.query(PasswordResetToken).one().used_at is None
    ok = client.post(
        "/auth/password-reset/confirm", json={"token": raw, "new_password": "Brandnew789"}
    )
    assert ok.status_code == 200


def test_confirm_missing_fields_422(client):
    assert client.post("/auth/password-reset/confirm", json={"token": "x"}).status_code == 422
    assert (
        client.post("/auth/password-reset/confirm", json={"new_password": "Brandnew789"}).status_code
        == 422
    )


def test_confirm_clears_lockout(client, auth_headers, monkeypatch):
    email = "test@example.com"
    clear_failures(email)
    for _ in range(5):
        record_failure(email)
    assert check_lockout(email)[0]
    assert _login(client, email, "Testpass123").status_code == 429

    raw = _request_token(client, monkeypatch)
    res = client.post(
        "/auth/password-reset/confirm", json={"token": raw, "new_password": "Brandnew789"}
    )
    assert res.status_code == 200
    assert not check_lockout(email)[0]
    assert _login(client, email, "Brandnew789").status_code == 200


def test_confirm_for_account_deactivated_after_request_400(client, auth_headers, db, monkeypatch):
    raw = _request_token(client, monkeypatch)
    db.query(User).filter(User.email == "test@example.com").update({User.is_active: False})
    db.commit()
    res = client.post(
        "/auth/password-reset/confirm", json={"token": raw, "new_password": "Brandnew789"}
    )
    assert res.status_code == 400
