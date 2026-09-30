"""Tests for community activity feed endpoints."""


def _register(client, email, name="User"):
    res = client.post(
        "/auth/register",
        json={"email": email, "password": "Password123", "display_name": name},
    )
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _create_community(client, headers, name="Test Community"):
    res = client.post(
        "/communities",
        headers=headers,
        json={"name": name, "postal_code": "12345", "city": "Teststadt"},
    )
    return res.json()["id"]


# ── Feed basics ────────────────────────────────────────────────────


def test_empty_feed(client):
    """Empty feed returns zero items."""
    res = client.get("/activity")
    assert res.status_code == 200
    data = res.json()
    assert data["items"] == []
    assert data["total"] == 0


def test_resource_creates_activity(client, auth_headers, community_id):
    """Sharing a resource generates a resource_shared event."""
    client.post(
        "/resources",
        headers=auth_headers,
        json={"title": "Drill", "category": "tool", "community_id": community_id},
    )
    res = client.get("/activity")
    data = res.json()
    assert data["total"] == 1
    assert data["items"][0]["event_type"] == "resource_shared"
    assert "Drill" in data["items"][0]["summary"]


def test_skill_offer_creates_activity(client, auth_headers, community_id):
    """Offering a skill generates a skill_offered event."""
    client.post(
        "/skills",
        headers=auth_headers,
        json={"title": "Piano Lessons", "category": "music", "skill_type": "offer", "community_id": community_id},
    )
    res = client.get("/activity")
    data = res.json()
    events = [e for e in data["items"] if e["event_type"] == "skill_offered"]
    assert len(events) == 1
    assert "Piano" in events[0]["summary"]


def test_skill_request_creates_activity(client, auth_headers, community_id):
    """Requesting a skill generates a skill_requested event."""
    client.post(
        "/skills",
        headers=auth_headers,
        json={"title": "Need cooking help", "category": "cooking", "skill_type": "request", "community_id": community_id},
    )
    res = client.get("/activity")
    data = res.json()
    events = [e for e in data["items"] if e["event_type"] == "skill_requested"]
    assert len(events) == 1


def test_booking_creates_activity(client, auth_headers, community_id):
    """Creating a booking generates a resource_borrowed event."""
    borrower = _register(client, "borrower@test.com", "Borrower")
    r = client.post(
        "/resources", headers=auth_headers,
        json={"title": "Ladder", "category": "tool", "community_id": community_id},
    )
    resource_id = r.json()["id"]

    client.post(
        "/bookings",
        headers=borrower,
        json={
            "resource_id": resource_id,
            "start_date": "2026-04-01",
            "end_date": "2026-04-05",
        },
    )

    res = client.get("/activity")
    events = [e for e in res.json()["items"] if e["event_type"] == "resource_borrowed"]
    assert len(events) == 1
    assert "Ladder" in events[0]["summary"]


def test_completed_booking_creates_activity(client, auth_headers, community_id):
    """Completing a booking generates a booking_completed event."""
    borrower = _register(client, "borrower@test.com", "Borrower")
    r = client.post(
        "/resources", headers=auth_headers,
        json={"title": "Drill", "category": "tool", "community_id": community_id},
    )
    resource_id = r.json()["id"]

    b = client.post(
        "/bookings", headers=borrower,
        json={"resource_id": resource_id, "start_date": "2026-04-01", "end_date": "2026-04-05"},
    )
    booking_id = b.json()["id"]

    client.patch(f"/bookings/{booking_id}", headers=auth_headers, json={"status": "approved"})
    client.patch(f"/bookings/{booking_id}", headers=borrower, json={"status": "completed"})

    res = client.get("/activity")
    events = [e for e in res.json()["items"] if e["event_type"] == "booking_completed"]
    assert len(events) == 1


def test_join_community_creates_activity(client, auth_headers):
    """Joining a community generates a member_joined event."""
    community_id = _create_community(client, auth_headers)
    joiner = _register(client, "joiner@test.com", "Joiner")

    client.post(f"/communities/{community_id}/join", headers=joiner)

    res = client.get("/activity?community_id=" + str(community_id))
    events = [e for e in res.json()["items"] if e["event_type"] == "member_joined"]
    assert len(events) == 1
    assert "Joiner" in events[0]["actor"]["display_name"]


# ── Filtering ──────────────────────────────────────────────────────


def test_filter_by_community(client, auth_headers):
    """Activity can be filtered by community_id."""
    community_id = _create_community(client, auth_headers)
    second_community_id = _create_community(client, auth_headers, name="Second Community")
    client.post(
        "/resources", headers=auth_headers,
        json={"title": "Community Drill", "category": "tool", "community_id": community_id},
    )
    client.post(
        "/resources", headers=auth_headers,
        json={"title": "Personal Saw", "category": "tool", "community_id": second_community_id},
    )

    all_activity = client.get("/activity")
    assert all_activity.json()["total"] >= 2

    community_activity = client.get(f"/activity?community_id={community_id}")
    items = community_activity.json()["items"]
    assert all(
        e["community_id"] == community_id
        for e in items
        if e["event_type"] != "member_joined"  # community create auto-joins
    )


def test_my_activity(client, auth_headers, community_id):
    """The /my endpoint returns only the current user's activity."""
    other = _register(client, "other@test.com", "Other")
    other_community_id = _create_community(client, other, name="Other Community")
    client.post(
        "/resources", headers=auth_headers,
        json={"title": "My Drill", "category": "tool", "community_id": community_id},
    )
    client.post(
        "/resources", headers=other,
        json={"title": "Other Drill", "category": "tool", "community_id": other_community_id},
    )

    res = client.get("/activity/my", headers=auth_headers)
    assert res.status_code == 200
    assert all(e["actor"]["display_name"] == "Test User" for e in res.json()["items"])


def test_my_activity_requires_auth(client):
    """The /my endpoint requires authentication."""
    res = client.get("/activity/my")
    assert res.status_code == 403
