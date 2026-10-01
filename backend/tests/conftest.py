"""Shared fixtures for tests – uses an in-memory SQLite database."""

import os

# Enable debug mode so the default secret key is accepted during tests.
os.environ.setdefault("NG_DEBUG", "true")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app

TEST_DATABASE_URL = "sqlite://"

engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def fake_dns(monkeypatch):
    """Resolve hostnames without real DNS so SSRF checks are deterministic.

    IP literals resolve to themselves, ``localhost`` to loopback, hostnames
    starting with ``internal.`` to a private address, everything else to a
    public address.
    """
    import ipaddress

    def _resolve(hostname, port):
        try:
            ipaddress.ip_address(hostname)
            return [hostname]
        except ValueError:
            pass
        if hostname == "localhost":
            return ["127.0.0.1"]
        if hostname.startswith("internal."):
            return ["10.0.0.5"]
        return ["93.184.216.34"]

    monkeypatch.setattr("app.utils.net._resolve", _resolve)


@pytest.fixture()
def db():
    session = TestSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db):
    def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def auth_headers(client):
    """Register a user and return headers with a valid bearer token."""
    res = client.post(
        "/auth/register",
        json={
            "email": "test@example.com",
            "password": "Testpass123",
            "display_name": "Test User",
            "neighbourhood": "Testville",
        },
    )
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def community_id(client, auth_headers):
    """Create a community owned by the default test user and return its ID."""
    res = client.post(
        "/communities",
        headers=auth_headers,
        json={"name": "Test Community", "postal_code": "12345", "city": "Teststadt"},
    )
    return res.json()["id"]


# ── Shared test helper fixtures ───────────────────────────────────────────────


@pytest.fixture
def register_user(client):
    """Return a helper that registers a user and returns auth headers."""
    def _register(n: int = 2) -> dict:
        resp = client.post(
            "/auth/register",
            json={
                "email": f"user{n}@example.com",
                "password": "Testpass123",
                "display_name": f"User {n}",
            },
        )
        assert resp.status_code == 201, resp.text
        token = resp.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}
    return _register


@pytest.fixture
def create_community_fn(client, auth_headers):
    """Return a helper that creates a community and returns its data."""
    def _create(name: str = "Test Community") -> dict:
        resp = client.post(
            "/communities",
            json={
                "name": name,
                "postal_code": "12345",
                "city": "Testville",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        return resp.json()
    return _create


@pytest.fixture()
def telegram_bot(client, monkeypatch):
    """Configure a (fake) Telegram bot and send the webhook secret on every request.

    Outbound Bot API calls are stubbed; tests that assert on them patch
    ``app.services.telegram.send_message`` themselves.
    """
    from app.config import settings
    from app.services import telegram as tg

    monkeypatch.setattr(settings, "telegram_bot_token", "123456:test-bot-token")
    monkeypatch.setattr(settings, "telegram_webhook_secret", "")
    monkeypatch.setattr(tg, "send_message", lambda *a, **kw: None)
    client.headers["X-Telegram-Bot-Api-Secret-Token"] = tg.webhook_secret()
    yield
    client.headers.pop("X-Telegram-Bot-Api-Secret-Token", None)


@pytest.fixture
def admin_headers(client, db):
    """Headers for a platform admin (role='admin')."""
    from app.models.user import User

    resp = client.post(
        "/auth/register",
        json={
            "email": "platform-admin@example.com",
            "password": "Testpass123",
            "display_name": "Platform Admin",
        },
    )
    assert resp.status_code == 201, resp.text
    user = db.query(User).filter(User.email == "platform-admin@example.com").first()
    user.role = "admin"
    db.commit()
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}
