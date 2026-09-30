"""Regression tests from the Red Sky / mesh QA pass."""

import uuid
from unittest.mock import patch

from app.models.crisis import CrisisVote, EmergencyTicket
from app.models.mesh import MeshSyncedMessage


def _mesh_msg(msg_type, community_id, data=None, mid=None):
    return {
        "ng": 1,
        "type": msg_type,
        "community_id": community_id,
        "sender_name": "Test User",
        "ts": 1709337600000,
        "id": mid or str(uuid.uuid4()),
        "data": data or {},
    }


def _join(client, headers, cid):
    res = client.post(f"/communities/{cid}/join", headers=headers)
    assert res.status_code in (200, 201), res.text


def _me(client, headers):
    return client.get("/users/me", headers=headers).json()["id"]


def _red(client, headers, cid):
    res = client.post(
        f"/communities/{cid}/crisis/toggle", headers=headers, json={"mode": "red"}
    )
    assert res.status_code == 200


# ── Matching: unmet needs with max-length ticket titles ───────────────


def test_unmet_needs_handles_300_char_ticket_title(client, auth_headers, community_id):
    _red(client, auth_headers, community_id)
    res = client.post(
        f"/communities/{community_id}/tickets",
        headers=auth_headers,
        json={"ticket_type": "request", "title": "x" * 300},
    )
    assert res.status_code == 201
    res = client.get(
        f"/matching/unmet-needs?community_id={community_id}", headers=auth_headers
    )
    assert res.status_code == 200
    assert len(res.json()[0]["title"]) == 300


# ── Tickets: unassign ─────────────────────────────────────────────────


def test_ticket_can_be_unassigned(client, auth_headers, community_id):
    me = _me(client, auth_headers)
    t = client.post(
        f"/communities/{community_id}/tickets",
        headers=auth_headers,
        json={"ticket_type": "request", "title": "Need help"},
    ).json()
    url = f"/communities/{community_id}/tickets/{t['id']}"
    res = client.patch(url, headers=auth_headers, json={"assigned_to_id": me})
    assert res.json()["assigned_to"]["id"] == me
    res = client.patch(url, headers=auth_headers, json={"assigned_to_id": None})
    assert res.status_code == 200
    assert res.json()["assigned_to"] is None
    # Omitting the field leaves assignment untouched
    client.patch(url, headers=auth_headers, json={"assigned_to_id": me})
    res = client.patch(url, headers=auth_headers, json={"title": "Renamed"})
    assert res.json()["assigned_to"]["id"] == me


# ── Privacy: no email / telegram id in nested user objects ────────────


def test_crisis_payloads_do_not_leak_email(client, auth_headers, community_id):
    t = client.post(
        f"/communities/{community_id}/tickets",
        headers=auth_headers,
        json={"ticket_type": "request", "title": "Need help"},
    ).json()
    assert "email" not in t["author"]
    assert "telegram_chat_id" not in t["author"]
    c = client.post(
        f"/communities/{community_id}/tickets/{t['id']}/comments",
        headers=auth_headers,
        json={"body": "hello"},
    ).json()
    assert "email" not in c["author"]
    vote = client.post(
        f"/communities/{community_id}/crisis/vote",
        headers=auth_headers,
        json={"vote_type": "activate"},
    ).json()
    assert "email" not in vote["user"]


def test_public_member_list_and_community_do_not_leak_email(
    client, auth_headers, community_id
):
    members = client.get(f"/communities/{community_id}/members").json()
    assert members and all("email" not in m["user"] for m in members)
    assert all("telegram_chat_id" not in m["user"] for m in members)
    community = client.get(f"/communities/{community_id}").json()
    assert "email" not in community["created_by"]


# ── Vote-triggered Red Sky notifies like the admin toggle ─────────────


def test_vote_threshold_switch_dispatches_crisis_event(
    client, auth_headers, community_id, register_user
):
    _join(client, register_user(2), community_id)
    with patch("app.routers.crisis.dispatch_event") as dispatch:
        res = client.post(
            f"/communities/{community_id}/crisis/vote",
            headers=auth_headers,
            json={"vote_type": "activate"},
        )
        assert res.status_code == 200
        # 1 of 2 members = 50%: below threshold, no switch, no event
        dispatch.assert_not_called()
    h2 = register_user(3)
    _join(client, h2, community_id)  # now 3 members, need 2
    with patch("app.routers.crisis.dispatch_event") as dispatch:
        client.post(
            f"/communities/{community_id}/crisis/vote",
            headers=h2,
            json={"vote_type": "activate"},
        )
        assert dispatch.call_count == 1
        assert dispatch.call_args.args[1] == "crisis.mode_changed"
    status = client.get(f"/communities/{community_id}/crisis/status").json()
    assert status["mode"] == "red"


# ── Mesh: votes honour the 60% threshold ──────────────────────────────


def test_mesh_votes_reach_threshold_and_switch_mode(
    client, auth_headers, community_id, register_user
):
    h2 = register_user(2)
    _join(client, h2, community_id)
    # 2 members -> threshold 2 (ceil(1.2))
    r1 = client.post(
        "/mesh/sync",
        headers=auth_headers,
        json={"messages": [_mesh_msg("crisis_vote", community_id, {"vote_type": "activate"})]},
    )
    assert r1.json()["synced"] == 1
    st = client.get(f"/communities/{community_id}/crisis/status").json()
    assert st["mode"] == "blue" and st["votes_to_activate"] == 1
    r2 = client.post(
        "/mesh/sync",
        headers=h2,
        json={"messages": [_mesh_msg("crisis_vote", community_id, {"vote_type": "activate"})]},
    )
    assert r2.json()["synced"] == 1
    st = client.get(f"/communities/{community_id}/crisis/status").json()
    assert st["mode"] == "red"
    assert st["votes_to_activate"] == 0


def test_mesh_crisis_status_change_clears_votes(
    client, auth_headers, community_id, register_user, db
):
    h2 = register_user(2)
    _join(client, h2, community_id)
    client.post(
        f"/communities/{community_id}/crisis/vote",
        headers=h2,
        json={"vote_type": "activate"},
    )
    assert db.query(CrisisVote).count() == 1
    res = client.post(
        "/mesh/sync",
        headers=auth_headers,
        json={"messages": [_mesh_msg("crisis_status", community_id, {"new_mode": "red"})]},
    )
    assert res.json()["synced"] == 1
    db.expire_all()
    assert db.query(CrisisVote).count() == 0


# ── Mesh: cross-community comment injection ───────────────────────────


def test_mesh_comment_cannot_target_ticket_of_other_community(
    client, auth_headers, register_user, community_id, db
):
    outsider = register_user(2)
    other = client.post(
        "/communities",
        headers=outsider,
        json={"name": "Other", "postal_code": "99999", "city": "Elsewhere"},
    ).json()["id"]
    ticket_mesh_id = str(uuid.uuid4())
    # Outsider creates a ticket in their own community via mesh
    r = client.post(
        "/mesh/sync",
        headers=outsider,
        json={"messages": [_mesh_msg("emergency_ticket", other, {"title": "Private"}, ticket_mesh_id)]},
    )
    assert r.json()["synced"] == 1
    # A member of a *different* community tries to comment on it
    res = client.post(
        "/mesh/sync",
        headers=auth_headers,
        json={
            "messages": [
                _mesh_msg(
                    "ticket_comment",
                    community_id,
                    {"ticket_mesh_id": ticket_mesh_id, "body": "injected"},
                )
            ]
        },
    )
    assert res.json()["synced"] == 0
    assert res.json()["errors"] == 1


# ── Mesh: check-in coordinate validation ──────────────────────────────


def test_mesh_checkin_rejects_out_of_range_coordinates(client, auth_headers, community_id):
    bad = [
        {"lat": 123.0, "lng": 10.0},
        {"lat": 10.0, "lng": -181.0},
        {"lat": 1e308, "lng": 1e308},
    ]
    msgs = [
        _mesh_msg("location_checkin", community_id, {**d, "status": "safe"}) for d in bad
    ]
    res = client.post("/mesh/sync", headers=auth_headers, json={"messages": msgs})
    assert res.json() == {"synced": 0, "duplicates": 0, "errors": 3}
    ok = _mesh_msg("location_checkin", community_id, {"lat": -90, "lng": 180, "status": "safe"})
    res = client.post("/mesh/sync", headers=auth_headers, json={"messages": [ok]})
    assert res.json()["synced"] == 1


# ── Mesh: handler writes and dedup record are one transaction ─────────


def test_mesh_failed_dedup_record_does_not_leave_orphan_ticket(
    client, auth_headers, community_id, db
):
    """If recording the mesh ID fails, the created ticket must be rolled back,
    otherwise a retry would create a duplicate ticket."""
    mid = str(uuid.uuid4())
    from sqlalchemy.exc import IntegrityError

    real_add = db.add

    def add(obj):
        if isinstance(obj, MeshSyncedMessage):
            raise IntegrityError("insert", {}, Exception("unique"))
        return real_add(obj)

    with patch.object(db, "add", side_effect=add):
        res = client.post(
            "/mesh/sync",
            headers=auth_headers,
            json={"messages": [_mesh_msg("emergency_ticket", community_id, {"title": "Once"}, mid)]},
        )
    assert res.json()["synced"] == 0
    assert db.query(EmergencyTicket).count() == 0


# ── Federation alerts: payload validation ─────────────────────────────


def test_broadcast_alert_validates_severity_and_lengths(client, auth_headers):
    for body in (
        {"title": "x", "severity": "apocalyptic"},
        {"title": "", "severity": "info"},
        {"title": "t" * 301, "severity": "info"},
        {"title": "t", "description": "d" * 5001},
    ):
        res = client.post("/federation/alerts/send", headers=auth_headers, json=body)
        assert res.status_code == 422, body


# ── Telegram: user text is HTML-escaped ───────────────────────────────


def test_telegram_group_ticket_message_escapes_html():
    from app.services.webhooks import _format_group, _format_personal

    text = _format_group(
        "ticket.created",
        {"title": "<a href='http://evil'>click</a> & more", "urgency": "high", "ticket_type": "request"},
    )
    assert "<a href" not in text
    assert "&lt;a href" in text and "&amp; more" in text
    text = _format_personal("ticket.assigned", {"title": "a < b", "urgency": "low"})
    assert "a &lt; b" in text


def test_telegram_crisis_summary_escapes_html(client, auth_headers, community_id, db):
    from app.models.community import Community
    from app.services.telegram_ai import _exec_summarize_crisis

    _red(client, auth_headers, community_id)
    client.post(
        f"/communities/{community_id}/tickets",
        headers=auth_headers,
        json={"ticket_type": "request", "title": "Need <b>water</i>"},
    )
    community = db.query(Community).filter(Community.id == community_id).first()
    out = _exec_summarize_crisis(community, db)
    assert "Need &lt;b&gt;water&lt;/i&gt;" in out


def test_telegram_created_request_is_logged_in_activity_feed(
    client, auth_headers, community_id, db
):
    from app.models.community import Community
    from app.models.user import User
    from app.services.telegram_ai import _exec_create_request

    _red(client, auth_headers, community_id)
    community = db.query(Community).filter(Community.id == community_id).first()
    user = db.query(User).first()
    _exec_create_request("Need insulin", "", user, community, db)
    feed = client.get(f"/activity?community_id={community_id}", headers=auth_headers).json()
    assert any("via Telegram" in a["summary"] for a in feed["items"])
