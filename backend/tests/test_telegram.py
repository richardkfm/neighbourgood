"""Tests for Telegram linking and bot webhook endpoints."""

import datetime
import json
from unittest.mock import patch

import pytest

from app.models.webhook import TelegramLinkToken

# Webhook calls need a configured bot and the webhook secret header
pytestmark = pytest.mark.usefixtures("telegram_bot")


def test_start_link_no_token_configured(client, auth_headers):
    """Returns 503 when bot token is not configured."""
    with patch("app.services.telegram.is_configured", return_value=False):
        res = client.post("/users/me/telegram/start-link", headers=auth_headers)
    assert res.status_code == 503


def test_start_link_configured(client, auth_headers, db):
    """Returns a bot_url when bot token is configured."""
    with patch("app.services.telegram.is_configured", return_value=True), \
         patch("app.config.settings.telegram_bot_name", "TestBot", create=True):
        with patch("app.config.settings") as mock_settings:
            mock_settings.telegram_bot_token = "fake-token"
            mock_settings.telegram_bot_name = "TestBot"
            mock_settings.telegram_webhook_secret = ""
            res = client.post("/users/me/telegram/start-link", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert "bot_url" in data
    assert "t.me" in data["bot_url"]


def test_unlink_telegram(client, auth_headers, db):
    """DELETE /users/me/telegram clears the chat_id."""
    # Set a telegram_chat_id on the user
    from app.models.user import User
    user = db.query(User).filter(User.email == "test@example.com").first()
    user.telegram_chat_id = "123456789"
    db.commit()

    res = client.delete("/users/me/telegram", headers=auth_headers)
    assert res.status_code == 204

    db.refresh(user)
    assert user.telegram_chat_id is None


def test_unlink_telegram_unauthenticated(client):
    res = client.delete("/users/me/telegram")
    assert res.status_code == 403


def test_community_start_link_no_token(client, auth_headers, community_id):
    with patch("app.services.telegram.is_configured", return_value=False):
        res = client.post(
            f"/communities/{community_id}/telegram/start-link",
            headers=auth_headers,
        )
    assert res.status_code == 503


def test_community_start_link_configured(client, auth_headers, community_id, db):
    with patch("app.services.telegram.is_configured", return_value=True):
        res = client.post(
            f"/communities/{community_id}/telegram/start-link",
            headers=auth_headers,
        )
    assert res.status_code == 200
    assert "token" in res.json()


def test_community_start_link_not_member(client, community_id):
    # Register a non-member user
    client.post(
        "/auth/register",
        json={
            "email": "outsider@example.com",
            "password": "Outsider123",
            "display_name": "Outsider",
        },
    )
    login = client.post("/auth/login", json={"email": "outsider@example.com", "password": "Outsider123"})
    other_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    with patch("app.services.telegram.is_configured", return_value=True):
        res = client.post(
            f"/communities/{community_id}/telegram/start-link",
            headers=other_headers,
        )
    assert res.status_code == 403


def test_community_unlink_telegram(client, auth_headers, community_id, db):
    from app.models.community import Community
    community = db.query(Community).filter(Community.id == community_id).first()
    community.telegram_group_id = "-100123456789"
    db.commit()

    res = client.delete(
        f"/communities/{community_id}/telegram",
        headers=auth_headers,
    )
    assert res.status_code == 204

    db.refresh(community)
    assert community.telegram_group_id is None


def test_telegram_webhook_no_secret_configured(client, db):
    """Telegram bot webhook processes /start without a configured secret."""
    # Create a valid link token
    from app.models.user import User
    user = db.query(User).filter(User.email == "test@example.com").first()
    if not user:
        client.post(
            "/auth/register",
            json={
                "email": "test@example.com",
                "password": "Testpass123",
                "display_name": "Test User",
                "neighbourhood": "Testville",
            },
        )
        user = db.query(User).filter(User.email == "test@example.com").first()

    token = TelegramLinkToken(
        token="valid-test-token-abc123",
        token_type="user",
        owner_id=user.id,
        expires_at=datetime.datetime.utcnow() + datetime.timedelta(minutes=10),
    )
    db.add(token)
    db.commit()

    with patch("app.services.telegram.send_message") as mock_send:
        res = client.post(
            "/telegram/webhook",
            json={
                "message": {
                    "chat": {"id": 987654321, "type": "private"},
                    "text": "/start valid-test-token-abc123",
                }
            },
        )
    assert res.status_code == 200

    db.refresh(user)
    assert user.telegram_chat_id == "987654321"

    db.refresh(token)
    assert token.used is True

    mock_send.assert_called_once()


def test_telegram_webhook_expired_token(client, db, auth_headers):
    """Expired token should send failure message and not link account."""
    from app.models.user import User
    user = db.query(User).filter(User.email == "test@example.com").first()

    token = TelegramLinkToken(
        token="expired-token-xyz",
        token_type="user",
        owner_id=user.id,
        expires_at=datetime.datetime.utcnow() - datetime.timedelta(minutes=1),
    )
    db.add(token)
    db.commit()

    with patch("app.services.telegram.send_message") as mock_send:
        res = client.post(
            "/telegram/webhook",
            json={
                "message": {
                    "chat": {"id": 111222333, "type": "private"},
                    "text": "/start expired-token-xyz",
                }
            },
        )
    assert res.status_code == 200

    db.refresh(user)
    assert user.telegram_chat_id is None
    mock_send.assert_called_once()
    assert "expired" in mock_send.call_args[0][1].lower() or "invalid" in mock_send.call_args[0][1].lower()


def test_telegram_webhook_community_link(client, auth_headers, community_id, db):
    """Test /link {token} command links a community group."""
    from app.models.community import Community

    with patch("app.services.telegram.is_configured", return_value=True):
        token_res = client.post(
            f"/communities/{community_id}/telegram/start-link",
            headers=auth_headers,
        )
    token_str = token_res.json()["token"]

    with patch("app.services.telegram.send_message") as mock_send:
        res = client.post(
            "/telegram/webhook",
            json={
                "message": {
                    "chat": {"id": -100987654321, "type": "group"},
                    "text": f"/link {token_str}",
                }
            },
        )
    assert res.status_code == 200

    community = db.query(Community).filter(Community.id == community_id).first()
    assert community.telegram_group_id == "-100987654321"
    mock_send.assert_called_once()


def test_telegram_webhook_secret_validation(client):
    """Reject requests with wrong secret header when secret is configured."""
    import app.config as cfg_module
    original = cfg_module.settings.telegram_webhook_secret

    try:
        cfg_module.settings.telegram_webhook_secret = "correct-secret"
        res = client.post(
            "/telegram/webhook",
            json={"message": {"chat": {"id": 1, "type": "private"}, "text": "/start abc"}},
            headers={"X-Telegram-Bot-Api-Secret-Token": "wrong-secret"},
        )
        assert res.status_code == 403
    finally:
        cfg_module.settings.telegram_webhook_secret = original


def test_profile_command_no_community(client):
    """Profile command returns ok when group is not linked to any community."""
    res = client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": -100999888777, "type": "group"},
                "text": "/profile Alice",
            }
        },
    )
    assert res.status_code == 200
