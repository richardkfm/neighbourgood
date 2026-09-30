"""Regression tests: session invalidation, webhook SSRF guard and NUL-byte rejection."""

import json

import pytest

from app.services.auth import create_access_token

PASSWORD = "Testpass123"


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── Session invalidation on password / email change ─────────────────────────


def test_change_password_invalidates_old_tokens_and_returns_fresh_one(client, auth_headers):
    old_token = auth_headers["Authorization"].split()[1]

    res = client.post(
        "/users/me/change-password",
        headers=auth_headers,
        json={"current_password": PASSWORD, "new_password": "Newpass456"},
    )
    assert res.status_code == 200
    new_token = res.json()["access_token"]
    assert new_token and new_token != old_token
    assert res.json()["email"] == "test@example.com"

    # Old session is signed out, the fresh token keeps working
    assert client.get("/users/me", headers=_bearer(old_token)).status_code == 401
    assert client.get("/users/me", headers=_bearer(new_token)).status_code == 200

    # A new login issues a token for the current version
    login = client.post("/auth/login", json={"email": "test@example.com", "password": "Newpass456"})
    assert login.status_code == 200
    assert client.get("/users/me", headers=_bearer(login.json()["access_token"])).status_code == 200


def test_failed_password_change_keeps_session(client, auth_headers):
    res = client.post(
        "/users/me/change-password",
        headers=auth_headers,
        json={"current_password": "Wrong123", "new_password": "Newpass456"},
    )
    assert res.status_code == 400
    assert client.get("/users/me", headers=auth_headers).status_code == 200


def test_change_email_invalidates_old_tokens_and_returns_fresh_one(client, auth_headers):
    old_token = auth_headers["Authorization"].split()[1]

    res = client.post(
        "/users/me/change-email",
        headers=auth_headers,
        json={"new_email": "new@example.com", "password": PASSWORD},
    )
    assert res.status_code == 200
    new_token = res.json()["access_token"]

    assert client.get("/users/me", headers=_bearer(old_token)).status_code == 401
    me = client.get("/users/me", headers=_bearer(new_token))
    assert me.status_code == 200
    assert me.json()["email"] == "new@example.com"


def test_wrong_password_email_change_does_not_bump_version(client, auth_headers, db):
    from app.models.user import User

    res = client.post(
        "/users/me/change-email",
        headers=auth_headers,
        json={"new_email": "new@example.com", "password": "Wrong123"},
    )
    assert res.status_code == 400
    assert db.query(User).filter(User.email == "test@example.com").first().token_version == 0
    assert client.get("/users/me", headers=auth_headers).status_code == 200


def test_token_with_mismatched_version_rejected(client, auth_headers, db):
    from app.models.user import User

    user = db.query(User).filter(User.email == "test@example.com").first()
    user.token_version = 3
    db.commit()

    assert client.get("/users/me", headers=auth_headers).status_code == 401  # issued at version 0
    assert client.get("/users/me", headers=_bearer(create_access_token(user.id, 3))).status_code == 200
    assert client.get("/users/me", headers=_bearer(create_access_token(user.id, 2))).status_code == 401


def test_optional_auth_ignores_stale_token(db, client, auth_headers):
    from fastapi.security import HTTPAuthorizationCredentials

    from app.dependencies import get_current_user_optional
    from app.models.user import User

    user = db.query(User).filter(User.email == "test@example.com").first()
    stale = HTTPAuthorizationCredentials(scheme="Bearer", credentials=create_access_token(user.id, 0))
    current = HTTPAuthorizationCredentials(scheme="Bearer", credentials=create_access_token(user.id, 1))

    assert get_current_user_optional(stale, db).id == user.id
    user.token_version = 1
    db.commit()
    assert get_current_user_optional(stale, db) is None
    assert get_current_user_optional(current, db).id == user.id


# ── Webhook SSRF guard ──────────────────────────────────────────────────────


def _webhook(url):
    return {"url": url, "secret": "supersecret123", "event_types": ["message.new"]}


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/hook",
        "http://localhost:8300/hook",
        "http://10.0.0.5/hook",
        "http://internal.example.com/hook",  # resolves to 10.0.0.5 (see conftest fake_dns)
        "http://192.168.1.10/hook",
        "http://172.16.0.1/hook",
        "http://169.254.169.254/latest/meta-data",
        "http://100.64.0.1/hook",
        "http://0.0.0.0/hook",
        "http://224.0.0.1/hook",
        "http://240.0.0.1/hook",
        "http://[::1]/hook",
        "http://[fe80::1]/hook",
        "http://[::ffff:10.0.0.1]/hook",
        "ftp://example.com/hook",
        "file:///etc/passwd",
        "http:///nohost",
    ],
)
def test_webhook_create_rejects_internal_or_bad_scheme(client, auth_headers, url):
    res = client.post("/webhooks", json=_webhook(url), headers=auth_headers)
    assert res.status_code == 422, url


def test_webhook_create_accepts_public_url(client, auth_headers):
    res = client.post("/webhooks", json=_webhook("https://hooks.example.com/ng"), headers=auth_headers)
    assert res.status_code == 201


def test_webhook_allow_private_setting(client, auth_headers, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "webhook_allow_private", True)
    res = client.post("/webhooks", json=_webhook("http://192.168.1.10/hook"), headers=auth_headers)
    assert res.status_code == 201
    # Scheme restriction still applies
    res = client.post("/webhooks", json=_webhook("ftp://192.168.1.10/hook"), headers=auth_headers)
    assert res.status_code == 422


def test_webhook_delivery_rechecks_dns(monkeypatch):
    """A hostname that later resolves to a private address must not be contacted."""
    from app.services import webhooks as svc

    calls = []

    class FakeClient:
        def __init__(self, *a, **kw):
            calls.append("client")

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, *a, **kw):
            calls.append("post")

    monkeypatch.setattr(svc.httpx, "Client", FakeClient)

    svc._deliver_webhook("https://hooks.example.com/ng", "s3cretvalue", "message.new", {})
    assert "post" in calls

    calls.clear()
    # DNS now points at an internal address (rebinding)
    monkeypatch.setattr("app.utils.net._resolve", lambda host, port: ["10.1.2.3"])
    svc._deliver_webhook("https://hooks.example.com/ng", "s3cretvalue", "message.new", {})
    assert calls == []


def test_webhook_delivery_respects_allow_private(monkeypatch):
    from app.config import settings
    from app.services import webhooks as svc

    posted = []

    class FakeClient:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, *a, **kw):
            posted.append(a[0])

            class R:
                status_code = 200

            return R()

    monkeypatch.setattr(svc.httpx, "Client", FakeClient)
    monkeypatch.setattr(settings, "webhook_allow_private", True)
    svc._deliver_webhook("http://192.168.1.10/hook", "s3cretvalue", "message.new", {})
    assert posted == ["http://192.168.1.10/hook"]


def test_federation_uses_shared_safe_url_helper():
    from app.routers import federation
    from app.utils import net

    assert federation._is_safe_url is net.is_safe_url
    assert federation._is_safe_url("https://peer.example.org") is True
    assert federation._is_safe_url("http://127.0.0.1:8300") is False
    assert federation._is_safe_url("gopher://peer.example.org") is False


def test_is_public_ip_ranges():
    import ipaddress

    from app.utils.net import is_public_ip

    for bad in ("127.0.0.1", "10.1.1.1", "172.20.0.1", "192.168.0.1", "169.254.1.1", "224.0.0.5",
                "0.0.0.0", "::1", "fe80::1", "fc00::1", "::ffff:192.168.0.1", "ff02::1"):
        assert not is_public_ip(ipaddress.ip_address(bad)), bad
    for good in ("93.184.216.34", "8.8.8.8", "2606:4700:4700::1111"):
        assert is_public_ip(ipaddress.ip_address(good)), good


# ── NUL bytes ───────────────────────────────────────────────────────────────


def test_nul_in_register_body_is_422(client):
    res = client.post(
        "/auth/register",
        json={"email": "nul@example.com", "password": PASSWORD, "display_name": "Bad\u0000Name"},
    )
    assert res.status_code == 422
    assert "NUL" in json.dumps(res.json())


def test_nul_in_resource_fields_is_422(client, auth_headers):
    for field in ("title", "description"):
        body = {"title": "Drill", "category": "tool", "description": "ok"}
        body[field] = "x\u0000y"
        res = client.post("/resources", json=body, headers=auth_headers)
        assert res.status_code == 422, field


def test_nul_nested_in_json_is_422(client, auth_headers):
    res = client.post(
        "/webhooks",
        json={"url": "https://example.com/h", "secret": "supersecret123", "event_types": ["a\u0000b"]},
        headers=auth_headers,
    )
    assert res.status_code == 422


def test_nul_in_query_string_and_path_is_422(client, auth_headers):
    assert client.get("/communities/search?q=a%00b").status_code == 422
    assert client.get("/resources?q=%00", headers=auth_headers).status_code == 422
    assert client.get("/resources/1%00").status_code == 422


def test_raw_nul_byte_in_json_body_is_422(client, auth_headers):
    res = client.post(
        "/resources",
        content=b'{"title": "a\x00b", "category": "tool"}',
        headers={**auth_headers, "Content-Type": "application/json"},
    )
    assert res.status_code == 422


def test_escaped_backslash_u0000_text_is_not_a_nul(client, auth_headers):
    """The literal text backslash-u0000 (an escaped backslash) is harmless and allowed."""
    res = client.post(
        "/resources",
        content=json.dumps({"title": "literal \\u0000 text", "category": "tool"}).encode(),
        headers={**auth_headers, "Content-Type": "application/json"},
    )
    assert res.status_code == 201
    assert res.json()["title"] == "literal \\u0000 text"


def test_bodies_still_reach_the_app_intact(client, auth_headers):
    res = client.post("/resources", json={"title": "Normal title", "category": "tool"}, headers=auth_headers)
    assert res.status_code == 201
    assert res.json()["title"] == "Normal title"


def test_malformed_json_still_reports_normal_error(client, auth_headers):
    res = client.post(
        "/resources",
        content=b'{"title": "\\u0000" ',  # NUL escape inside malformed JSON
        headers={**auth_headers, "Content-Type": "application/json"},
    )
    assert res.status_code == 422
