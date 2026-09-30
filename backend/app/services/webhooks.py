"""Generic outbound webhook dispatcher and Telegram event fan-out.

Call dispatch_event() after any state-changing action. It runs as a
FastAPI BackgroundTask so it never blocks the HTTP response.
"""

import hashlib
import hmac
import html
import json
import logging
from datetime import datetime, timezone

import httpx

from app.config import settings
from app.services import telegram as tg
from app.utils.net import is_safe_url

logger = logging.getLogger(__name__)


# ── Telegram message templates ────────────────────────────────────


def _e(value) -> str:
    """Escape user-controlled text for Telegram's HTML parse mode."""
    return html.escape(str(value), quote=False)


def _format_personal(event_type: str, payload: dict) -> str | None:
    """Return a personal Telegram message string, or None if not applicable."""
    if event_type == "message.new":
        return f"New message from <b>{_e(payload.get('sender_name', 'someone'))}</b> — open the app to reply."
    if event_type == "booking.created":
        return (
            f"<b>{_e(payload.get('borrower_name', 'Someone'))}</b> wants to borrow "
            f"<b>{_e(payload.get('resource_title', 'your item'))}</b> "
            f"({_e(payload.get('start_date', '?'))} – {_e(payload.get('end_date', '?'))})."
        )
    if event_type == "booking.status_changed":
        return (
            f"Your booking for <b>{_e(payload.get('resource_title', 'an item'))}</b>: "
            f"status changed to <b>{_e(payload.get('status', '?'))}</b>."
        )
    if event_type == "ticket.assigned":
        return (
            f"Ticket assigned to you: [{_e(payload.get('urgency', '?').upper())}] "
            f"<b>{_e(payload.get('title', '?'))}</b>"
        )
    if event_type == "crisis.mode_changed":
        community = _e(payload.get("community_name", "Your community"))
        return f"<b>{community}</b> is now in Red Sky (crisis) mode."
    return None


def _format_group(event_type: str, payload: dict) -> str | None:
    """Return a community group Telegram message string, or None if not applicable."""
    if event_type == "resource.shared":
        return (
            f"<b>{_e(payload.get('actor_name', 'A neighbour'))}</b> shared "
            f"<b>'{_e(payload.get('title', 'an item'))}'</b> for borrowing!"
        )
    if event_type == "skill.created":
        skill_type = payload.get("skill_type", "offer")
        category = _e(payload.get("category", ""))
        title = _e(payload.get("title", "a skill"))
        actor = _e(payload.get("actor_name", "A neighbour"))
        if skill_type == "offer":
            return f"<b>{actor}</b> is offering <b>'{title}'</b> ({category}) — connect in the app!"
        return f"<b>{actor}</b> is looking for help with <b>'{title}'</b> ({category})."
    if event_type == "member.joined":
        return (
            f"Welcome <b>{_e(payload.get('actor_name', 'a new member'))}</b> to "
            f"<b>{_e(payload.get('community_name', 'the community'))}</b>!"
        )
    if event_type == "crisis.mode_changed":
        community = _e(payload.get("community_name", "The community"))
        return f"<b>{community}</b> has activated Red Sky mode — check emergency tickets in the app."
    if event_type == "ticket.created":
        urgency = _e(payload.get("urgency", "?").upper())
        ticket_type = _e(payload.get("ticket_type", "ticket"))
        title = _e(payload.get("title", "?"))
        return f"[{urgency}] New {ticket_type}: <b>{title}</b>"
    return None


# ── Webhook delivery ──────────────────────────────────────────────


def _sign_payload(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _deliver_webhook(url: str, secret: str, event_type: str, payload: dict) -> None:
    """POST signed event payload to a registered webhook URL.

    The target is re-validated here (not just at registration) because DNS can
    change between create time and delivery time.
    """
    if not is_safe_url(url, allow_private=settings.webhook_allow_private):
        logger.warning("Blocked webhook delivery to non-public or invalid URL: %s", url)
        return
    body = json.dumps(
        {"event": event_type, "data": payload, "timestamp": datetime.now(timezone.utc).isoformat()}
    ).encode()
    signature = _sign_payload(secret, body)
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(
                url,
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-NeighbourGood-Signature": f"sha256={signature}",
                },
            )
            if resp.status_code >= 400:
                logger.warning("Webhook delivery to %s returned %s", url, resp.status_code)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Webhook delivery error to %s: %s", url, exc)


# ── Main dispatch function ────────────────────────────────────────


def dispatch_event(
    db,
    event_type: str,
    payload: dict,
    user_ids: list[int] | None = None,
    community_id: int | None = None,
) -> None:
    """Fan-out an event to all registered webhooks and Telegram channels.

    Intended to be called as a FastAPI BackgroundTask so it does not block
    the HTTP response. All failures are logged and swallowed.
    """
    from app.models.community import Community, CommunityMember
    from app.models.user import User
    from app.models.webhook import Webhook

    user_ids = user_ids or []

    # ── 1. Generic webhooks ──────────────────────────────────────
    try:
        all_webhooks = db.query(Webhook).filter(Webhook.is_active == True).all()  # noqa: E712
        # Community-wide events (resource.shared, skill.created, member.joined, ...)
        # carry no target users; they go to webhooks of the community's members.
        community_member_ids: set[int] = set()
        if community_id is not None:
            community_member_ids = {
                row[0]
                for row in db.query(CommunityMember.user_id).filter(
                    CommunityMember.community_id == community_id
                )
            }
        for wh in all_webhooks:
            try:
                subscribed = json.loads(wh.event_types)
            except Exception:
                continue
            if event_type not in subscribed:
                continue
            # Match scope: user webhooks fire for their own events and for events
            # in communities they belong to; community webhooks fire for community events.
            if wh.owner_type == "user" and (
                wh.owner_id in user_ids or wh.owner_id in community_member_ids
            ):
                _deliver_webhook(wh.url, wh.secret, event_type, payload)
            elif wh.owner_type == "community" and wh.owner_id == community_id:
                _deliver_webhook(wh.url, wh.secret, event_type, payload)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Webhook fan-out error: %s", exc)

    # ── 2. Personal Telegram messages ────────────────────────────
    if tg.is_configured() and user_ids:
        personal_text = _format_personal(event_type, payload)
        if personal_text:
            try:
                users = db.query(User).filter(
                    User.id.in_(user_ids),
                    User.telegram_chat_id.isnot(None),
                ).all()
                for u in users:
                    tg.send_message(u.telegram_chat_id, personal_text)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Telegram personal notify error: %s", exc)

    # ── 3. Community group Telegram message ──────────────────────
    if tg.is_configured() and community_id:
        group_text = _format_group(event_type, payload)
        if group_text:
            try:
                community = db.query(Community).filter(
                    Community.id == community_id,
                    Community.telegram_group_id.isnot(None),
                ).first()
                if community:
                    tg.send_message(community.telegram_group_id, group_text)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Telegram group notify error: %s", exc)
