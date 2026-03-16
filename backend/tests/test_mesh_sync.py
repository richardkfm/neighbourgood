"""Tests for the BLE mesh sync endpoint."""

import uuid


def _mesh_msg(msg_type="emergency_ticket", community_id=1, data=None):
    """Helper to build a mesh message payload."""
    return {
        "ng": 1,
        "type": msg_type,
        "community_id": community_id,
        "sender_name": "Test User",
        "ts": 1709337600000,
        "id": str(uuid.uuid4()),
        "data": data or {},
    }


# ── Auth required ─────────────────────────────────────────────────


def test_sync_requires_auth(client):
    res = client.post("/mesh/sync", json={"messages": []})
    assert res.status_code == 403


# ── Empty sync ────────────────────────────────────────────────────


def test_sync_empty_messages(client, auth_headers):
    res = client.post("/mesh/sync", json={"messages": []}, headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["synced"] == 0
    assert data["duplicates"] == 0
    assert data["errors"] == 0


# ── Sync emergency ticket ────────────────────────────────────────


def test_sync_emergency_ticket(client, auth_headers, community_id):
    msg = _mesh_msg(
        community_id=community_id,
        data={
            "title": "Need water supplies",
            "description": "Flooding in sector 4",
            "ticket_type": "request",
            "urgency": "high",
        },
    )
    res = client.post(
        "/mesh/sync", json={"messages": [msg]}, headers=auth_headers
    )
    assert res.status_code == 200
    data = res.json()
    assert data["synced"] == 1
    assert data["duplicates"] == 0
    assert data["errors"] == 0

    # Verify ticket was created
    tickets_res = client.get(
        f"/communities/{community_id}/tickets", headers=auth_headers
    )
    assert tickets_res.status_code == 200
    items = tickets_res.json()["items"]
    assert any(t["title"] == "Need water supplies" for t in items)


# ── Deduplication ─────────────────────────────────────────────────


def test_sync_deduplication(client, auth_headers, community_id):
    msg = _mesh_msg(
        community_id=community_id,
        data={
            "title": "Duplicate test",
            "ticket_type": "offer",
            "urgency": "low",
        },
    )
    # First sync
    res1 = client.post(
        "/mesh/sync", json={"messages": [msg]}, headers=auth_headers
    )
    assert res1.json()["synced"] == 1

    # Second sync with same message ID
    res2 = client.post(
        "/mesh/sync", json={"messages": [msg]}, headers=auth_headers
    )
    data2 = res2.json()
    assert data2["synced"] == 0
    assert data2["duplicates"] == 1


# ── Crisis vote sync ─────────────────────────────────────────────


def test_sync_crisis_vote(client, auth_headers, community_id):
    msg = _mesh_msg(
        msg_type="crisis_vote",
        community_id=community_id,
        data={"vote_type": "activate"},
    )
    res = client.post(
        "/mesh/sync", json={"messages": [msg]}, headers=auth_headers
    )
    assert res.status_code == 200
    assert res.json()["synced"] == 1

    # Verify vote was recorded
    status_res = client.get(f"/communities/{community_id}/crisis/status")
    assert status_res.status_code == 200
    assert status_res.json()["votes_to_activate"] >= 1


# ── Non-member community ─────────────────────────────────────────


def test_sync_non_member_community(client, auth_headers):
    """Messages for communities the user isn't a member of should error."""
    msg = _mesh_msg(
        community_id=99999,
        data={"title": "Test", "ticket_type": "request", "urgency": "low"},
    )
    res = client.post(
        "/mesh/sync", json={"messages": [msg]}, headers=auth_headers
    )
    assert res.status_code == 200
    assert res.json()["errors"] == 1
    assert res.json()["synced"] == 0


# ── Invalid message type ─────────────────────────────────────────


def test_sync_invalid_message_type(client, auth_headers):
    msg = _mesh_msg()
    msg["type"] = "invalid_type"
    res = client.post(
        "/mesh/sync", json={"messages": [msg]}, headers=auth_headers
    )
    assert res.status_code == 422  # Pydantic validation error


# ── Heartbeat acknowledged but not persisted ─────────────────────


def test_sync_heartbeat_acknowledged(client, auth_headers, community_id):
    msg = _mesh_msg(msg_type="heartbeat", community_id=community_id)
    res = client.post(
        "/mesh/sync", json={"messages": [msg]}, headers=auth_headers
    )
    assert res.status_code == 200
    assert res.json()["synced"] == 1


# ── Missing ticket title ─────────────────────────────────────────


def test_sync_ticket_missing_title(client, auth_headers, community_id):
    msg = _mesh_msg(
        community_id=community_id,
        data={"ticket_type": "request", "urgency": "low"},
    )
    res = client.post(
        "/mesh/sync", json={"messages": [msg]}, headers=auth_headers
    )
    assert res.status_code == 200
    assert res.json()["errors"] == 1


# ── Multiple messages batch ──────────────────────────────────────


def test_sync_batch_messages(client, auth_headers, community_id):
    msgs = [
        _mesh_msg(
            community_id=community_id,
            data={
                "title": f"Batch ticket {i}",
                "ticket_type": "request",
                "urgency": "medium",
            },
        )
        for i in range(5)
    ]
    res = client.post(
        "/mesh/sync", json={"messages": msgs}, headers=auth_headers
    )
    assert res.status_code == 200
    data = res.json()
    assert data["synced"] == 5
    assert data["duplicates"] == 0
    assert data["errors"] == 0


# ── Ticket comment sync ────────────────────────────────────────


def test_sync_ticket_comment(client, auth_headers, community_id):
    """Sync a ticket via mesh, then sync a comment referencing it."""
    ticket_msg = _mesh_msg(
        community_id=community_id,
        data={
            "title": "Need blankets",
            "ticket_type": "request",
            "urgency": "high",
        },
    )
    # Sync the ticket first
    res = client.post(
        "/mesh/sync", json={"messages": [ticket_msg]}, headers=auth_headers
    )
    assert res.json()["synced"] == 1

    # Now sync a comment referencing the ticket's mesh ID
    comment_msg = _mesh_msg(
        msg_type="ticket_comment",
        community_id=community_id,
        data={
            "ticket_mesh_id": ticket_msg["id"],
            "body": "I have 10 blankets available",
        },
    )
    res = client.post(
        "/mesh/sync", json={"messages": [comment_msg]}, headers=auth_headers
    )
    assert res.status_code == 200
    assert res.json()["synced"] == 1
    assert res.json()["errors"] == 0


def test_sync_ticket_comment_missing_ticket(client, auth_headers, community_id):
    """Comment referencing non-existent ticket mesh ID should error."""
    comment_msg = _mesh_msg(
        msg_type="ticket_comment",
        community_id=community_id,
        data={
            "ticket_mesh_id": "nonexistent-mesh-id",
            "body": "Some comment",
        },
    )
    res = client.post(
        "/mesh/sync", json={"messages": [comment_msg]}, headers=auth_headers
    )
    assert res.status_code == 200
    assert res.json()["errors"] == 1
    assert res.json()["synced"] == 0


def test_sync_ticket_comment_empty_body(client, auth_headers, community_id):
    """Comment with empty body should error."""
    comment_msg = _mesh_msg(
        msg_type="ticket_comment",
        community_id=community_id,
        data={"ticket_mesh_id": "some-id", "body": ""},
    )
    res = client.post(
        "/mesh/sync", json={"messages": [comment_msg]}, headers=auth_headers
    )
    assert res.status_code == 200
    assert res.json()["errors"] == 1


# ── Direct message sync ────────────────────────────────────────


def test_sync_direct_message(client, auth_headers, community_id, register_user):
    """Sync a direct message to a user in the same community."""
    # Register second user and join the community
    user2_headers = register_user(2)
    join_res = client.post(
        f"/communities/{community_id}/join", headers=user2_headers
    )
    assert join_res.status_code in (200, 201), join_res.text

    # Get user2 ID
    me_res = client.get("/users/me", headers=user2_headers)
    user2_id = me_res.json()["id"]

    msg = _mesh_msg(
        msg_type="direct_message",
        community_id=community_id,
        data={"recipient_id": user2_id, "body": "Stay safe!"},
    )
    res = client.post(
        "/mesh/sync", json={"messages": [msg]}, headers=auth_headers
    )
    assert res.status_code == 200
    assert res.json()["synced"] == 1
    assert res.json()["errors"] == 0


def test_sync_direct_message_invalid_recipient(client, auth_headers, community_id):
    """Message to non-existent user should error."""
    msg = _mesh_msg(
        msg_type="direct_message",
        community_id=community_id,
        data={"recipient_id": 99999, "body": "Hello?"},
    )
    res = client.post(
        "/mesh/sync", json={"messages": [msg]}, headers=auth_headers
    )
    assert res.status_code == 200
    assert res.json()["errors"] == 1
    assert res.json()["synced"] == 0


# ── Crisis status sync ─────────────────────────────────────────


def test_sync_crisis_status_as_admin(client, auth_headers, community_id):
    """Admin (community creator) can change crisis mode via mesh."""
    msg = _mesh_msg(
        msg_type="crisis_status",
        community_id=community_id,
        data={"new_mode": "red"},
    )
    res = client.post(
        "/mesh/sync", json={"messages": [msg]}, headers=auth_headers
    )
    assert res.status_code == 200
    assert res.json()["synced"] == 1

    # Verify mode changed
    community_res = client.get(
        f"/communities/{community_id}", headers=auth_headers
    )
    assert community_res.json()["mode"] == "red"


def test_sync_crisis_status_as_member(client, auth_headers, community_id, register_user):
    """Regular member cannot change crisis mode via mesh."""
    user2_headers = register_user(3)
    client.post(f"/communities/{community_id}/join", headers=user2_headers)

    msg = _mesh_msg(
        msg_type="crisis_status",
        community_id=community_id,
        data={"new_mode": "red"},
    )
    res = client.post(
        "/mesh/sync", json={"messages": [msg]}, headers=user2_headers
    )
    assert res.status_code == 200
    assert res.json()["errors"] == 1
    assert res.json()["synced"] == 0


# ── Resource offer/request sync ──────────────────────────────────


def test_sync_resource_offer(client, auth_headers, community_id):
    """Sync a resource offer creates a resource listing."""
    msg = _mesh_msg(
        msg_type="resource_offer",
        community_id=community_id,
        data={
            "title": "Portable generator",
            "description": "Can power small devices",
            "category": "electronics",
        },
    )
    res = client.post(
        "/mesh/sync", json={"messages": [msg]}, headers=auth_headers
    )
    assert res.status_code == 200
    assert res.json()["synced"] == 1
    assert res.json()["errors"] == 0

    # Verify resource was created
    resources_res = client.get("/resources", headers=auth_headers)
    assert resources_res.status_code == 200
    items = resources_res.json()["items"]
    assert any(r["title"] == "Portable generator" for r in items)


def test_sync_resource_request(client, auth_headers, community_id):
    """Sync a resource request creates a resource listing."""
    msg = _mesh_msg(
        msg_type="resource_request",
        community_id=community_id,
        data={
            "title": "Water filters",
            "description": "Urgently need water purification",
            "category": "other",
        },
    )
    res = client.post(
        "/mesh/sync", json={"messages": [msg]}, headers=auth_headers
    )
    assert res.status_code == 200
    assert res.json()["synced"] == 1
    assert res.json()["errors"] == 0


def test_sync_resource_missing_title(client, auth_headers, community_id):
    """Resource with no title should error."""
    msg = _mesh_msg(
        msg_type="resource_offer",
        community_id=community_id,
        data={"description": "No title here", "category": "tools"},
    )
    res = client.post(
        "/mesh/sync", json={"messages": [msg]}, headers=auth_headers
    )
    assert res.status_code == 200
    assert res.json()["errors"] == 1
    assert res.json()["synced"] == 0


def test_sync_resource_invalid_category_defaults_to_other(client, auth_headers, community_id):
    """Invalid category falls back to 'other'."""
    msg = _mesh_msg(
        msg_type="resource_offer",
        community_id=community_id,
        data={
            "title": "Mystery item",
            "category": "invalid_cat",
        },
    )
    res = client.post(
        "/mesh/sync", json={"messages": [msg]}, headers=auth_headers
    )
    assert res.status_code == 200
    assert res.json()["synced"] == 1


# ── Location check-in sync ──────────────────────────────────


def test_sync_location_checkin(client, auth_headers, community_id):
    """Sync a location check-in creates a checkin record."""
    msg = _mesh_msg(
        msg_type="location_checkin",
        community_id=community_id,
        data={
            "lat": 51.5074,
            "lng": -0.1278,
            "status": "safe",
            "note": "All good here",
        },
    )
    res = client.post(
        "/mesh/sync", json={"messages": [msg]}, headers=auth_headers
    )
    assert res.status_code == 200
    assert res.json()["synced"] == 1
    assert res.json()["errors"] == 0


def test_sync_location_checkin_need_help(client, auth_headers, community_id):
    """Check-in with need_help status."""
    msg = _mesh_msg(
        msg_type="location_checkin",
        community_id=community_id,
        data={
            "lat": 51.51,
            "lng": -0.13,
            "status": "need_help",
        },
    )
    res = client.post(
        "/mesh/sync", json={"messages": [msg]}, headers=auth_headers
    )
    assert res.status_code == 200
    assert res.json()["synced"] == 1


def test_sync_location_checkin_missing_coords(client, auth_headers, community_id):
    """Check-in without coordinates should error."""
    msg = _mesh_msg(
        msg_type="location_checkin",
        community_id=community_id,
        data={"status": "safe"},
    )
    res = client.post(
        "/mesh/sync", json={"messages": [msg]}, headers=auth_headers
    )
    assert res.status_code == 200
    assert res.json()["errors"] == 1
    assert res.json()["synced"] == 0


def test_get_community_checkins(client, auth_headers, community_id):
    """GET checkins returns recently synced check-ins."""
    # Sync a check-in first
    msg = _mesh_msg(
        msg_type="location_checkin",
        community_id=community_id,
        data={
            "lat": 51.5074,
            "lng": -0.1278,
            "status": "evacuating",
            "note": "Heading north",
        },
    )
    client.post(
        "/mesh/sync", json={"messages": [msg]}, headers=auth_headers
    )

    # Fetch check-ins
    res = client.get(
        f"/mesh/checkins/{community_id}", headers=auth_headers
    )
    assert res.status_code == 200
    checkins = res.json()
    assert len(checkins) >= 1
    assert checkins[0]["status"] == "evacuating"
    assert checkins[0]["lat"] == 51.5074
    assert checkins[0]["display_name"] == "Test User"


def test_get_checkins_requires_membership(client, auth_headers, register_user):
    """Non-members cannot view community check-ins."""
    user2_headers = register_user(4)
    res = client.get(
        "/mesh/checkins/1", headers=user2_headers
    )
    assert res.status_code == 403


# ── Mesh key exchange ────────────────────────────────────────


def test_set_and_get_mesh_key(client, auth_headers):
    """Set and retrieve mesh encryption public key."""
    key_data = "eyJrdHkiOiJFQyIsImNydiI6IlAtMjU2IiwieCI6InRlc3QiLCJ5IjoidGVzdCJ9"
    res = client.put(
        "/mesh/keys/me",
        json={"public_key": key_data},
        headers=auth_headers,
    )
    assert res.status_code == 200

    # Get own key via user ID
    me_res = client.get("/users/me", headers=auth_headers)
    user_id = me_res.json()["id"]

    get_res = client.get(f"/mesh/keys/{user_id}", headers=auth_headers)
    assert get_res.status_code == 200
    assert get_res.json()["public_key"] == key_data


def test_get_mesh_key_not_set(client, auth_headers, register_user):
    """Getting key for user without one returns 404."""
    user2_headers = register_user(5)
    me_res = client.get("/users/me", headers=user2_headers)
    user2_id = me_res.json()["id"]

    res = client.get(f"/mesh/keys/{user2_id}", headers=auth_headers)
    assert res.status_code == 404


# ── Mesh metrics ─────────────────────────────────────────────


def test_submit_mesh_metrics(client, auth_headers):
    """Submit mesh session metrics."""
    res = client.post(
        "/mesh/metrics",
        json={
            "messages_sent": 10,
            "messages_received": 15,
            "messages_relayed": 5,
            "reconnect_attempts": 2,
            "reconnect_successes": 1,
            "peak_peer_count": 3,
            "acks_sent": 8,
            "acks_received": 6,
            "errors": 1,
            "session_duration_ms": 300000,
        },
        headers=auth_headers,
    )
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_submit_mesh_metrics_requires_auth(client):
    """Metrics endpoint requires authentication."""
    res = client.post("/mesh/metrics", json={})
    assert res.status_code == 403
