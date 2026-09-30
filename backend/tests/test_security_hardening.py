"""Tests for admin bootstrap (NG_ADMIN_EMAILS), Telegram webhook secret and mesh replay hardening."""

import time
import uuid
from unittest.mock import patch

import pytest

from app.config import settings
from app.models.crisis import CrisisVote, EmergencyTicket
from app.models.mesh_checkin import MeshCheckin
from app.models.user import User
from app.services import telegram as tg


# ── NG_ADMIN_EMAILS ──────────────────────────────────────────────────────────


def _role(client, headers):
    return client.get("/users/me", headers=headers).json()["role"]


def test_admin_email_is_promoted_case_insensitively(client, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "admin_emails", ["  TEST@Example.com "])
    assert _role(client, auth_headers) == "admin"


def test_unlisted_email_stays_member(client, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "admin_emails", ["someone-else@example.com"])
    assert _role(client, auth_headers) == "member"


def test_admin_email_grants_admin_endpoints(client, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "admin_emails", ["test@example.com"])
    res = client.delete("/federation/directory/99999", headers=auth_headers)
    assert res.status_code == 404  # past the admin check


def test_removing_email_does_not_demote(client, auth_headers, db, monkeypatch):
    user = db.query(User).filter(User.email == "test@example.com").first()
    user.role = "admin"
    db.commit()
    monkeypatch.setattr(settings, "admin_emails", [])
    assert _role(client, auth_headers) == "admin"


# ── Telegram webhook secret ──────────────────────────────────────────────────

_UPDATE = {"message": {"chat": {"id": 1, "type": "private"}, "text": "hello"}}


def test_webhook_disabled_without_bot_token(client, monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", "")
    res = client.post("/telegram/webhook", json=_UPDATE)
    assert res.status_code == 404


def test_webhook_requires_secret_even_when_not_configured(client, monkeypatch):
    """With no NG_TELEGRAM_WEBHOOK_SECRET the derived secret is still enforced."""
    monkeypatch.setattr(settings, "telegram_bot_token", "123456:token")
    monkeypatch.setattr(settings, "telegram_webhook_secret", "")
    assert client.post("/telegram/webhook", json=_UPDATE).status_code == 403
    res = client.post(
        "/telegram/webhook", json=_UPDATE, headers={"X-Telegram-Bot-Api-Secret-Token": "guess"}
    )
    assert res.status_code == 403
    res = client.post(
        "/telegram/webhook",
        json=_UPDATE,
        headers={"X-Telegram-Bot-Api-Secret-Token": tg.webhook_secret()},
    )
    assert res.status_code == 200


def test_derived_secret_depends_on_secret_key_and_token(monkeypatch):
    monkeypatch.setattr(settings, "telegram_webhook_secret", "")
    monkeypatch.setattr(settings, "telegram_bot_token", "123456:token")
    first = tg.webhook_secret()
    assert len(first) == 64 and first.isalnum()
    monkeypatch.setattr(settings, "telegram_bot_token", "123456:other")
    assert tg.webhook_secret() != first
    monkeypatch.setattr(settings, "secret_key", "x" * 40)
    monkeypatch.setattr(settings, "telegram_bot_token", "123456:token")
    assert tg.webhook_secret() != first


def test_explicit_secret_takes_precedence(client, monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", "123456:token")
    monkeypatch.setattr(settings, "telegram_webhook_secret", "explicit-secret")
    assert tg.webhook_secret() == "explicit-secret"
    res = client.post(
        "/telegram/webhook", json=_UPDATE, headers={"X-Telegram-Bot-Api-Secret-Token": "explicit-secret"}
    )
    assert res.status_code == 200


def test_register_webhook_admin_only(client, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", "123456:token")
    res = client.post("/telegram/webhook/register", headers=auth_headers)
    assert res.status_code == 403


def test_register_webhook_sends_derived_secret(client, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "admin_emails", ["test@example.com"])
    monkeypatch.setattr(settings, "telegram_bot_token", "123456:token")
    monkeypatch.setattr(settings, "telegram_webhook_secret", "")
    monkeypatch.setattr(settings, "instance_url", "https://ng.example.org/")
    with patch("app.services.telegram.set_webhook", return_value=True) as mock_set:
        res = client.post("/telegram/webhook/register", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["url"] == "https://ng.example.org/telegram/webhook"
    mock_set.assert_called_once_with("https://ng.example.org/telegram/webhook", tg.webhook_secret())


def test_register_webhook_needs_instance_url(client, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "admin_emails", ["test@example.com"])
    monkeypatch.setattr(settings, "telegram_bot_token", "123456:token")
    monkeypatch.setattr(settings, "instance_url", "")
    res = client.post("/telegram/webhook/register", headers=auth_headers)
    assert res.status_code == 400


# ── Mesh: replay window and relayed messages ─────────────────────────────────


def _msg(msg_type, community_id, data, sender_name="Test User", ts=None):
    return {
        "ng": 1,
        "type": msg_type,
        "community_id": community_id,
        "sender_name": sender_name,
        "ts": ts if ts is not None else int(time.time() * 1000),
        "id": str(uuid.uuid4()),
        "data": data,
    }


def _sync(client, headers, *msgs):
    res = client.post("/mesh/sync", headers=headers, json={"messages": list(msgs)})
    assert res.status_code == 200, res.text
    return res.json()


@pytest.mark.parametrize(
    "age_ms",
    [
        (settings.mesh_max_message_age_hours * 3600 + 60) * 1000,  # older than the window
        -2 * 3600 * 1000,  # two hours in the future
    ],
)
def test_mesh_message_outside_time_window_is_rejected(client, auth_headers, community_id, db, age_ms):
    msg = _msg("emergency_ticket", community_id, {"title": "Old"}, ts=int(time.time() * 1000) - age_ms)
    result = _sync(client, auth_headers, msg)
    assert result["rejected"] == 1
    assert result["failed_ids"] == []
    assert db.query(EmergencyTicket).count() == 0


def test_mesh_max_age_is_configurable(client, auth_headers, community_id, db, monkeypatch):
    monkeypatch.setattr(settings, "mesh_max_message_age_hours", 1)
    two_hours_ago = int(time.time() * 1000) - 2 * 3600 * 1000
    result = _sync(client, auth_headers, _msg("emergency_ticket", community_id, {"title": "x"}, ts=two_hours_ago))
    assert result["rejected"] == 1


def test_relayed_vote_is_not_cast_for_the_relay(client, auth_headers, community_id, db):
    result = _sync(
        client, auth_headers,
        _msg("crisis_vote", community_id, {"vote_type": "activate"}, sender_name="Someone Else"),
    )
    assert result["rejected"] == 1
    assert result["failed_ids"] == []
    assert db.query(CrisisVote).count() == 0


def test_relayed_checkin_is_not_stored_as_the_relay(client, auth_headers, community_id, db):
    result = _sync(
        client, auth_headers,
        _msg("location_checkin", community_id, {"lat": 52.5, "lng": 13.4, "status": "safe"}, sender_name="Other"),
    )
    assert result["rejected"] == 1
    assert db.query(MeshCheckin).count() == 0


def test_own_vote_matches_display_name_case_insensitively(client, auth_headers, community_id, db):
    result = _sync(
        client, auth_headers,
        _msg("crisis_vote", community_id, {"vote_type": "activate"}, sender_name=" test user "),
    )
    assert result["synced"] == 1
    # Sole member: the vote reaches the threshold and switches the community
    assert client.get(f"/communities/{community_id}/crisis/status").json()["mode"] == "red"


def test_relayed_ticket_is_marked_unverified(client, auth_headers, community_id, db):
    result = _sync(
        client, auth_headers,
        _msg("emergency_ticket", community_id, {"title": "Water needed", "description": "Two people"},
             sender_name="Mallory"),
    )
    assert result["synced"] == 1
    ticket = db.query(EmergencyTicket).one()
    assert ticket.description.startswith(
        '[Relayed via mesh by Test User; original sender "Mallory" is unverified]\n'
    )
    assert ticket.description.endswith("Two people")
    feed = client.get(f"/activity?community_id={community_id}", headers=auth_headers).json()
    assert any('relayed from "Mallory" (unverified)' in item["summary"] for item in feed["items"])


def test_own_ticket_is_not_marked(client, auth_headers, community_id, db):
    _sync(client, auth_headers, _msg("emergency_ticket", community_id, {"title": "Mine", "description": "d"}))
    assert db.query(EmergencyTicket).one().description == "d"
