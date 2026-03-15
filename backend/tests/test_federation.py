"""Tests for federation endpoints – instance directory, alerts, data export/import."""

import datetime
from unittest.mock import patch, MagicMock

import pytest

from app.models.federation import KnownInstance, RedSkyAlert
from app.models.user import User


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_admin(client, db):
    """Register a user and promote to admin; return auth headers."""
    res = client.post(
        "/auth/register",
        json={
            "email": "admin@example.com",
            "password": "Adminpass1",
            "display_name": "Admin User",
        },
    )
    assert res.status_code == 201, res.text
    token = res.json()["access_token"]
    user = db.query(User).filter(User.email == "admin@example.com").first()
    user.role = "admin"
    db.commit()
    return {"Authorization": f"Bearer {token}"}


def _seed_instance(db, url="https://remote.example.com", name="Remote NG"):
    inst = KnownInstance(
        url=url,
        name=name,
        description="A test instance",
        region="EU",
        version="1.8.0",
        platform_mode="blue",
        admin_contact="admin@remote.example.com",
        community_count=3,
        user_count=20,
        resource_count=15,
        skill_count=8,
        event_count=4,
        active_user_count=12,
        is_reachable=True,
        last_seen_at=datetime.datetime.utcnow(),
    )
    db.add(inst)
    db.commit()
    db.refresh(inst)
    return inst


def _seed_alert(db, source_url="https://remote.example.com", title="Test Alert"):
    alert = RedSkyAlert(
        source_instance_url=source_url,
        source_instance_name="Remote NG",
        title=title,
        description="A test alert",
        severity="warning",
        is_active=True,
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


# ── Instance Directory ────────────────────────────────────────────────────────


class TestInstanceDirectory:
    def test_list_empty(self, client):
        res = client.get("/federation/directory")
        assert res.status_code == 200
        assert res.json() == []

    def test_list_returns_instances(self, client, db):
        _seed_instance(db)
        res = client.get("/federation/directory")
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 1
        assert data[0]["name"] == "Remote NG"
        assert data[0]["resource_count"] == 15
        assert data[0]["skill_count"] == 8
        assert data[0]["event_count"] == 4
        assert data[0]["active_user_count"] == 12

    def test_list_reachable_only(self, client, db):
        inst = _seed_instance(db)
        inst.is_reachable = False
        db.commit()
        res = client.get("/federation/directory?reachable_only=true")
        assert res.status_code == 200
        assert len(res.json()) == 0

    @patch("app.routers.federation._fetch_instance_info")
    def test_add_instance(self, mock_fetch, client, auth_headers):
        mock_fetch.return_value = {
            "name": "New Instance",
            "description": "A new one",
            "region": "US",
            "version": "1.8.0",
            "platform_mode": "blue",
            "admin_contact": "",
            "community_count": 1,
            "user_count": 5,
            "resource_count": 3,
            "skill_count": 2,
            "event_count": 1,
            "active_user_count": 4,
        }
        res = client.post(
            "/federation/directory",
            json={"url": "https://new.example.com"},
            headers=auth_headers,
        )
        assert res.status_code == 201
        data = res.json()
        assert data["name"] == "New Instance"
        assert data["resource_count"] == 3

    @patch("app.routers.federation._fetch_instance_info")
    def test_add_duplicate_409(self, mock_fetch, client, db, auth_headers):
        _seed_instance(db)
        mock_fetch.return_value = {"name": "Dup"}
        res = client.post(
            "/federation/directory",
            json={"url": "https://remote.example.com"},
            headers=auth_headers,
        )
        assert res.status_code == 409

    @patch("app.routers.federation._fetch_instance_info")
    def test_add_unreachable_422(self, mock_fetch, client, auth_headers):
        mock_fetch.return_value = None
        res = client.post(
            "/federation/directory",
            json={"url": "https://unreachable.example.com"},
            headers=auth_headers,
        )
        assert res.status_code == 422

    def test_add_unauthenticated(self, client):
        res = client.post(
            "/federation/directory",
            json={"url": "https://example.com"},
        )
        assert res.status_code == 403

    def test_remove_admin_only(self, client, db, auth_headers):
        inst = _seed_instance(db)
        # Non-admin cannot delete
        res = client.delete(
            f"/federation/directory/{inst.id}",
            headers=auth_headers,
        )
        assert res.status_code == 403

    def test_remove_by_admin(self, client, db):
        admin_headers = _make_admin(client, db)
        inst = _seed_instance(db)
        res = client.delete(
            f"/federation/directory/{inst.id}",
            headers=admin_headers,
        )
        assert res.status_code == 204

    def test_remove_not_found(self, client, db):
        admin_headers = _make_admin(client, db)
        res = client.delete(
            "/federation/directory/99999",
            headers=admin_headers,
        )
        assert res.status_code == 404

    @patch("app.routers.federation._fetch_instance_info")
    def test_refresh_directory(self, mock_fetch, client, db):
        admin_headers = _make_admin(client, db)
        _seed_instance(db)
        mock_fetch.return_value = {
            "name": "Updated Name",
            "resource_count": 50,
            "skill_count": 25,
            "event_count": 10,
            "active_user_count": 30,
        }
        res = client.post(
            "/federation/directory/refresh",
            headers=admin_headers,
        )
        assert res.status_code == 200
        data = res.json()
        assert data[0]["name"] == "Updated Name"
        assert data[0]["resource_count"] == 50

    def test_refresh_unauthenticated(self, client):
        res = client.post("/federation/directory/refresh")
        assert res.status_code == 403


# ── Red Sky Alerts ────────────────────────────────────────────────────────────


class TestAlerts:
    def test_list_alerts_empty(self, client):
        res = client.get("/federation/alerts")
        assert res.status_code == 200
        assert res.json() == []

    def test_list_active_alerts(self, client, db):
        _seed_alert(db)
        res = client.get("/federation/alerts?active_only=true")
        assert res.status_code == 200
        assert len(res.json()) == 1

    def test_list_includes_inactive(self, client, db):
        a = _seed_alert(db)
        a.is_active = False
        db.commit()
        res = client.get("/federation/alerts?active_only=false")
        assert res.status_code == 200
        assert len(res.json()) == 1

    def test_receive_from_known(self, client, db):
        _seed_instance(db)
        res = client.post(
            "/federation/alerts/receive",
            json={
                "source_instance_url": "https://remote.example.com",
                "source_instance_name": "Remote NG",
                "title": "Flood warning",
                "description": "Heavy rainfall expected",
                "severity": "critical",
            },
        )
        assert res.status_code == 201
        assert res.json()["title"] == "Flood warning"
        assert res.json()["severity"] == "critical"

    def test_receive_from_unknown_403(self, client):
        res = client.post(
            "/federation/alerts/receive",
            json={
                "source_instance_url": "https://unknown.example.com",
                "source_instance_name": "Unknown",
                "title": "Test",
            },
        )
        assert res.status_code == 403

    def test_receive_invalid_severity(self, client, db):
        _seed_instance(db)
        res = client.post(
            "/federation/alerts/receive",
            json={
                "source_instance_url": "https://remote.example.com",
                "source_instance_name": "Remote NG",
                "title": "Test",
                "severity": "extreme",
            },
        )
        assert res.status_code == 422

    def test_dismiss_admin(self, client, db):
        admin_headers = _make_admin(client, db)
        alert = _seed_alert(db)
        res = client.patch(
            f"/federation/alerts/{alert.id}/dismiss",
            headers=admin_headers,
        )
        assert res.status_code == 200
        assert res.json()["is_active"] is False

    def test_dismiss_non_admin_403(self, client, db, auth_headers):
        alert = _seed_alert(db)
        res = client.patch(
            f"/federation/alerts/{alert.id}/dismiss",
            headers=auth_headers,
        )
        assert res.status_code == 403

    def test_dismiss_not_found(self, client, db):
        admin_headers = _make_admin(client, db)
        res = client.patch(
            "/federation/alerts/99999/dismiss",
            headers=admin_headers,
        )
        assert res.status_code == 404


# ── Data Export ───────────────────────────────────────────────────────────────


class TestDataExport:
    def test_export_my_data(self, client, auth_headers):
        res = client.get("/federation/export/my-data", headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert "user" in data
        assert data["user"]["email"] == "test@example.com"
        assert "resources" in data
        assert "skills" in data
        assert "bookings" in data
        assert "messages" in data
        assert "reviews" in data
        assert "communities" in data

    def test_export_unauthenticated(self, client):
        res = client.get("/federation/export/my-data")
        assert res.status_code == 403


# ── Data Import ───────────────────────────────────────────────────────────────


class TestDataImport:
    def test_import_resources_and_skills(self, client, auth_headers):
        res = client.post(
            "/federation/migrate/import",
            json={
                "display_name": "Imported User",
                "resources": [
                    {"title": "My Drill", "category": "tools", "condition": "good"},
                    {"title": "My Ladder", "category": "tools"},
                ],
                "skills": [
                    {"title": "Plumbing", "category": "repairs", "skill_type": "offer"},
                ],
            },
            headers=auth_headers,
        )
        assert res.status_code == 201
        data = res.json()
        assert data["resources_created"] == 2
        assert data["skills_created"] == 1

    def test_import_unauthenticated(self, client):
        res = client.post(
            "/federation/migrate/import",
            json={"display_name": "Test", "resources": [], "skills": []},
        )
        assert res.status_code == 403

    def test_import_empty(self, client, auth_headers):
        res = client.post(
            "/federation/migrate/import",
            json={"display_name": "Test", "resources": [], "skills": []},
            headers=auth_headers,
        )
        assert res.status_code == 201
        assert res.json()["resources_created"] == 0
        assert res.json()["skills_created"] == 0


# ── Instance Info (enriched stats) ────────────────────────────────────────────


class TestInstanceInfoStats:
    def test_instance_info_has_new_fields(self, client):
        res = client.get("/instance/info")
        assert res.status_code == 200
        data = res.json()
        assert "resource_count" in data
        assert "skill_count" in data
        assert "event_count" in data
        assert "active_user_count" in data
