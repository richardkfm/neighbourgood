"""Tests for review/rating endpoints on completed bookings."""


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


def _create_completed_booking(client, lender_headers, borrower_headers, community_id):
    """Helper: create a resource, book it, approve, and complete."""
    r = client.post(
        "/resources", headers=lender_headers,
        json={"title": "Drill", "category": "tool", "community_id": community_id},
    )
    resource_id = r.json()["id"]

    b = client.post(
        "/bookings", headers=borrower_headers,
        json={"resource_id": resource_id, "start_date": "2026-04-01", "end_date": "2026-04-05"},
    )
    booking_id = b.json()["id"]

    client.patch(f"/bookings/{booking_id}", headers=lender_headers, json={"status": "approved"})
    client.patch(f"/bookings/{booking_id}", headers=borrower_headers, json={"status": "completed"})
    return booking_id


# ── Create review ──────────────────────────────────────────────────


def test_borrower_reviews_lender(client, auth_headers, community_id):
    """Borrower can review the lender after completion."""
    borrower = _register(client, "borrower@test.com", "Borrower")
    booking_id = _create_completed_booking(client, auth_headers, borrower, community_id)

    res = client.post(
        "/reviews",
        headers=borrower,
        json={"booking_id": booking_id, "rating": 5, "comment": "Great lender!"},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["rating"] == 5
    assert data["comment"] == "Great lender!"
    assert data["reviewer"]["display_name"] == "Borrower"
    assert data["reviewee"]["display_name"] == "Test User"


def test_lender_reviews_borrower(client, auth_headers, community_id):
    """Lender can review the borrower after completion."""
    borrower = _register(client, "borrower@test.com", "Borrower")
    booking_id = _create_completed_booking(client, auth_headers, borrower, community_id)

    res = client.post(
        "/reviews",
        headers=auth_headers,
        json={"booking_id": booking_id, "rating": 4, "comment": "Returned on time"},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["reviewer"]["display_name"] == "Test User"
    assert data["reviewee"]["display_name"] == "Borrower"


def test_both_parties_can_review(client, auth_headers, community_id):
    """Both borrower and lender can review the same booking."""
    borrower = _register(client, "borrower@test.com", "Borrower")
    booking_id = _create_completed_booking(client, auth_headers, borrower, community_id)

    # Borrower reviews lender
    res1 = client.post(
        "/reviews", headers=borrower,
        json={"booking_id": booking_id, "rating": 5},
    )
    assert res1.status_code == 201

    # Lender reviews borrower
    res2 = client.post(
        "/reviews", headers=auth_headers,
        json={"booking_id": booking_id, "rating": 4},
    )
    assert res2.status_code == 201


def test_cannot_review_pending_booking(client, auth_headers, community_id):
    """Cannot review a booking that is not completed."""
    borrower = _register(client, "borrower@test.com", "Borrower")
    r = client.post(
        "/resources", headers=auth_headers,
        json={"title": "Drill", "category": "tool", "community_id": community_id},
    )
    b = client.post(
        "/bookings", headers=borrower,
        json={"resource_id": r.json()["id"], "start_date": "2026-04-01", "end_date": "2026-04-05"},
    )
    res = client.post(
        "/reviews", headers=borrower,
        json={"booking_id": b.json()["id"], "rating": 5},
    )
    assert res.status_code == 409


def test_cannot_review_twice(client, auth_headers, community_id):
    """Same person cannot review the same booking twice."""
    borrower = _register(client, "borrower@test.com", "Borrower")
    booking_id = _create_completed_booking(client, auth_headers, borrower, community_id)

    client.post(
        "/reviews", headers=borrower,
        json={"booking_id": booking_id, "rating": 5},
    )
    res = client.post(
        "/reviews", headers=borrower,
        json={"booking_id": booking_id, "rating": 3},
    )
    assert res.status_code == 409


def test_unrelated_user_cannot_review(client, auth_headers, community_id):
    """A user not involved in the booking cannot review it."""
    borrower = _register(client, "borrower@test.com", "Borrower")
    booking_id = _create_completed_booking(client, auth_headers, borrower, community_id)

    outsider = _register(client, "outsider@test.com", "Outsider")
    res = client.post(
        "/reviews", headers=outsider,
        json={"booking_id": booking_id, "rating": 1},
    )
    assert res.status_code == 403


def test_rating_out_of_range(client, auth_headers, community_id):
    """Rating must be 1-5."""
    borrower = _register(client, "borrower@test.com", "Borrower")
    booking_id = _create_completed_booking(client, auth_headers, borrower, community_id)

    res = client.post(
        "/reviews", headers=borrower,
        json={"booking_id": booking_id, "rating": 0},
    )
    assert res.status_code == 422

    res = client.post(
        "/reviews", headers=borrower,
        json={"booking_id": booking_id, "rating": 6},
    )
    assert res.status_code == 422


def test_review_requires_auth(client, auth_headers):
    """Review creation requires authentication."""
    res = client.post("/reviews", json={"booking_id": 1, "rating": 5})
    assert res.status_code == 403


# ── Read reviews ───────────────────────────────────────────────────


def test_get_booking_reviews(client, auth_headers, community_id):
    """Get all reviews for a booking."""
    borrower = _register(client, "borrower@test.com", "Borrower")
    booking_id = _create_completed_booking(client, auth_headers, borrower, community_id)

    client.post("/reviews", headers=borrower, json={"booking_id": booking_id, "rating": 5})
    client.post("/reviews", headers=auth_headers, json={"booking_id": booking_id, "rating": 4})

    res = client.get(f"/reviews/booking/{booking_id}")
    assert res.status_code == 200
    assert len(res.json()) == 2


def test_get_user_reviews(client, auth_headers, community_id):
    """Get all reviews received by a user."""
    borrower = _register(client, "borrower@test.com", "Borrower")
    booking_id = _create_completed_booking(client, auth_headers, borrower, community_id)

    # Borrower reviews lender (auth_headers user)
    client.post("/reviews", headers=borrower, json={"booking_id": booking_id, "rating": 5})

    me = client.get("/users/me", headers=auth_headers)
    user_id = me.json()["id"]

    res = client.get(f"/reviews/user/{user_id}")
    assert res.status_code == 200
    assert len(res.json()) == 1
    assert res.json()[0]["rating"] == 5


def test_get_user_review_summary(client, auth_headers, community_id):
    """Review summary shows average rating and total count."""
    borrower1 = _register(client, "b1@test.com", "B1")
    booking_id1 = _create_completed_booking(client, auth_headers, borrower1, community_id)
    client.post("/reviews", headers=borrower1, json={"booking_id": booking_id1, "rating": 5})

    borrower2 = _register(client, "b2@test.com", "B2")
    r2 = client.post(
        "/resources", headers=auth_headers,
        json={"title": "Saw", "category": "tool", "community_id": community_id},
    )
    b2 = client.post(
        "/bookings", headers=borrower2,
        json={"resource_id": r2.json()["id"], "start_date": "2026-05-01", "end_date": "2026-05-05"},
    )
    booking_id2 = b2.json()["id"]
    client.patch(f"/bookings/{booking_id2}", headers=auth_headers, json={"status": "approved"})
    client.patch(f"/bookings/{booking_id2}", headers=borrower2, json={"status": "completed"})
    client.post("/reviews", headers=borrower2, json={"booking_id": booking_id2, "rating": 3})

    me = client.get("/users/me", headers=auth_headers)
    user_id = me.json()["id"]

    res = client.get(f"/reviews/user/{user_id}/summary")
    assert res.status_code == 200
    data = res.json()
    assert data["total_reviews"] == 2
    assert data["average_rating"] == 4.0


def test_review_summary_no_reviews(client, auth_headers):
    """Summary for user with no reviews returns zero."""
    me = client.get("/users/me", headers=auth_headers)
    user_id = me.json()["id"]

    res = client.get(f"/reviews/user/{user_id}/summary")
    assert res.status_code == 200
    assert res.json()["total_reviews"] == 0
    assert res.json()["average_rating"] == 0.0


def test_review_summary_user_not_found(client):
    """Summary for non-existent user returns 404."""
    res = client.get("/reviews/user/999/summary")
    assert res.status_code == 404
