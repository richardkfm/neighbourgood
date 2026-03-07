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
