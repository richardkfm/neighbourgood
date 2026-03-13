"""Tests for community events endpoints."""

import datetime


def _register(client, email, name="User"):
    res = client.post(
        "/auth/register",
        json={"email": email, "password": "Password123", "display_name": name},
    )
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _future():
    return (datetime.datetime.utcnow() + datetime.timedelta(days=7)).isoformat()


def _past():
    return (datetime.datetime.utcnow() - datetime.timedelta(days=1)).isoformat()


# ── Categories ─────────────────────────────────────────────────────


def test_list_event_categories(client):
    res = client.get("/events/categories")
    assert res.status_code == 200
    cats = res.json()
    values = [c["value"] for c in cats]
    assert "meetup" in values
    assert "repair_cafe" in values
    assert "workshop" in values
    assert all("label" in c and "icon" in c for c in cats)


# ── List ───────────────────────────────────────────────────────────


def test_list_events_empty(client):
    res = client.get("/events")
    assert res.status_code == 200
    data = res.json()
    assert data["items"] == []
    assert data["total"] == 0


# ── CRUD ───────────────────────────────────────────────────────────


def test_create_event(client, auth_headers, community_id):
    res = client.post(
        "/events",
        headers=auth_headers,
        json={
            "title": "Repair Café",
            "description": "Bring your broken stuff!",
            "category": "repair_cafe",
            "start_at": _future(),
            "location": "Community Hall",
            "community_id": community_id,
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["title"] == "Repair Café"
    assert data["category"] == "repair_cafe"
    assert data["location"] == "Community Hall"
    assert data["attendee_count"] == 0
    assert data["is_attending"] is False
    assert "organizer" in data


def test_create_event_requires_auth(client, community_id):
    res = client.post(
        "/events",
        json={"title": "Test", "category": "meetup", "start_at": _future(), "community_id": community_id},
    )
    assert res.status_code == 403


def test_create_event_invalid_category(client, auth_headers, community_id):
    res = client.post(
        "/events",
        headers=auth_headers,
        json={"title": "X", "category": "nonexistent", "start_at": _future(), "community_id": community_id},
    )
    assert res.status_code == 422


def test_create_event_non_member_forbidden(client, community_id):
    other = _register(client, "outsider@test.com", "Outsider")
    res = client.post(
        "/events",
        headers=other,
        json={"title": "Test", "category": "meetup", "start_at": _future(), "community_id": community_id},
    )
    assert res.status_code == 403


def test_get_event(client, auth_headers, community_id):
    create = client.post(
        "/events",
        headers=auth_headers,
        json={"title": "Seed Swap", "category": "swap", "start_at": _future(), "community_id": community_id},
    )
    event_id = create.json()["id"]

    res = client.get(f"/events/{event_id}")
    assert res.status_code == 200
    assert res.json()["title"] == "Seed Swap"


def test_get_event_not_found(client):
    res = client.get("/events/999999")
    assert res.status_code == 404


def test_update_event(client, auth_headers, community_id):
    create = client.post(
        "/events",
        headers=auth_headers,
        json={"title": "Old Title", "category": "meetup", "start_at": _future(), "community_id": community_id},
    )
    event_id = create.json()["id"]

    res = client.patch(
        f"/events/{event_id}",
        headers=auth_headers,
        json={"title": "New Title", "location": "Park"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["title"] == "New Title"
    assert data["location"] == "Park"


def test_update_event_invalid_category(client, auth_headers, community_id):
    create = client.post(
        "/events",
        headers=auth_headers,
        json={"title": "Test", "category": "meetup", "start_at": _future(), "community_id": community_id},
    )
    event_id = create.json()["id"]

    res = client.patch(f"/events/{event_id}", headers=auth_headers, json={"category": "bad"})
    assert res.status_code == 422


def test_update_event_not_organizer(client, auth_headers, community_id):
    create = client.post(
        "/events",
        headers=auth_headers,
        json={"title": "Protected", "category": "food", "start_at": _future(), "community_id": community_id},
    )
    event_id = create.json()["id"]

    other = _register(client, "interloper@test.com", "Interloper")
    res = client.patch(f"/events/{event_id}", headers=other, json={"title": "Stolen"})
    assert res.status_code == 403


def test_delete_event(client, auth_headers, community_id):
    create = client.post(
        "/events",
        headers=auth_headers,
        json={"title": "To Delete", "category": "other", "start_at": _future(), "community_id": community_id},
    )
    event_id = create.json()["id"]

    res = client.delete(f"/events/{event_id}", headers=auth_headers)
    assert res.status_code == 204

    res = client.get(f"/events/{event_id}")
    assert res.status_code == 404


def test_delete_event_not_organizer(client, auth_headers, community_id):
    create = client.post(
        "/events",
        headers=auth_headers,
        json={"title": "Mine", "category": "sport", "start_at": _future(), "community_id": community_id},
    )
    event_id = create.json()["id"]

    other = _register(client, "thief@test.com", "Thief")
    res = client.delete(f"/events/{event_id}", headers=other)
    assert res.status_code == 403


# ── RSVP ──────────────────────────────────────────────────────────


def test_attend_event(client, auth_headers, community_id):
    create = client.post(
        "/events",
        headers=auth_headers,
        json={"title": "Workshop", "category": "workshop", "start_at": _future(), "community_id": community_id},
    )
    event_id = create.json()["id"]

    res = client.post(f"/events/{event_id}/attend", headers=auth_headers)
    assert res.status_code == 201
    data = res.json()
    assert data["attendee_count"] == 1
    assert data["is_attending"] is True


def test_attend_event_duplicate(client, auth_headers, community_id):
    create = client.post(
        "/events",
        headers=auth_headers,
        json={"title": "Workshop 2", "category": "workshop", "start_at": _future(), "community_id": community_id},
    )
    event_id = create.json()["id"]

    client.post(f"/events/{event_id}/attend", headers=auth_headers)
    res = client.post(f"/events/{event_id}/attend", headers=auth_headers)
    assert res.status_code == 409


def test_attend_event_full(client, auth_headers, community_id):
    create = client.post(
        "/events",
        headers=auth_headers,
        json={
            "title": "Tiny Event",
            "category": "cultural",
            "start_at": _future(),
            "max_attendees": 1,
            "community_id": community_id,
        },
    )
    event_id = create.json()["id"]

    # First user attends
    client.post(f"/events/{event_id}/attend", headers=auth_headers)

    # Second user tries to attend — event full
    other = _register(client, "latecomer@test.com", "Latecomer")
    res = client.post(f"/events/{event_id}/attend", headers=other)
    assert res.status_code == 409


def test_unattend_event(client, auth_headers, community_id):
    create = client.post(
        "/events",
        headers=auth_headers,
        json={"title": "Garden Day", "category": "gardening", "start_at": _future(), "community_id": community_id},
    )
    event_id = create.json()["id"]

    client.post(f"/events/{event_id}/attend", headers=auth_headers)
    res = client.delete(f"/events/{event_id}/attend", headers=auth_headers)
    assert res.status_code == 204

    event = client.get(f"/events/{event_id}").json()
    assert event["attendee_count"] == 0


def test_unattend_not_attending(client, auth_headers, community_id):
    create = client.post(
        "/events",
        headers=auth_headers,
        json={"title": "Food Fest", "category": "food", "start_at": _future(), "community_id": community_id},
    )
    event_id = create.json()["id"]

    res = client.delete(f"/events/{event_id}/attend", headers=auth_headers)
    assert res.status_code == 404


# ── Filters ────────────────────────────────────────────────────────


def test_filter_by_category(client, auth_headers, community_id):
    client.post("/events", headers=auth_headers, json={
        "title": "Meetup", "category": "meetup", "start_at": _future(), "community_id": community_id,
    })
    client.post("/events", headers=auth_headers, json={
        "title": "Workshop", "category": "workshop", "start_at": _future(), "community_id": community_id,
    })

    res = client.get(f"/events?category=meetup&community_id={community_id}")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert data["items"][0]["category"] == "meetup"


def test_filter_upcoming(client, auth_headers, community_id):
    client.post("/events", headers=auth_headers, json={
        "title": "Past Event", "category": "other", "start_at": _past(), "community_id": community_id,
    })
    client.post("/events", headers=auth_headers, json={
        "title": "Future Event", "category": "other", "start_at": _future(), "community_id": community_id,
    })

    res = client.get(f"/events?upcoming=true&community_id={community_id}")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "Future Event"


def test_search_events(client, auth_headers, community_id):
    client.post("/events", headers=auth_headers, json={
        "title": "Python Workshop", "category": "workshop", "start_at": _future(), "community_id": community_id,
    })
    client.post("/events", headers=auth_headers, json={
        "title": "Salsa Night", "category": "cultural", "start_at": _future(), "community_id": community_id,
    })

    res = client.get(f"/events?q=python&community_id={community_id}")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert "Python" in data["items"][0]["title"]


def test_filter_by_community(client, auth_headers, community_id):
    # Create a second community
    res2 = client.post(
        "/communities",
        headers=auth_headers,
        json={"name": "Other Community", "postal_code": "99999", "city": "Anderstadt"},
    )
    other_community_id = res2.json()["id"]

    client.post("/events", headers=auth_headers, json={
        "title": "Event A", "category": "meetup", "start_at": _future(), "community_id": community_id,
    })
    client.post("/events", headers=auth_headers, json={
        "title": "Event B", "category": "meetup", "start_at": _future(), "community_id": other_community_id,
    })

    res = client.get(f"/events?community_id={community_id}")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "Event A"
