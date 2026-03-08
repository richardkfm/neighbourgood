"""Tests for the Telegram AI natural language interface.

Covers:
- Private-chat NL messages dispatched to the AI handler
- Each intent execution path (search_resource, list_resources, search_skill,
  summarize_crisis, create_request)
- Unknown/help fallback
- Unlinked user is silently ignored
- No-AI fallback (AI not configured → help text returned)
- Group-chat crisis keyword shortcut
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from app.models.community import Community, CommunityMember
from app.models.crisis import EmergencyTicket
from app.models.resource import Resource
from app.models.skill import Skill
from app.models.user import User


# ── Helpers ───────────────────────────────────────────────────────────────────


def _register_and_link(client, db, email="linked@example.com", chat_id="111000111"):
    """Register a user, set their telegram_chat_id, return (user, headers)."""
    res = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "Testpass123",
            "display_name": "Linked User",
            "neighbourhood": "Linkville",
        },
    )
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    user = db.query(User).filter(User.email == email).first()
    user.telegram_chat_id = chat_id
    db.commit()
    return user, headers


def _make_community(db, name="Test Community", mode="blue", created_by_id: int = None) -> Community:
    community = Community(
        name=name,
        postal_code="12345",
        city="Testcity",
        mode=mode,
        is_active=True,
        created_by_id=created_by_id,
    )
    db.add(community)
    db.flush()
    return community


def _join_community(db, user: User, community: Community, role: str = "member"):
    membership = CommunityMember(
        community_id=community.id,
        user_id=user.id,
        role=role,
    )
    db.add(membership)
    db.flush()


def _webhook(client, text: str, chat_id: int = 111000111, chat_type: str = "private"):
    return client.post(
        "/telegram/webhook",
        json={
            "message": {
                "chat": {"id": chat_id, "type": chat_type},
                "text": text,
            }
        },
    )


# ── Unlinked user silently ignored ────────────────────────────────────────────


def test_nl_unlinked_user_ignored(client):
    """Private-chat NL message from unknown chat_id is silently ignored (no send_message call)."""
    with patch("app.services.telegram.send_message") as mock_send:
        res = client.post(
            "/telegram/webhook",
            json={
                "message": {
                    "chat": {"id": 999999999, "type": "private"},
                    "text": "do you have a ladder?",
                }
            },
        )
    assert res.status_code == 200
    mock_send.assert_not_called()


# ── No-AI fallback ────────────────────────────────────────────────────────────


def test_nl_no_ai_returns_help(client, db):
    """When AI is not configured, NL messages return the slash-command help text."""
    user, _ = _register_and_link(client, db, chat_id="222000222")
    community = _make_community(db, created_by_id=user.id)
    _join_community(db, user, community)
    db.commit()

    with patch("app.services.telegram_ai.get_ai_client", return_value=None), \
         patch("app.services.telegram.send_message") as mock_send:
        res = client.post(
            "/telegram/webhook",
            json={
                "message": {
                    "chat": {"id": 222000222, "type": "private"},
                    "text": "do you have a ladder?",
                }
            },
        )
    assert res.status_code == 200
    mock_send.assert_called_once()
    reply = mock_send.call_args[0][1]
    assert "/profile" in reply or "not configured" in reply.lower()


# ── search_resource intent ────────────────────────────────────────────────────


def test_nl_search_resource_found(client, db):
    """AI classifies 'do you have a drill?' → search_resource, returns matching resource."""
    user, _ = _register_and_link(client, db, chat_id="333000333")
    community = _make_community(db, created_by_id=user.id)
    _join_community(db, user, community)
    resource = Resource(
        title="Power Drill",
        category="tools",
        is_available=True,
        owner_id=user.id,
        community_id=community.id,
    )
    db.add(resource)
    db.commit()

    mock_client = MagicMock()
    mock_client.chat.return_value = json.dumps(
        {"intent": "search_resource", "query": "drill", "title": "", "description": ""}
    )

    with patch("app.services.telegram_ai.get_ai_client", return_value=mock_client), \
         patch("app.services.telegram.send_message") as mock_send:
        res = client.post(
            "/telegram/webhook",
            json={
                "message": {
                    "chat": {"id": 333000333, "type": "private"},
                    "text": "do you have a drill?",
                }
            },
        )
    assert res.status_code == 200
    reply = mock_send.call_args[0][1]
    assert "Power Drill" in reply


def test_nl_search_resource_not_found(client, db):
    """search_resource with no match returns a 'no resources' message."""
    user, _ = _register_and_link(client, db, chat_id="333111333")
    community = _make_community(db, created_by_id=user.id)
    _join_community(db, user, community)
    db.commit()

    mock_client = MagicMock()
    mock_client.chat.return_value = json.dumps(
        {"intent": "search_resource", "query": "chainsaw", "title": "", "description": ""}
    )

    with patch("app.services.telegram_ai.get_ai_client", return_value=mock_client), \
         patch("app.services.telegram.send_message") as mock_send:
        res = client.post(
            "/telegram/webhook",
            json={
                "message": {
                    "chat": {"id": 333111333, "type": "private"},
                    "text": "anyone have a chainsaw?",
                }
            },
        )
    assert res.status_code == 200
    reply = mock_send.call_args[0][1]
    assert "No resources" in reply or "chainsaw" in reply


# ── list_resources intent ─────────────────────────────────────────────────────


def test_nl_list_resources(client, db):
    """'What can I borrow?' → list_resources → returns available items."""
    user, _ = _register_and_link(client, db, chat_id="444000444")
    community = _make_community(db, created_by_id=user.id)
    _join_community(db, user, community)
    db.add(Resource(title="Ladder", category="tools", is_available=True,
                    owner_id=user.id, community_id=community.id))
    db.add(Resource(title="Tent", category="outdoor", is_available=True,
                    owner_id=user.id, community_id=community.id))
    db.commit()

    mock_client = MagicMock()
    mock_client.chat.return_value = json.dumps(
        {"intent": "list_resources", "query": "", "title": "", "description": ""}
    )

    with patch("app.services.telegram_ai.get_ai_client", return_value=mock_client), \
         patch("app.services.telegram.send_message") as mock_send:
        res = client.post(
            "/telegram/webhook",
            json={
                "message": {
                    "chat": {"id": 444000444, "type": "private"},
                    "text": "what can I borrow?",
                }
            },
        )
    assert res.status_code == 200
    reply = mock_send.call_args[0][1]
    assert "Ladder" in reply
    assert "Tent" in reply


# ── search_skill intent ───────────────────────────────────────────────────────


def test_nl_search_skill_found(client, db):
    """'Who can help with plumbing?' → search_skill → returns matching skill."""
    user, _ = _register_and_link(client, db, chat_id="555000555")
    community = _make_community(db, created_by_id=user.id)
    _join_community(db, user, community)
    db.add(Skill(title="Plumbing repairs", category="maintenance",
                 skill_type="offer", owner_id=user.id, community_id=community.id))
    db.commit()

    mock_client = MagicMock()
    mock_client.chat.return_value = json.dumps(
        {"intent": "search_skill", "query": "plumbing", "title": "", "description": ""}
    )

    with patch("app.services.telegram_ai.get_ai_client", return_value=mock_client), \
         patch("app.services.telegram.send_message") as mock_send:
        res = client.post(
            "/telegram/webhook",
            json={
                "message": {
                    "chat": {"id": 555000555, "type": "private"},
                    "text": "who can help with plumbing?",
                }
            },
        )
    assert res.status_code == 200
    reply = mock_send.call_args[0][1]
    assert "Plumbing" in reply


# ── summarize_crisis intent ───────────────────────────────────────────────────


def test_nl_summarize_crisis_red_sky(client, db):
    """'What emergency tickets are open?' → summarize_crisis → lists tickets."""
    user, _ = _register_and_link(client, db, chat_id="666000666")
    community = _make_community(db, mode="red", created_by_id=user.id)
    _join_community(db, user, community)
    db.add(EmergencyTicket(
        community_id=community.id,
        author_id=user.id,
        ticket_type="request",
        title="Need warm blankets",
        status="open",
        urgency="high",
    ))
    db.commit()

    mock_client = MagicMock()
    mock_client.chat.return_value = json.dumps(
        {"intent": "summarize_crisis", "query": "", "title": "", "description": ""}
    )

    with patch("app.services.telegram_ai.get_ai_client", return_value=mock_client), \
         patch("app.services.telegram.send_message") as mock_send:
        res = client.post(
            "/telegram/webhook",
            json={
                "message": {
                    "chat": {"id": 666000666, "type": "private"},
                    "text": "what emergency tickets are open?",
                }
            },
        )
    assert res.status_code == 200
    reply = mock_send.call_args[0][1]
    assert "Need warm blankets" in reply


def test_nl_summarize_crisis_blue_sky(client, db):
    """summarize_crisis on a Blue Sky community explains no active crisis."""
    user, _ = _register_and_link(client, db, chat_id="666111666")
    community = _make_community(db, mode="blue", created_by_id=user.id)
    _join_community(db, user, community)
    db.commit()

    mock_client = MagicMock()
    mock_client.chat.return_value = json.dumps(
        {"intent": "summarize_crisis", "query": "", "title": "", "description": ""}
    )

    with patch("app.services.telegram_ai.get_ai_client", return_value=mock_client), \
         patch("app.services.telegram.send_message") as mock_send:
        res = client.post(
            "/telegram/webhook",
            json={
                "message": {
                    "chat": {"id": 666111666, "type": "private"},
                    "text": "any crisis tickets?",
                }
            },
        )
    assert res.status_code == 200
    reply = mock_send.call_args[0][1]
    assert "Blue Sky" in reply


# ── create_request intent ─────────────────────────────────────────────────────


def test_nl_create_request_red_sky(client, db):
    """create_request in a Red Sky community creates an EmergencyTicket."""
    user, _ = _register_and_link(client, db, chat_id="777000777")
    community = _make_community(db, mode="red", created_by_id=user.id)
    _join_community(db, user, community)
    db.commit()

    mock_client = MagicMock()
    mock_client.chat.return_value = json.dumps(
        {
            "intent": "create_request",
            "query": "",
            "title": "No power, need food",
            "description": "We have been without power for 2 days",
        }
    )

    with patch("app.services.telegram_ai.get_ai_client", return_value=mock_client), \
         patch("app.services.telegram.send_message") as mock_send:
        res = client.post(
            "/telegram/webhook",
            json={
                "message": {
                    "chat": {"id": 777000777, "type": "private"},
                    "text": "I need food, we have had no power for 2 days",
                }
            },
        )
    assert res.status_code == 200
    reply = mock_send.call_args[0][1]
    assert "created" in reply.lower() or "Emergency request" in reply

    ticket = db.query(EmergencyTicket).filter(
        EmergencyTicket.community_id == community.id
    ).first()
    assert ticket is not None
    assert ticket.ticket_type == "request"
    assert ticket.author_id == user.id


def test_nl_create_request_blue_sky_rejected(client, db):
    """create_request in Blue Sky mode is rejected with an explanation."""
    user, _ = _register_and_link(client, db, chat_id="777111777")
    community = _make_community(db, mode="blue", created_by_id=user.id)
    _join_community(db, user, community)
    db.commit()

    mock_client = MagicMock()
    mock_client.chat.return_value = json.dumps(
        {"intent": "create_request", "query": "", "title": "Need help", "description": ""}
    )

    with patch("app.services.telegram_ai.get_ai_client", return_value=mock_client), \
         patch("app.services.telegram.send_message") as mock_send:
        res = client.post(
            "/telegram/webhook",
            json={
                "message": {
                    "chat": {"id": 777111777, "type": "private"},
                    "text": "I need emergency help",
                }
            },
        )
    assert res.status_code == 200
    reply = mock_send.call_args[0][1]
    assert "Blue Sky" in reply or "crisis" in reply.lower()

    assert db.query(EmergencyTicket).filter(
        EmergencyTicket.community_id == community.id
    ).count() == 0


# ── Unknown / help fallback ───────────────────────────────────────────────────


def test_nl_unknown_intent_returns_help(client, db):
    """When the LLM returns 'help' intent, the bot returns the help message."""
    user, _ = _register_and_link(client, db, chat_id="888000888")
    community = _make_community(db, created_by_id=user.id)
    _join_community(db, user, community)
    db.commit()

    mock_client = MagicMock()
    mock_client.chat.return_value = json.dumps(
        {"intent": "help", "query": "", "title": "", "description": ""}
    )

    with patch("app.services.telegram_ai.get_ai_client", return_value=mock_client), \
         patch("app.services.telegram.send_message") as mock_send:
        res = client.post(
            "/telegram/webhook",
            json={
                "message": {
                    "chat": {"id": 888000888, "type": "private"},
                    "text": "aslkdjhaskdjhaskdjh",
                }
            },
        )
    assert res.status_code == 200
    reply = mock_send.call_args[0][1]
    assert "/profile" in reply


# ── Group-chat crisis shortcut ────────────────────────────────────────────────


def test_group_chat_crisis_keyword(client, db, auth_headers):
    """A group chat message with 'crisis' keyword triggers crisis summary."""
    from app.models.user import User as UserModel
    user = db.query(UserModel).filter(UserModel.email == "test@example.com").first()
    community = _make_community(db, mode="red", created_by_id=user.id)
    community.telegram_group_id = "-100555001"
    db.commit()

    with patch("app.services.telegram_ai._exec_summarize_crisis",
               return_value="No open tickets."), \
         patch("app.services.telegram.send_message") as mock_send:
        res = client.post(
            "/telegram/webhook",
            json={
                "message": {
                    "chat": {"id": -100555001, "type": "group"},
                    "text": "what's the crisis situation?",
                }
            },
        )
    assert res.status_code == 200
    mock_send.assert_called_once()


def test_group_chat_non_crisis_text_ignored(client, db, auth_headers):
    """A group chat message without crisis keywords is silently ignored."""
    from app.models.user import User as UserModel
    user = db.query(UserModel).filter(UserModel.email == "test@example.com").first()
    community = _make_community(db, created_by_id=user.id)
    community.telegram_group_id = "-100555002"
    db.commit()

    with patch("app.services.telegram.send_message") as mock_send:
        res = client.post(
            "/telegram/webhook",
            json={
                "message": {
                    "chat": {"id": -100555002, "type": "group"},
                    "text": "hello everyone!",
                }
            },
        )
    assert res.status_code == 200
    mock_send.assert_not_called()
