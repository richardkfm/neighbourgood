"""Tests for Red Sky (crisis) mode: toggle, voting, emergency tickets, leaders."""


def _register(client, email, name="User"):
    """Helper: register a user and return auth headers."""
    res = client.post(
        "/auth/register",
        json={"email": email, "password": "Password123", "display_name": name},
    )
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _create_community(client, headers, name="Test Community", plz="10115", city="Berlin"):
    """Helper: create a community and return its data."""
    res = client.post(
        "/communities",
        headers=headers,
        json={"name": name, "postal_code": plz, "city": city},
    )
    return res.json()


# ── Crisis mode toggle (admin) ────────────────────────────────────


def test_admin_toggle_crisis_mode(client, auth_headers):
    c = _create_community(client, auth_headers)
    cid = c["id"]

    # Initially blue
    res = client.get(f"/communities/{cid}/crisis/status")
    assert res.status_code == 200
    assert res.json()["mode"] == "blue"

    # Toggle to red
    res = client.post(
        f"/communities/{cid}/crisis/toggle",
        headers=auth_headers,
        json={"mode": "red"},
    )
    assert res.status_code == 200
    assert res.json()["mode"] == "red"

    # Toggle back to blue
    res = client.post(
        f"/communities/{cid}/crisis/toggle",
        headers=auth_headers,
        json={"mode": "blue"},
    )
    assert res.status_code == 200
    assert res.json()["mode"] == "blue"


def test_toggle_requires_admin(client, auth_headers):
    c = _create_community(client, auth_headers)
    cid = c["id"]

    other = _register(client, "member@test.com", "Member")
    client.post(f"/communities/{cid}/join", headers=other)

    res = client.post(
        f"/communities/{cid}/crisis/toggle",
        headers=other,
        json={"mode": "red"},
    )
    assert res.status_code == 403


def test_toggle_invalid_mode(client, auth_headers):
    c = _create_community(client, auth_headers)
    res = client.post(
        f"/communities/{c['id']}/crisis/toggle",
        headers=auth_headers,
        json={"mode": "purple"},
    )
    assert res.status_code == 422


def test_toggle_clears_votes(client, auth_headers):
    c = _create_community(client, auth_headers)
    cid = c["id"]

    # Add a second member so the threshold isn't 1/1
    other = _register(client, "member@test.com", "Member")
    client.post(f"/communities/{cid}/join", headers=other)

    # Cast a vote (with 2 members, threshold is 2, so 1 vote won't trigger auto-switch)
    client.post(
        f"/communities/{cid}/crisis/vote",
        headers=auth_headers,
        json={"vote_type": "activate"},
    )

    # Verify vote exists
    res = client.get(f"/communities/{cid}/crisis/status")
    assert res.json()["votes_to_activate"] == 1

    # Admin toggle clears votes
    client.post(
        f"/communities/{cid}/crisis/toggle",
        headers=auth_headers,
        json={"mode": "red"},
    )
    res = client.get(f"/communities/{cid}/crisis/status")
    assert res.json()["votes_to_activate"] == 0
    assert res.json()["votes_to_deactivate"] == 0


# ── Crisis mode voting ────────────────────────────────────────────


def test_cast_vote(client, auth_headers):
    c = _create_community(client, auth_headers)
    cid = c["id"]

    res = client.post(
        f"/communities/{cid}/crisis/vote",
        headers=auth_headers,
        json={"vote_type": "activate"},
    )
    assert res.status_code == 200
    assert res.json()["vote_type"] == "activate"


def test_duplicate_vote_rejected(client, auth_headers):
    c = _create_community(client, auth_headers)
    cid = c["id"]

    # Add a second member so threshold isn't met with 1 vote
    other = _register(client, "m2@test.com", "M2")
    client.post(f"/communities/{cid}/join", headers=other)

    client.post(
        f"/communities/{cid}/crisis/vote",
        headers=auth_headers,
        json={"vote_type": "activate"},
    )
    res = client.post(
        f"/communities/{cid}/crisis/vote",
        headers=auth_headers,
        json={"vote_type": "activate"},
    )
    assert res.status_code == 409


def test_change_vote_to_noop_rejected(client, auth_headers):
    c = _create_community(client, auth_headers)
    cid = c["id"]

    # Add a second member so threshold isn't met with 1 vote
    other = _register(client, "m2@test.com", "M2")
    client.post(f"/communities/{cid}/join", headers=other)

    client.post(
        f"/communities/{cid}/crisis/vote",
        headers=auth_headers,
        json={"vote_type": "activate"},
    )
    res = client.post(
        f"/communities/{cid}/crisis/vote",
        headers=auth_headers,
        json={"vote_type": "deactivate"},
    )
    # While blue, "deactivate" is a no-op vote: 409, and the earlier vote stays
    assert res.status_code == 409
    assert client.get(f"/communities/{cid}/crisis/status").json()["votes_to_activate"] == 1


def test_retract_vote(client, auth_headers):
    c = _create_community(client, auth_headers)
    cid = c["id"]

    # Add a second member so threshold isn't met with 1 vote
    other = _register(client, "m2@test.com", "M2")
    client.post(f"/communities/{cid}/join", headers=other)

    client.post(
        f"/communities/{cid}/crisis/vote",
        headers=auth_headers,
        json={"vote_type": "activate"},
    )
    res = client.delete(f"/communities/{cid}/crisis/vote", headers=auth_headers)
    assert res.status_code == 204

    # Verify vote gone
    status = client.get(f"/communities/{cid}/crisis/status").json()
    assert status["votes_to_activate"] == 0


def test_retract_nonexistent_vote(client, auth_headers):
    c = _create_community(client, auth_headers)
    res = client.delete(f"/communities/{c['id']}/crisis/vote", headers=auth_headers)
    assert res.status_code == 404


def test_vote_requires_membership(client, auth_headers):
    c = _create_community(client, auth_headers)
    outsider = _register(client, "outsider@test.com", "Outsider")

    res = client.post(
        f"/communities/{c['id']}/crisis/vote",
        headers=outsider,
        json={"vote_type": "activate"},
    )
    assert res.status_code == 403


def test_vote_threshold_triggers_mode_switch(client, auth_headers):
    """When 60% of members vote to activate, mode auto-switches to red."""
    c = _create_community(client, auth_headers)
    cid = c["id"]

    # 1 member (admin), threshold = ceil(1 * 60 / 100) = 1
    # A single vote from the only member should trigger
    client.post(
        f"/communities/{cid}/crisis/vote",
        headers=auth_headers,
        json={"vote_type": "activate"},
    )

    status = client.get(f"/communities/{cid}/crisis/status").json()
    assert status["mode"] == "red"
    # Votes should be cleared after switch
    assert status["votes_to_activate"] == 0


def test_threshold_crossing_logs_activity_once(client, auth_headers, db):
    """Crossing the vote threshold must log exactly one crisis_mode_changed activity.

    Regression guard for the race condition where two concurrent voters could
    each cross the threshold and double-log the mode switch.
    """
    from app.models.activity import Activity

    c = _create_community(client, auth_headers)
    cid = c["id"]

    res = client.post(
        f"/communities/{cid}/crisis/vote",
        headers=auth_headers,
        json={"vote_type": "activate"},
    )
    assert res.status_code == 200

    activities = (
        db.query(Activity)
        .filter(
            Activity.community_id == cid,
            Activity.event_type == "crisis_mode_changed",
        )
        .all()
    )
    assert len(activities) == 1, f"expected one mode-change activity, got {len(activities)}"


# ── Emergency tickets ─────────────────────────────────────────────


def test_create_ticket(client, auth_headers):
    c = _create_community(client, auth_headers)
    cid = c["id"]

    res = client.post(
        f"/communities/{cid}/tickets",
        headers=auth_headers,
        json={
            "ticket_type": "request",
            "title": "Need water",
            "description": "Running low on drinking water",
            "urgency": "high",
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["title"] == "Need water"
    assert data["ticket_type"] == "request"
    assert data["urgency"] == "high"
    assert data["status"] == "open"


def test_create_ticket_requires_membership(client, auth_headers):
    c = _create_community(client, auth_headers)
    outsider = _register(client, "outsider@test.com", "Outsider")

    res = client.post(
        f"/communities/{c['id']}/tickets",
        headers=outsider,
        json={"ticket_type": "request", "title": "Help"},
    )
    assert res.status_code == 403


def test_create_offer_ticket(client, auth_headers):
    c = _create_community(client, auth_headers)
    res = client.post(
        f"/communities/{c['id']}/tickets",
        headers=auth_headers,
        json={"ticket_type": "offer", "title": "I have extra blankets"},
    )
    assert res.status_code == 201
    assert res.json()["ticket_type"] == "offer"


def test_emergency_ping_requires_crisis_mode(client, auth_headers):
    c = _create_community(client, auth_headers)
    # Community is in blue mode by default
    res = client.post(
        f"/communities/{c['id']}/tickets",
        headers=auth_headers,
        json={"ticket_type": "emergency_ping", "title": "SOS"},
    )
    assert res.status_code == 422
    assert "Red Sky" in res.json()["detail"]


def test_emergency_ping_allowed_in_crisis_mode(client, auth_headers):
    c = _create_community(client, auth_headers)
    cid = c["id"]

    # Activate crisis mode
    client.post(
        f"/communities/{cid}/crisis/toggle",
        headers=auth_headers,
        json={"mode": "red"},
    )

    res = client.post(
        f"/communities/{cid}/tickets",
        headers=auth_headers,
        json={"ticket_type": "emergency_ping", "title": "SOS - trapped"},
    )
    assert res.status_code == 201
    assert res.json()["ticket_type"] == "emergency_ping"


def test_list_tickets(client, auth_headers):
    c = _create_community(client, auth_headers)
    cid = c["id"]

    client.post(
        f"/communities/{cid}/tickets",
        headers=auth_headers,
        json={"ticket_type": "request", "title": "Need food"},
    )
    client.post(
        f"/communities/{cid}/tickets",
        headers=auth_headers,
        json={"ticket_type": "offer", "title": "Have blankets"},
    )

    res = client.get(f"/communities/{cid}/tickets", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2


def test_list_tickets_filter_by_type(client, auth_headers):
    c = _create_community(client, auth_headers)
    cid = c["id"]

    client.post(
        f"/communities/{cid}/tickets",
        headers=auth_headers,
        json={"ticket_type": "request", "title": "Need food"},
    )
    client.post(
        f"/communities/{cid}/tickets",
        headers=auth_headers,
        json={"ticket_type": "offer", "title": "Have blankets"},
    )

    res = client.get(
        f"/communities/{cid}/tickets?ticket_type=request", headers=auth_headers
    )
    assert res.status_code == 200
    assert res.json()["total"] == 1
    assert res.json()["items"][0]["ticket_type"] == "request"


def test_update_ticket_status(client, auth_headers):
    c = _create_community(client, auth_headers)
    cid = c["id"]

    ticket = client.post(
        f"/communities/{cid}/tickets",
        headers=auth_headers,
        json={"ticket_type": "request", "title": "Need help"},
    ).json()

    res = client.patch(
        f"/communities/{cid}/tickets/{ticket['id']}",
        headers=auth_headers,
        json={"status": "in_progress"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "in_progress"


def test_update_ticket_by_non_author_non_admin(client, auth_headers):
    c = _create_community(client, auth_headers)
    cid = c["id"]

    ticket = client.post(
        f"/communities/{cid}/tickets",
        headers=auth_headers,
        json={"ticket_type": "request", "title": "Need help"},
    ).json()

    # Other member tries to update
    other = _register(client, "other@test.com", "Other")
    client.post(f"/communities/{cid}/join", headers=other)

    res = client.patch(
        f"/communities/{cid}/tickets/{ticket['id']}",
        headers=other,
        json={"status": "resolved"},
    )
    assert res.status_code == 403


def test_get_single_ticket(client, auth_headers):
    c = _create_community(client, auth_headers)
    cid = c["id"]

    ticket = client.post(
        f"/communities/{cid}/tickets",
        headers=auth_headers,
        json={"ticket_type": "offer", "title": "I have a generator"},
    ).json()

    res = client.get(
        f"/communities/{cid}/tickets/{ticket['id']}", headers=auth_headers
    )
    assert res.status_code == 200
    assert res.json()["title"] == "I have a generator"


# ── Leader management ─────────────────────────────────────────────


def test_promote_to_leader(client, auth_headers):
    c = _create_community(client, auth_headers)
    cid = c["id"]

    other = _register(client, "member@test.com", "Member")
    client.post(f"/communities/{cid}/join", headers=other)

    # Get member's user ID
    members = client.get(f"/communities/{cid}/members").json()
    member_user_id = [m for m in members if m["role"] == "member"][0]["user"]["id"]

    res = client.post(
        f"/communities/{cid}/leaders/{member_user_id}", headers=auth_headers
    )
    assert res.status_code == 200
    assert res.json()["role"] == "leader"


def test_promote_requires_admin(client, auth_headers):
    c = _create_community(client, auth_headers)
    cid = c["id"]

    member1 = _register(client, "m1@test.com", "M1")
    client.post(f"/communities/{cid}/join", headers=member1)
    member2 = _register(client, "m2@test.com", "M2")
    client.post(f"/communities/{cid}/join", headers=member2)

    members = client.get(f"/communities/{cid}/members").json()
    m2_id = [m for m in members if m["user"]["display_name"] == "M2"][0]["user"]["id"]

    # Member trying to promote another member
    res = client.post(f"/communities/{cid}/leaders/{m2_id}", headers=member1)
    assert res.status_code == 403


def test_promote_admin_fails(client, auth_headers):
    c = _create_community(client, auth_headers)
    cid = c["id"]

    members = client.get(f"/communities/{cid}/members").json()
    admin_id = members[0]["user"]["id"]

    res = client.post(f"/communities/{cid}/leaders/{admin_id}", headers=auth_headers)
    assert res.status_code == 422


def test_promote_already_leader_fails(client, auth_headers):
    c = _create_community(client, auth_headers)
    cid = c["id"]

    other = _register(client, "member@test.com", "Member")
    client.post(f"/communities/{cid}/join", headers=other)

    members = client.get(f"/communities/{cid}/members").json()
    member_id = [m for m in members if m["role"] == "member"][0]["user"]["id"]

    # Promote once
    client.post(f"/communities/{cid}/leaders/{member_id}", headers=auth_headers)
    # Promote again
    res = client.post(f"/communities/{cid}/leaders/{member_id}", headers=auth_headers)
    assert res.status_code == 409


def test_demote_leader(client, auth_headers):
    c = _create_community(client, auth_headers)
    cid = c["id"]

    other = _register(client, "member@test.com", "Member")
    client.post(f"/communities/{cid}/join", headers=other)

    members = client.get(f"/communities/{cid}/members").json()
    member_id = [m for m in members if m["role"] == "member"][0]["user"]["id"]

    # Promote then demote
    client.post(f"/communities/{cid}/leaders/{member_id}", headers=auth_headers)
    res = client.delete(f"/communities/{cid}/leaders/{member_id}", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["role"] == "member"


def test_demote_non_leader_fails(client, auth_headers):
    c = _create_community(client, auth_headers)
    cid = c["id"]

    other = _register(client, "member@test.com", "Member")
    client.post(f"/communities/{cid}/join", headers=other)

    members = client.get(f"/communities/{cid}/members").json()
    member_id = [m for m in members if m["role"] == "member"][0]["user"]["id"]

    res = client.delete(
        f"/communities/{cid}/leaders/{member_id}", headers=auth_headers
    )
    assert res.status_code == 422


def test_list_leaders(client, auth_headers):
    c = _create_community(client, auth_headers)
    cid = c["id"]

    m1 = _register(client, "m1@test.com", "Leader1")
    client.post(f"/communities/{cid}/join", headers=m1)
    m2 = _register(client, "m2@test.com", "Leader2")
    client.post(f"/communities/{cid}/join", headers=m2)

    members = client.get(f"/communities/{cid}/members").json()
    member_ids = [m["user"]["id"] for m in members if m["role"] == "member"]

    for uid in member_ids:
        client.post(f"/communities/{cid}/leaders/{uid}", headers=auth_headers)

    res = client.get(f"/communities/{cid}/leaders", headers=auth_headers)
    assert res.status_code == 200
    leaders = res.json()
    assert len(leaders) == 2
    assert all(l["role"] == "leader" for l in leaders)


def test_leader_can_update_ticket(client, auth_headers):
    """Leaders should be able to update tickets created by other members."""
    c = _create_community(client, auth_headers)
    cid = c["id"]

    member = _register(client, "member@test.com", "Member")
    client.post(f"/communities/{cid}/join", headers=member)

    leader = _register(client, "leader@test.com", "Leader")
    client.post(f"/communities/{cid}/join", headers=leader)

    # Promote leader
    members = client.get(f"/communities/{cid}/members").json()
    leader_uid = [m for m in members if m["user"]["display_name"] == "Leader"][0][
        "user"
    ]["id"]
    client.post(f"/communities/{cid}/leaders/{leader_uid}", headers=auth_headers)

    # Member creates a ticket
    ticket = client.post(
        f"/communities/{cid}/tickets",
        headers=member,
        json={"ticket_type": "request", "title": "Need help"},
    ).json()

    # Leader updates the ticket
    res = client.patch(
        f"/communities/{cid}/tickets/{ticket['id']}",
        headers=leader,
        json={"status": "in_progress"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "in_progress"


# ── Map endpoint ──────────────────────────────────────────────────


def test_communities_map_endpoint(client, auth_headers):
    _create_community(client, auth_headers, name="Group A", plz="10115", city="Berlin")
    _create_community(client, auth_headers, name="Group B", plz="80331", city="Munich")

    res = client.get("/communities/map")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 2
    assert all("name" in c and "city" in c for c in data)


def test_map_excludes_merged(client, auth_headers):
    a = _create_community(client, auth_headers, name="Old", plz="10115", city="Berlin")
    b = _create_community(client, auth_headers, name="New", plz="10115", city="Berlin")

    client.post(
        "/communities/merge",
        headers=auth_headers,
        json={"source_id": a["id"], "target_id": b["id"]},
    )

    res = client.get("/communities/map")
    assert len(res.json()) == 1
    assert res.json()[0]["name"] == "New"


def test_community_mode_in_response(client, auth_headers):
    c = _create_community(client, auth_headers)
    res = client.get(f"/communities/{c['id']}")
    assert res.status_code == 200
    assert res.json()["mode"] == "blue"


# ── Ticket comments ───────────────────────────────────────────────


def test_create_ticket_comment(client, auth_headers):
    c = _create_community(client, auth_headers)
    cid = c["id"]

    ticket = client.post(
        f"/communities/{cid}/tickets",
        headers=auth_headers,
        json={"ticket_type": "request", "title": "Need water", "urgency": "high"},
    ).json()
    tid = ticket["id"]

    res = client.post(
        f"/communities/{cid}/tickets/{tid}/comments",
        headers=auth_headers,
        json={"body": "I can help!"},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["body"] == "I can help!"
    assert "author" in data


def test_list_ticket_comments(client, auth_headers):
    c = _create_community(client, auth_headers)
    cid = c["id"]

    ticket = client.post(
        f"/communities/{cid}/tickets",
        headers=auth_headers,
        json={"ticket_type": "request", "title": "Need water", "urgency": "high"},
    ).json()
    tid = ticket["id"]

    client.post(
        f"/communities/{cid}/tickets/{tid}/comments",
        headers=auth_headers,
        json={"body": "First comment"},
    )
    client.post(
        f"/communities/{cid}/tickets/{tid}/comments",
        headers=auth_headers,
        json={"body": "Second comment"},
    )

    res = client.get(
        f"/communities/{cid}/tickets/{tid}/comments",
        headers=auth_headers,
    )
    assert res.status_code == 200
    items = res.json()
    assert len(items) == 2
    assert items[0]["body"] == "First comment"
    assert items[1]["body"] == "Second comment"


def test_comment_requires_membership(client, auth_headers):
    c = _create_community(client, auth_headers)
    cid = c["id"]

    ticket = client.post(
        f"/communities/{cid}/tickets",
        headers=auth_headers,
        json={"ticket_type": "request", "title": "Need water", "urgency": "high"},
    ).json()
    tid = ticket["id"]

    outsider = _register(client, "outsider@test.com", "Outsider")
    res = client.post(
        f"/communities/{cid}/tickets/{tid}/comments",
        headers=outsider,
        json={"body": "I can help!"},
    )
    assert res.status_code == 403


def test_comment_on_nonexistent_ticket(client, auth_headers):
    c = _create_community(client, auth_headers)
    cid = c["id"]

    res = client.post(
        f"/communities/{cid}/tickets/99999/comments",
        headers=auth_headers,
        json={"body": "I can help!"},
    )
    assert res.status_code == 404


def test_comment_body_required(client, auth_headers):
    c = _create_community(client, auth_headers)
    cid = c["id"]

    ticket = client.post(
        f"/communities/{cid}/tickets",
        headers=auth_headers,
        json={"ticket_type": "request", "title": "Need water", "urgency": "high"},
    ).json()
    tid = ticket["id"]

    res = client.post(
        f"/communities/{cid}/tickets/{tid}/comments",
        headers=auth_headers,
        json={"body": ""},
    )
    assert res.status_code == 422
