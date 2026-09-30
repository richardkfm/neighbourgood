"""Global Red Sky (effective mode), crisis vote edge cases, alert expiry, body limit, datetimes."""

import datetime
import json
from unittest.mock import MagicMock, patch

import pytest

from app.config import settings
from app.models.community import Community
from app.models.crisis import CrisisVote, EmergencyTicket
from app.models.federation import KnownInstance, RedSkyAlert
from app.models.user import User


def _join(client, cid, headers):
    assert client.post(f"/communities/{cid}/join", headers=headers).status_code == 200


def _vote(client, cid, headers, vote_type):
    return client.post(f"/communities/{cid}/crisis/vote", json={"vote_type": vote_type}, headers=headers)


def _status(client, cid):
    return client.get(f"/communities/{cid}/crisis/status").json()


@pytest.fixture()
def global_red(monkeypatch):
    monkeypatch.setattr(settings, "platform_mode", "red")


# ── Global red / effective mode ──────────────────────────────────


def test_effective_mode_follows_stored_mode_by_default(client, auth_headers, community_id):
    c = client.get(f"/communities/{community_id}").json()
    assert c["mode"] == "blue" and c["effective_mode"] == "blue"
    st = client.get(f"/status?community_id={community_id}").json()
    assert st["mode"] == "blue" and st["effective_mode"] == "blue" and st["instance_red"] is False
    assert st["community_mode"] == "blue"


def test_global_red_makes_every_community_red(client, auth_headers, community_id, global_red):
    c = client.get(f"/communities/{community_id}").json()
    assert c["mode"] == "blue"  # stored mode kept
    assert c["effective_mode"] == "red"
    mine = client.get("/communities/my/memberships", headers=auth_headers).json()
    assert mine[0]["effective_mode"] == "red"
    assert client.get("/communities/map").json()[0]["effective_mode"] == "red"

    st = client.get("/status").json()
    assert st["mode"] == "red" and st["effective_mode"] == "red" and st["instance_red"] is True
    st = client.get(f"/status?community_id={community_id}").json()
    assert st["effective_mode"] == "red" and st["community_mode"] == "blue"

    crisis = _status(client, community_id)
    assert crisis["mode"] == "blue" and crisis["effective_mode"] == "red" and crisis["instance_red"] is True


def test_global_red_allows_pings_and_unmet_needs(client, auth_headers, community_id, global_red):
    res = client.post(
        f"/communities/{community_id}/tickets",
        json={"ticket_type": "emergency_ping", "title": "Help"},
        headers=auth_headers,
    )
    assert res.status_code == 201
    res = client.get(f"/matching/unmet-needs?community_id={community_id}", headers=auth_headers)
    assert res.status_code == 200


def test_pings_refused_when_blue(client, auth_headers, community_id):
    res = client.post(
        f"/communities/{community_id}/tickets",
        json={"ticket_type": "emergency_ping", "title": "Help"},
        headers=auth_headers,
    )
    assert res.status_code == 422


def test_global_red_mesh_ping_not_downgraded(client, db, auth_headers, community_id, global_red):
    import time
    import uuid

    msg = {
        "ng": 1, "type": "emergency_ticket", "community_id": community_id, "sender_name": "Test User",
        "ts": int(time.time() * 1000), "id": str(uuid.uuid4()),
        "data": {"title": "Ping", "ticket_type": "emergency_ping"},
    }
    assert client.post("/mesh/sync", json={"messages": [msg]}, headers=auth_headers).json()["synced"] == 1
    assert db.query(EmergencyTicket).one().ticket_type == "emergency_ping"


def test_global_red_telegram_request_creation(db, auth_headers, client, community_id, global_red):
    from app.services.telegram_ai import _exec_create_request

    user = db.query(User).first()
    community = db.query(Community).filter(Community.id == community_id).one()
    reply = _exec_create_request("Need water", "", user, community, db)
    assert "Blue Sky" not in reply
    assert db.query(EmergencyTicket).count() == 1


def test_stored_mode_applies_again_when_instance_blue(client, auth_headers, community_id, monkeypatch):
    monkeypatch.setattr(settings, "platform_mode", "red")
    # A vote during global red still changes the stored mode
    assert _vote(client, community_id, auth_headers, "activate").status_code == 200
    assert _status(client, community_id)["mode"] == "red"
    monkeypatch.setattr(settings, "platform_mode", "blue")
    assert client.get(f"/communities/{community_id}").json()["effective_mode"] == "red"
    client.post(f"/communities/{community_id}/crisis/toggle", json={"mode": "blue"}, headers=auth_headers)
    assert client.get(f"/communities/{community_id}").json()["effective_mode"] == "blue"


# ── Crisis vote edge cases ───────────────────────────────────────


def test_noop_votes_rejected(client, auth_headers, community_id):
    assert _vote(client, community_id, auth_headers, "deactivate").status_code == 409
    client.post(f"/communities/{community_id}/crisis/toggle", json={"mode": "red"}, headers=auth_headers)
    assert _vote(client, community_id, auth_headers, "activate").status_code == 409


def test_threshold_reevaluated_when_member_leaves(client, db, auth_headers, community_id, register_user):
    # 5 members; 3 activate votes = 60% -> switches. Use 6 members and 3 votes (50%), then 1 leaves.
    others = [register_user(n) for n in range(2, 7)]
    for h in others:
        _join(client, community_id, h)
    for h in (auth_headers, others[0], others[1]):
        assert _vote(client, community_id, h, "activate").status_code == 200
    assert _status(client, community_id)["mode"] == "blue"  # 3/6 = 50%

    # A non-voter leaves: 3/5 = 60% reaches the threshold
    assert client.delete(f"/communities/{community_id}/leave", headers=others[4]).status_code == 204
    st = _status(client, community_id)
    assert st["mode"] == "red"
    assert st["votes_to_activate"] == 0  # votes cleared on the switch


def test_leaving_member_vote_is_removed(client, db, auth_headers, community_id, register_user):
    others = [register_user(n) for n in range(2, 5)]
    for h in others:
        _join(client, community_id, h)
    assert _vote(client, community_id, others[0], "activate").status_code == 200
    client.delete(f"/communities/{community_id}/leave", headers=others[0])
    assert _status(client, community_id)["votes_to_activate"] == 0
    assert db.query(CrisisVote).count() == 0


def test_mode_change_clears_stale_votes(client, db, auth_headers, community_id, register_user):
    other = register_user(2)
    _join(client, community_id, other)
    third = register_user(3)
    _join(client, community_id, third)
    assert _vote(client, community_id, other, "activate").status_code == 200
    # Admin toggles red: the pending activate vote is stale and removed
    client.post(f"/communities/{community_id}/crisis/toggle", json={"mode": "red"}, headers=auth_headers)
    assert db.query(CrisisVote).count() == 0
    # Vote-driven switch back to blue clears votes too
    for h in (auth_headers, other):
        assert _vote(client, community_id, h, "deactivate").status_code == 200
    st = _status(client, community_id)
    assert st["mode"] == "blue" and st["votes_to_deactivate"] == 0


def test_mesh_noop_vote_is_rejected_not_retried(client, auth_headers, community_id):
    import time
    import uuid

    msg = {
        "ng": 1, "type": "crisis_vote", "community_id": community_id, "sender_name": "Test User",
        "ts": int(time.time() * 1000), "id": str(uuid.uuid4()), "data": {"vote_type": "deactivate"},
    }
    res = client.post("/mesh/sync", json={"messages": [msg]}, headers=auth_headers).json()
    assert res["rejected"] == 1 and res["failed_ids"] == []


# ── Alerts: expiry and detail ────────────────────────────────────


def _admin(client, db):
    res = client.post(
        "/auth/register",
        json={"email": "admin@example.com", "password": "Adminpass1", "display_name": "Admin"},
    )
    db.query(User).filter(User.email == "admin@example.com").update({"role": "admin"})
    db.commit()
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _seed_instance(db):
    db.add(KnownInstance(url="https://remote.example.com", name="Remote NG", last_seen_at=datetime.datetime.utcnow()))
    db.commit()


def _published(expires_at=None):
    resp = MagicMock(status_code=200)
    body = {"alert_uid": "a" * 32, "title": "Flood", "description": "d", "severity": "critical"}
    if expires_at is not None:
        body["expires_at"] = expires_at
    resp.json.return_value = body
    return resp


def _receive(client):
    return client.post(
        "/federation/alerts/receive",
        json={"source_instance_url": "https://remote.example.com", "alert_uid": "a" * 32},
    )


@pytest.mark.parametrize("hours, ok", [(0, False), (1, True), (336, True), (337, False)])
@patch("app.routers.federation.httpx.post")
def test_broadcast_duration_bounds(mock_post, client, db, hours, ok):
    headers = _admin(client, db)
    with patch("app.routers.federation.settings.instance_url", "https://home.example.com"):
        res = client.post(
            "/federation/alerts/send",
            json={"title": "T", "severity": "info", "duration_hours": hours},
            headers=headers,
        )
    assert (res.status_code == 200) is ok
    if ok:
        from app.models.federation import SentAlert

        sent = db.query(SentAlert).one()
        delta = sent.expires_at - datetime.datetime.utcnow()
        assert datetime.timedelta(hours=hours) - datetime.timedelta(minutes=1) < delta <= datetime.timedelta(hours=hours)


@patch("app.routers.federation._is_safe_url", return_value=True)
@patch("app.routers.federation.httpx.get")
def test_receiver_stores_sender_expiry(mock_get, _safe, client, db):
    _seed_instance(db)
    expires = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=5)).isoformat()
    mock_get.return_value = _published(expires)
    res = _receive(client)
    assert res.status_code == 201
    body = res.json()
    assert body["expires_at"].endswith("Z")
    assert body["is_active"] is True
    stored = db.query(RedSkyAlert).one().expires_at
    assert datetime.timedelta(hours=4, minutes=59) < stored - datetime.datetime.utcnow() <= datetime.timedelta(hours=5)


@patch("app.routers.federation._is_safe_url", return_value=True)
@patch("app.routers.federation.httpx.get")
def test_receiver_clamps_and_defaults_expiry(mock_get, _safe, client, db):
    _seed_instance(db)
    far = (datetime.datetime.utcnow() + datetime.timedelta(days=365)).isoformat() + "Z"
    mock_get.return_value = _published(far)
    _receive(client)
    stored = db.query(RedSkyAlert).one().expires_at
    assert stored - datetime.datetime.utcnow() <= datetime.timedelta(hours=336)

    db.query(RedSkyAlert).delete()
    db.commit()
    mock_get.return_value = _published(None)  # legacy sender without expiry
    _receive(client)
    stored = db.query(RedSkyAlert).one().expires_at
    assert datetime.timedelta(hours=47) < stored - datetime.datetime.utcnow() <= datetime.timedelta(hours=48)


def test_expired_alerts_are_inactive(client, db):
    now = datetime.datetime.utcnow()
    db.add_all([
        RedSkyAlert(source_instance_url="u", source_instance_name="n", title="Old", expires_at=now - datetime.timedelta(hours=1)),
        RedSkyAlert(source_instance_url="u", source_instance_name="n", title="Live", expires_at=now + datetime.timedelta(hours=1)),
        RedSkyAlert(source_instance_url="u", source_instance_name="n", title="Legacy"),
    ])
    db.commit()
    active = client.get("/federation/alerts?active_only=true").json()
    assert {a["title"] for a in active} == {"Live", "Legacy"}
    everything = {a["title"]: a for a in client.get("/federation/alerts?active_only=false").json()}
    assert everything["Old"]["is_active"] is False
    assert everything["Live"]["is_active"] is True


def test_alert_detail_for_any_logged_in_user(client, db, auth_headers):
    alert = RedSkyAlert(
        source_instance_url="https://remote.example.com", source_instance_name="Remote NG",
        title="Flood", description="Move uphill", severity="critical",
        expires_at=datetime.datetime.utcnow() - datetime.timedelta(minutes=1),
    )
    db.add(alert)
    db.commit()
    res = client.get(f"/federation/alerts/{alert.id}", headers=auth_headers)
    assert res.status_code == 200
    body = res.json()
    assert body["title"] == "Flood" and body["source_instance_name"] == "Remote NG"
    assert body["is_active"] is False  # expired
    assert body["created_at"].endswith("Z") and body["expires_at"].endswith("Z")
    assert client.get(f"/federation/alerts/{alert.id}").status_code == 403
    assert client.get("/federation/alerts/99999", headers=auth_headers).status_code == 404


# ── Request body size limit ──────────────────────────────────────


def test_json_body_over_limit_is_rejected(client, auth_headers):
    big = json.dumps({"messages": [], "pad": "x" * (settings.max_request_body_bytes + 10)})
    res = client.post(
        "/mesh/sync", content=big, headers={**auth_headers, "Content-Type": "application/json"}
    )
    assert res.status_code == 413


def test_chunked_body_over_limit_is_rejected(client, auth_headers):
    chunk = b"x" * 65536

    def gen():
        yield b'{"messages": [], "pad": "'
        for _ in range(settings.max_request_body_bytes // len(chunk) + 2):
            yield chunk
        yield b'"}'

    res = client.post(
        "/mesh/sync", content=gen(), headers={**auth_headers, "Content-Type": "application/json"}
    )
    assert res.status_code == 413


def test_body_under_limit_passes(client, auth_headers):
    res = client.post("/mesh/sync", json={"messages": []}, headers=auth_headers)
    assert res.status_code == 200


def test_multipart_upload_keeps_image_limit(client, auth_headers, community_id):
    """A 2 MB upload is above the JSON limit but within the 5 MB image limit."""
    res = client.post(
        "/resources",
        json={"title": "Drill", "category": "tool", "community_id": community_id},
        headers=auth_headers,
    )
    rid = res.json()["id"]
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * (2 * 1024 * 1024)
    res = client.post(
        f"/resources/{rid}/image", files={"file": ("a.png", png, "image/png")}, headers=auth_headers
    )
    assert res.status_code != 413
    too_big = b"\x89PNG\r\n\x1a\n" + b"\x00" * (settings.max_image_size + 128 * 1024)
    res = client.post(
        f"/resources/{rid}/image", files={"file": ("a.png", too_big, "image/png")}, headers=auth_headers
    )
    assert res.status_code == 413


# ── Datetimes ─────────────────────────────────────────────────────


def test_aware_due_at_is_stored_as_utc(client, db, auth_headers, community_id):
    res = client.post(
        f"/communities/{community_id}/tickets",
        json={"ticket_type": "request", "title": "Due", "due_at": "2030-01-01T12:00:00+02:00"},
        headers=auth_headers,
    )
    assert res.status_code == 201
    body = res.json()
    assert body["due_at"] == "2030-01-01T10:00:00Z"
    assert body["created_at"].endswith("Z") and body["updated_at"].endswith("Z")
    ticket = db.query(EmergencyTicket).one()
    assert ticket.due_at == datetime.datetime(2030, 1, 1, 10, 0)

    res = client.patch(
        f"/communities/{community_id}/tickets/{ticket.id}",
        json={"due_at": "2030-01-01T00:30:00-05:00"},
        headers=auth_headers,
    )
    assert res.json()["due_at"] == "2030-01-01T05:30:00Z"


def test_overdue_aware_due_at_escalates_triage(client, auth_headers, community_id):
    past = (datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3))) - datetime.timedelta(hours=1))
    res = client.post(
        f"/communities/{community_id}/tickets",
        json={"ticket_type": "request", "title": "Late", "urgency": "low", "due_at": past.isoformat()},
        headers=auth_headers,
    )
    assert res.json()["triage_score"] >= 300  # low (100) + overdue (200)


def test_crisis_outputs_are_utc_marked(client, auth_headers, community_id):
    vote = _vote(client, community_id, auth_headers, "activate").json()
    assert vote["created_at"].endswith("Z")
    ticket = client.post(
        f"/communities/{community_id}/tickets", json={"ticket_type": "request", "title": "T"}, headers=auth_headers
    ).json()
    comment = client.post(
        f"/communities/{community_id}/tickets/{ticket['id']}/comments", json={"body": "hi"}, headers=auth_headers
    ).json()
    assert comment["created_at"].endswith("Z")
