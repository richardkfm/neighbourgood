"""Telegram Bot API client.

Sends messages via the Telegram Bot API. All functions are no-ops when
NG_TELEGRAM_BOT_TOKEN is not configured, so the app works without a bot.
"""

import hashlib
import hmac
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_BASE = "https://api.telegram.org/bot{token}/{method}"


def _api_url(method: str) -> str:
    return _BASE.format(token=settings.telegram_bot_token, method=method)


def is_configured() -> bool:
    return bool(settings.telegram_bot_token)


def webhook_secret() -> str:
    """Secret Telegram must echo in X-Telegram-Bot-Api-Secret-Token on webhook calls.

    NG_TELEGRAM_WEBHOOK_SECRET when set; otherwise derived from NG_SECRET_KEY and
    the bot token, so the webhook is never left unauthenticated. The derived
    value is hex, which fits Telegram's allowed secret_token characters.
    """
    if settings.telegram_webhook_secret:
        return settings.telegram_webhook_secret
    return hmac.new(
        settings.secret_key.encode(),
        f"telegram-webhook:{settings.telegram_bot_token}".encode(),
        hashlib.sha256,
    ).hexdigest()


def send_message(chat_id: str, text: str) -> None:
    """Send a Telegram message. Silently skips if bot token is not set."""
    if not is_configured():
        return
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(
                _api_url("sendMessage"),
                json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            )
            if resp.status_code != 200:
                logger.warning("Telegram sendMessage failed: %s", resp.text)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Telegram sendMessage error: %s", exc)


def set_webhook(url: str, secret_token: str) -> bool:
    """Register this server's URL as the Telegram bot webhook."""
    if not is_configured():
        return False
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(
                _api_url("setWebhook"),
                json={"url": url, "secret_token": secret_token},
            )
            return resp.status_code == 200
    except Exception as exc:  # noqa: BLE001
        logger.warning("Telegram setWebhook error: %s", exc)
        return False
