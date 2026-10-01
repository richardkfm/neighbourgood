"""Tests for booking endpoints: create, list, status transitions, calendar, conflicts."""


def _create_community(client, headers, name="Test Community"):
    res = client.post(
        "/communities",
        headers=headers,
        json={"name": name, "postal_code": "12345", "city": "Teststadt"},
    )
    return res.json()["id"]


def _create_resource(client, headers, community_id, title="Shared Drill"):
    """Helper: create a resource and return its ID."""
    res = client.post(
        "/resources",
        headers=headers,
        json={"title": title, "category": "tool", "community_id": community_id},
    )
    return res.json()["id"]


def _register(client, email, name="User", community_id=None):
    """Helper: register a user (optionally joining a community) and return auth headers."""
    res = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "Password123",
            "display_name": name,
        },
    )
    headers = {"Authorization": f"Bearer {res.json()['access_token']}"}
    if community_id is not None:
        assert client.post(f"/communities/{community_id}/join", headers=headers).status_code == 200
    return headers


# ── Create booking ──────────────────────────────────────────────────


def test_create_booking(client, auth_headers):
    cid = _create_community(client, auth_headers)
    borrower_headers = _register(client, "borrower@test.com", "Borrower", cid)
    resource_id = _create_resource(client, auth_headers, cid)

    res = client.post(
        "/bookings",
        headers=borrower_headers,
        json={
            "resource_id": resource_id,
            "start_date": "2099-03-01",
            "end_date": "2099-03-05",
            "message": "Can I borrow this?",
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["resource_id"] == resource_id
    assert data["status"] == "pending"
    assert data["message"] == "Can I borrow this?"
    assert data["start_date"] == "2099-03-01"
    assert data["end_date"] == "2099-03-05"


def test_create_booking_invalid_dates(client, auth_headers):
    cid = _create_community(client, auth_headers)
    borrower_headers = _register(client, "borrower@test.com", "Borrower", cid)
    resource_id = _create_resource(client, auth_headers, cid)

    res = client.post(
        "/bookings",
        headers=borrower_headers,
        json={
            "resource_id": resource_id,
            "start_date": "2099-03-10",
            "end_date": "2099-03-05",
        },
    )
    assert res.status_code == 422


def test_cannot_book_own_resource(client, auth_headers):
    cid = _create_community(client, auth_headers)
    resource_id = _create_resource(client, auth_headers, cid)

    res = client.post(
        "/bookings",
        headers=auth_headers,
        json={
            "resource_id": resource_id,
            "start_date": "2099-03-01",
            "end_date": "2099-03-05",
        },
    )
    assert res.status_code == 409
    assert "own resource" in res.json()["detail"].lower()


def test_cannot_book_unavailable_resource(client, auth_headers):
    cid = _create_community(client, auth_headers)
    borrower_headers = _register(client, "borrower@test.com", "Borrower", cid)
    resource_id = _create_resource(client, auth_headers, cid)

    # Mark resource unavailable
    client.patch(
        f"/resources/{resource_id}",
        headers=auth_headers,
        json={"is_available": False},
    )

    res = client.post(
        "/bookings",
        headers=borrower_headers,
        json={
            "resource_id": resource_id,
            "start_date": "2099-03-01",
            "end_date": "2099-03-05",
        },
    )
    assert res.status_code == 409
    assert "not available" in res.json()["detail"].lower()


def test_booking_date_conflict(client, auth_headers):
    cid = _create_community(client, auth_headers)
    borrower1 = _register(client, "b1@test.com", "Borrower1", cid)
    borrower2 = _register(client, "b2@test.com", "Borrower2", cid)
    resource_id = _create_resource(client, auth_headers, cid)

    # First booking
    res = client.post(
        "/bookings",
        headers=borrower1,
        json={
            "resource_id": resource_id,
            "start_date": "2099-03-01",
            "end_date": "2099-03-10",
        },
    )
    assert res.status_code == 201

    # Overlapping booking should fail
    res = client.post(
        "/bookings",
        headers=borrower2,
        json={
            "resource_id": resource_id,
            "start_date": "2099-03-05",
            "end_date": "2099-03-15",
        },
    )
    assert res.status_code == 409
    assert "overlap" in res.json()["detail"].lower()


def test_booking_non_overlapping_dates_ok(client, auth_headers):
    cid = _create_community(client, auth_headers)
    borrower1 = _register(client, "b1@test.com", "Borrower1", cid)
    borrower2 = _register(client, "b2@test.com", "Borrower2", cid)
    resource_id = _create_resource(client, auth_headers, cid)

    res = client.post(
        "/bookings",
        headers=borrower1,
        json={
            "resource_id": resource_id,
            "start_date": "2099-03-01",
            "end_date": "2099-03-05",
        },
    )
    assert res.status_code == 201

    # Non-overlapping: after the first booking ends
    res = client.post(
        "/bookings",
        headers=borrower2,
        json={
            "resource_id": resource_id,
            "start_date": "2099-03-06",
            "end_date": "2099-03-10",
        },
    )
    assert res.status_code == 201


def test_booking_resource_not_found(client, auth_headers):
    res = client.post(
        "/bookings",
        headers=auth_headers,
        json={
            "resource_id": 9999,
            "start_date": "2099-03-01",
            "end_date": "2099-03-05",
        },
    )
    assert res.status_code == 404


def test_create_booking_requires_auth(client):
    res = client.post(
        "/bookings",
        json={
            "resource_id": 1,
            "start_date": "2099-03-01",
            "end_date": "2099-03-05",
        },
    )
    assert res.status_code == 403


# ── List bookings ───────────────────────────────────────────────────


def test_list_bookings_as_borrower(client, auth_headers):
    cid = _create_community(client, auth_headers)
    borrower_headers = _register(client, "borrower@test.com", "Borrower", cid)
    resource_id = _create_resource(client, auth_headers, cid)

    client.post(
        "/bookings",
        headers=borrower_headers,
        json={
            "resource_id": resource_id,
            "start_date": "2099-03-01",
            "end_date": "2099-03-05",
        },
    )

    res = client.get("/bookings?role=borrower", headers=borrower_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert data["items"][0]["resource_title"] == "Shared Drill"


def test_list_bookings_as_owner(client, auth_headers):
    cid = _create_community(client, auth_headers)
    borrower_headers = _register(client, "borrower@test.com", "Borrower", cid)
    resource_id = _create_resource(client, auth_headers, cid)

    client.post(
        "/bookings",
        headers=borrower_headers,
        json={
            "resource_id": resource_id,
            "start_date": "2099-03-01",
            "end_date": "2099-03-05",
        },
    )

    # Owner should see the incoming request
    res = client.get("/bookings?role=owner", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1


def test_list_bookings_status_filter(client, auth_headers):
    cid = _create_community(client, auth_headers)
    borrower_headers = _register(client, "borrower@test.com", "Borrower", cid)
    resource_id = _create_resource(client, auth_headers, cid)

    client.post(
        "/bookings",
        headers=borrower_headers,
        json={
            "resource_id": resource_id,
            "start_date": "2099-03-01",
            "end_date": "2099-03-05",
        },
    )

    # Filter by pending
    res = client.get("/bookings?status=pending", headers=borrower_headers)
    assert res.json()["total"] == 1

    # Filter by approved (should be empty)
    res = client.get("/bookings?status=approved", headers=borrower_headers)
    assert res.json()["total"] == 0


# ── Status transitions ──────────────────────────────────────────────


def test_owner_approves_booking(client, auth_headers):
    cid = _create_community(client, auth_headers)
    borrower_headers = _register(client, "borrower@test.com", "Borrower", cid)
    resource_id = _create_resource(client, auth_headers, cid)

    create_res = client.post(
        "/bookings",
        headers=borrower_headers,
        json={
            "resource_id": resource_id,
            "start_date": "2099-03-01",
            "end_date": "2099-03-05",
        },
    )
    booking_id = create_res.json()["id"]

    res = client.patch(
        f"/bookings/{booking_id}",
        headers=auth_headers,
        json={"status": "approved"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "approved"


def test_owner_rejects_booking(client, auth_headers):
    cid = _create_community(client, auth_headers)
    borrower_headers = _register(client, "borrower@test.com", "Borrower", cid)
    resource_id = _create_resource(client, auth_headers, cid)

    create_res = client.post(
        "/bookings",
        headers=borrower_headers,
        json={
            "resource_id": resource_id,
            "start_date": "2099-03-01",
            "end_date": "2099-03-05",
        },
    )
    booking_id = create_res.json()["id"]

    res = client.patch(
        f"/bookings/{booking_id}",
        headers=auth_headers,
        json={"status": "rejected"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "rejected"


def test_borrower_cancels_pending_booking(client, auth_headers):
    cid = _create_community(client, auth_headers)
    borrower_headers = _register(client, "borrower@test.com", "Borrower", cid)
    resource_id = _create_resource(client, auth_headers, cid)

    create_res = client.post(
        "/bookings",
        headers=borrower_headers,
        json={
            "resource_id": resource_id,
            "start_date": "2099-03-01",
            "end_date": "2099-03-05",
        },
    )
    booking_id = create_res.json()["id"]

    res = client.patch(
        f"/bookings/{booking_id}",
        headers=borrower_headers,
        json={"status": "cancelled"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "cancelled"


def test_borrower_cannot_approve(client, auth_headers):
    cid = _create_community(client, auth_headers)
    borrower_headers = _register(client, "borrower@test.com", "Borrower", cid)
    resource_id = _create_resource(client, auth_headers, cid)

    create_res = client.post(
        "/bookings",
        headers=borrower_headers,
        json={
            "resource_id": resource_id,
            "start_date": "2099-03-01",
            "end_date": "2099-03-05",
        },
    )
    booking_id = create_res.json()["id"]

    res = client.patch(
        f"/bookings/{booking_id}",
        headers=borrower_headers,
        json={"status": "approved"},
    )
    assert res.status_code == 409


def test_complete_approved_booking(client, auth_headers):
    cid = _create_community(client, auth_headers)
    borrower_headers = _register(client, "borrower@test.com", "Borrower", cid)
    resource_id = _create_resource(client, auth_headers, cid)

    create_res = client.post(
        "/bookings",
        headers=borrower_headers,
        json={
            "resource_id": resource_id,
            "start_date": "2099-03-01",
            "end_date": "2099-03-05",
        },
    )
    booking_id = create_res.json()["id"]

    # Approve first
    client.patch(
        f"/bookings/{booking_id}",
        headers=auth_headers,
        json={"status": "approved"},
    )

    # Then complete
    res = client.patch(
        f"/bookings/{booking_id}",
        headers=auth_headers,
        json={"status": "completed"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "completed"


def test_cannot_approve_rejected_booking(client, auth_headers):
    cid = _create_community(client, auth_headers)
    borrower_headers = _register(client, "borrower@test.com", "Borrower", cid)
    resource_id = _create_resource(client, auth_headers, cid)

    create_res = client.post(
        "/bookings",
        headers=borrower_headers,
        json={
            "resource_id": resource_id,
            "start_date": "2099-03-01",
            "end_date": "2099-03-05",
        },
    )
    booking_id = create_res.json()["id"]

    # Reject
    client.patch(
        f"/bookings/{booking_id}",
        headers=auth_headers,
        json={"status": "rejected"},
    )

    # Try to approve after rejection
    res = client.patch(
        f"/bookings/{booking_id}",
        headers=auth_headers,
        json={"status": "approved"},
    )
    assert res.status_code == 409


# ── Get booking / access control ────────────────────────────────────


def test_get_booking(client, auth_headers):
    cid = _create_community(client, auth_headers)
    borrower_headers = _register(client, "borrower@test.com", "Borrower", cid)
    resource_id = _create_resource(client, auth_headers, cid)

    create_res = client.post(
        "/bookings",
        headers=borrower_headers,
        json={
            "resource_id": resource_id,
            "start_date": "2099-03-01",
            "end_date": "2099-03-05",
        },
    )
    booking_id = create_res.json()["id"]

    # Borrower can access
    res = client.get(f"/bookings/{booking_id}", headers=borrower_headers)
    assert res.status_code == 200

    # Owner can access
    res = client.get(f"/bookings/{booking_id}", headers=auth_headers)
    assert res.status_code == 200


def test_get_booking_forbidden(client, auth_headers):
    cid = _create_community(client, auth_headers)
    borrower_headers = _register(client, "borrower@test.com", "Borrower", cid)
    stranger_headers = _register(client, "stranger@test.com", "Stranger")
    resource_id = _create_resource(client, auth_headers, cid)

    create_res = client.post(
        "/bookings",
        headers=borrower_headers,
        json={
            "resource_id": resource_id,
            "start_date": "2099-03-01",
            "end_date": "2099-03-05",
        },
    )
    booking_id = create_res.json()["id"]

    # Third party cannot access
    res = client.get(f"/bookings/{booking_id}", headers=stranger_headers)
    assert res.status_code == 403


def test_get_booking_not_found(client, auth_headers):
    res = client.get("/bookings/9999", headers=auth_headers)
    assert res.status_code == 404


# ── Calendar endpoint ───────────────────────────────────────────────


def test_calendar_endpoint(client, auth_headers):
    cid = _create_community(client, auth_headers)
    borrower_headers = _register(client, "borrower@test.com", "Borrower", cid)
    resource_id = _create_resource(client, auth_headers, cid)

    # Create a booking in March 2026
    client.post(
        "/bookings",
        headers=borrower_headers,
        json={
            "resource_id": resource_id,
            "start_date": "2099-03-10",
            "end_date": "2099-03-15",
        },
    )

    res = client.get(f"/bookings/resource/{resource_id}/calendar?month=3&year=2099")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 1
    assert data[0]["start_date"] == "2099-03-10"


def test_calendar_excludes_cancelled(client, auth_headers):
    cid = _create_community(client, auth_headers)
    borrower_headers = _register(client, "borrower@test.com", "Borrower", cid)
    resource_id = _create_resource(client, auth_headers, cid)

    create_res = client.post(
        "/bookings",
        headers=borrower_headers,
        json={
            "resource_id": resource_id,
            "start_date": "2099-03-10",
            "end_date": "2099-03-15",
        },
    )
    booking_id = create_res.json()["id"]

    # Cancel the booking
    client.patch(
        f"/bookings/{booking_id}",
        headers=borrower_headers,
        json={"status": "cancelled"},
    )

    res = client.get(f"/bookings/resource/{resource_id}/calendar?month=3&year=2099")
    assert res.status_code == 200
    assert len(res.json()) == 0


def test_calendar_different_month(client, auth_headers):
    cid = _create_community(client, auth_headers)
    borrower_headers = _register(client, "borrower@test.com", "Borrower", cid)
    resource_id = _create_resource(client, auth_headers, cid)

    client.post(
        "/bookings",
        headers=borrower_headers,
        json={
            "resource_id": resource_id,
            "start_date": "2099-03-10",
            "end_date": "2099-03-15",
        },
    )

    # Query April — should return no bookings
    res = client.get(f"/bookings/resource/{resource_id}/calendar?month=4&year=2099")
    assert res.status_code == 200
    assert len(res.json()) == 0
