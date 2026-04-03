"""Tests for skill reviews, trust badges, and trust summary endpoints."""


def _register(client, email, name="User"):
    res = client.post(
        "/auth/register",
        json={"email": email, "password": "Password123", "display_name": name},
    )
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _create_community(client, headers, name="Trust Community"):
    res = client.post(
        "/communities",
        headers=headers,
        json={"name": name, "postal_code": "12345", "city": "Teststadt"},
    )
    return res.json()["id"]


def _join_community(client, headers, community_id):
    client.post(f"/communities/{community_id}/join", headers=headers)


def _create_skill(client, headers, community_id, title="Python Tutoring"):
    res = client.post(
        "/skills",
        headers=headers,
        json={
            "title": title,
            "category": "tutoring",
            "skill_type": "offer",
            "community_id": community_id,
        },
    )
    return res.json()["id"]


def _create_completed_booking(client, lender_headers, borrower_headers, community_id):
    r = client.post(
        "/resources",
        headers=lender_headers,
        json={"title": "Drill", "category": "tool", "community_id": community_id},
    )
    resource_id = r.json()["id"]
    b = client.post(
        "/bookings",
        headers=borrower_headers,
        json={"resource_id": resource_id, "start_date": "2026-04-01", "end_date": "2026-04-05"},
    )
    booking_id = b.json()["id"]
    client.patch(f"/bookings/{booking_id}", headers=lender_headers, json={"status": "approved"})
    client.patch(f"/bookings/{booking_id}", headers=borrower_headers, json={"status": "completed"})
    return booking_id


def _get_user_id(client, headers):
    return client.get("/users/me", headers=headers).json()["id"]


# ── Skill review creation ─────────────────────────────────────────


def test_create_skill_review(client, auth_headers):
    """Community member can review a skill in their community."""
    community_id = _create_community(client, auth_headers)
    skill_id = _create_skill(client, auth_headers, community_id)

    reviewer = _register(client, "reviewer@test.com", "Reviewer")
    _join_community(client, reviewer, community_id)

    res = client.post(
        "/reviews/skill",
        headers=reviewer,
        json={"skill_id": skill_id, "rating": 5, "comment": "Excellent tutor!"},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["rating"] == 5
    assert data["review_type"] == "skill"
    assert data["skill_id"] == skill_id
    assert data["comment"] == "Excellent tutor!"


def test_skill_review_self_rejected(client, auth_headers):
    """Cannot review your own skill."""
    community_id = _create_community(client, auth_headers)
    skill_id = _create_skill(client, auth_headers, community_id)

    res = client.post(
        "/reviews/skill",
        headers=auth_headers,
        json={"skill_id": skill_id, "rating": 5},
    )
    assert res.status_code == 403


def test_skill_review_duplicate_rejected(client, auth_headers):
    """Cannot review the same skill twice."""
    community_id = _create_community(client, auth_headers)
    skill_id = _create_skill(client, auth_headers, community_id)

    reviewer = _register(client, "reviewer@test.com", "Reviewer")
    _join_community(client, reviewer, community_id)

    client.post("/reviews/skill", headers=reviewer, json={"skill_id": skill_id, "rating": 5})
    res = client.post("/reviews/skill", headers=reviewer, json={"skill_id": skill_id, "rating": 3})
    assert res.status_code == 409


def test_skill_review_non_community_member_rejected(client, auth_headers):
    """Non-community member cannot review a skill."""
    community_id = _create_community(client, auth_headers)
    skill_id = _create_skill(client, auth_headers, community_id)

    outsider = _register(client, "outsider@test.com", "Outsider")

    res = client.post(
        "/reviews/skill",
        headers=outsider,
        json={"skill_id": skill_id, "rating": 5},
    )
    assert res.status_code == 403


def test_skill_review_not_found(client, auth_headers):
    """Review for non-existent skill returns 404."""
    res = client.post(
        "/reviews/skill",
        headers=auth_headers,
        json={"skill_id": 99999, "rating": 5},
    )
    assert res.status_code == 404


def test_skill_review_requires_auth(client):
    """Skill review requires authentication."""
    res = client.post("/reviews/skill", json={"skill_id": 1, "rating": 5})
    assert res.status_code == 403


# ── Get skill reviews ─────────────────────────────────────────────


def test_get_skill_reviews(client, auth_headers):
    """Get reviews for a skill listing."""
    community_id = _create_community(client, auth_headers)
    skill_id = _create_skill(client, auth_headers, community_id)

    r1 = _register(client, "r1@test.com", "R1")
    _join_community(client, r1, community_id)
    client.post("/reviews/skill", headers=r1, json={"skill_id": skill_id, "rating": 5})

    r2 = _register(client, "r2@test.com", "R2")
    _join_community(client, r2, community_id)
    client.post("/reviews/skill", headers=r2, json={"skill_id": skill_id, "rating": 4})

    res = client.get(f"/reviews/skill/{skill_id}")
    assert res.status_code == 200
    assert len(res.json()) == 2


def test_get_skill_reviews_not_found(client):
    """Get reviews for non-existent skill returns 404."""
    res = client.get("/reviews/skill/99999")
    assert res.status_code == 404


# ── User reviews with type filter ─────────────────────────────────


def test_get_user_reviews_filtered_by_skill(client, auth_headers):
    """Filter user reviews by type=skill."""
    community_id = _create_community(client, auth_headers)
    skill_id = _create_skill(client, auth_headers, community_id)
    user_id = _get_user_id(client, auth_headers)

    reviewer = _register(client, "reviewer@test.com", "Reviewer")
    _join_community(client, reviewer, community_id)
    client.post("/reviews/skill", headers=reviewer, json={"skill_id": skill_id, "rating": 5})

    res = client.get(f"/reviews/user/{user_id}?review_type=skill")
    assert res.status_code == 200
    reviews = res.json()
    assert len(reviews) == 1
    assert reviews[0]["review_type"] == "skill"


def test_get_user_reviews_given(client, auth_headers):
    """Filter user reviews to those given by the user."""
    community_id = _create_community(client, auth_headers)
    skill_owner = _register(client, "owner@test.com", "Owner")
    _join_community(client, skill_owner, community_id)
    skill_id = _create_skill(client, skill_owner, community_id, "Cooking Lessons")

    # auth_headers user reviews the skill
    client.post("/reviews/skill", headers=auth_headers, json={"skill_id": skill_id, "rating": 4})

    user_id = _get_user_id(client, auth_headers)
    res = client.get(f"/reviews/user/{user_id}?review_type=given")
    assert res.status_code == 200
    reviews = res.json()
    assert len(reviews) == 1
    assert reviews[0]["reviewer_id"] == user_id


# ── Review summary with breakdown ─────────────────────────────────


def test_review_summary_breakdown(client, auth_headers):
    """Summary includes lender/borrower/skill breakdown."""
    community_id = _create_community(client, auth_headers)
    user_id = _get_user_id(client, auth_headers)

    # Create a skill and get skill reviews
    skill_id = _create_skill(client, auth_headers, community_id)
    reviewer = _register(client, "rev@test.com", "Rev")
    _join_community(client, reviewer, community_id)
    client.post("/reviews/skill", headers=reviewer, json={"skill_id": skill_id, "rating": 4})

    res = client.get(f"/reviews/user/{user_id}/summary")
    assert res.status_code == 200
    data = res.json()
    assert data["total_reviews"] == 1
    assert data["skill_count"] == 1
    assert data["skill_avg"] == 4.0
    assert data["lender_count"] == 0
    assert data["borrower_count"] == 0


# ── Trust endpoints ───────────────────────────────────────────────


def test_get_user_trust(client, auth_headers):
    """Public trust endpoint returns trust summary."""
    user_id = _get_user_id(client, auth_headers)

    res = client.get(f"/users/{user_id}/trust")
    assert res.status_code == 200
    data = res.json()
    assert data["user_id"] == user_id
    assert "badges" in data
    assert "reputation_level" in data
    assert "average_rating" in data
    assert data["badges"] == []  # no reviews yet


def test_get_my_trust(client, auth_headers):
    """Authenticated trust endpoint returns own trust summary."""
    res = client.get("/users/me/trust", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["badges"] == []


def test_trust_not_found(client):
    """Trust for non-existent user returns 404."""
    res = client.get("/users/99999/trust")
    assert res.status_code == 404


# ── Badge computation ─────────────────────────────────────────────


def test_no_badge_under_threshold(client, auth_headers):
    """No badge when fewer than 3 reviews."""
    community_id = _create_community(client, auth_headers)
    skill_id = _create_skill(client, auth_headers, community_id)
    user_id = _get_user_id(client, auth_headers)

    # Only 2 skill reviews (threshold is 3)
    for i in range(2):
        r = _register(client, f"r{i}@test.com", f"R{i}")
        _join_community(client, r, community_id)
        client.post("/reviews/skill", headers=r, json={"skill_id": skill_id, "rating": 5})

    res = client.get(f"/users/{user_id}/trust")
    data = res.json()
    assert data["skill_reviews"] == 2
    badge_keys = [b["key"] for b in data["badges"]]
    assert "skilled_helper" not in badge_keys


def test_skilled_helper_badge_earned(client, auth_headers):
    """Skilled Helper badge earned with 3+ skill reviews averaging >= 4.0."""
    community_id = _create_community(client, auth_headers)
    skill_id = _create_skill(client, auth_headers, community_id)
    user_id = _get_user_id(client, auth_headers)

    for i in range(3):
        r = _register(client, f"r{i}@test.com", f"R{i}")
        _join_community(client, r, community_id)
        client.post("/reviews/skill", headers=r, json={"skill_id": skill_id, "rating": 5})

    res = client.get(f"/users/{user_id}/trust")
    data = res.json()
    assert data["skill_reviews"] == 3
    badge_keys = [b["key"] for b in data["badges"]]
    assert "skilled_helper" in badge_keys


def test_badge_not_earned_low_avg(client, auth_headers):
    """Badge NOT earned when average is below 4.0."""
    community_id = _create_community(client, auth_headers)
    skill_id = _create_skill(client, auth_headers, community_id)
    user_id = _get_user_id(client, auth_headers)

    ratings = [2, 3, 3]  # avg = 2.67
    for i, rating in enumerate(ratings):
        r = _register(client, f"r{i}@test.com", f"R{i}")
        _join_community(client, r, community_id)
        client.post("/reviews/skill", headers=r, json={"skill_id": skill_id, "rating": rating})

    res = client.get(f"/users/{user_id}/trust")
    data = res.json()
    assert data["skill_reviews"] == 3
    badge_keys = [b["key"] for b in data["badges"]]
    assert "skilled_helper" not in badge_keys


def test_trusted_lender_badge(client, auth_headers):
    """Trusted Lender badge earned with 3+ lending reviews avg >= 4.0."""
    community_id = _create_community(client, auth_headers)
    user_id = _get_user_id(client, auth_headers)

    for i in range(3):
        borrower = _register(client, f"b{i}@test.com", f"B{i}")
        _join_community(client, borrower, community_id)
        booking_id = _create_completed_booking(client, auth_headers, borrower, community_id)
        # Borrower reviews lender
        client.post("/reviews", headers=borrower, json={"booking_id": booking_id, "rating": 5})

    res = client.get(f"/users/{user_id}/trust")
    data = res.json()
    assert data["lender_reviews"] == 3
    badge_keys = [b["key"] for b in data["badges"]]
    assert "trusted_lender" in badge_keys


def test_reliable_borrower_badge(client, auth_headers):
    """Reliable Borrower badge earned with 3+ borrower reviews avg >= 4.0."""
    community_id = _create_community(client, auth_headers)

    lender = _register(client, "lender@test.com", "Lender")
    _join_community(client, lender, community_id)

    for i in range(3):
        booking_id = _create_completed_booking(client, lender, auth_headers, community_id)
        # Lender reviews borrower (auth_headers user)
        client.post("/reviews", headers=lender, json={"booking_id": booking_id, "rating": 4})

    user_id = _get_user_id(client, auth_headers)
    res = client.get(f"/users/{user_id}/trust")
    data = res.json()
    assert data["borrower_reviews"] == 3
    badge_keys = [b["key"] for b in data["badges"]]
    assert "reliable_borrower" in badge_keys


# ── OwnerTrust in listings ────────────────────────────────────────


def test_skill_list_includes_owner_trust(client, auth_headers):
    """Skill listings include owner_trust field."""
    community_id = _create_community(client, auth_headers)
    _create_skill(client, auth_headers, community_id)

    res = client.get("/skills", headers=auth_headers)
    assert res.status_code == 200
    items = res.json()["items"]
    assert len(items) >= 1
    assert "owner_trust" in items[0]
    assert items[0]["owner_trust"]["reputation_level"] is not None


def test_resource_list_includes_owner_trust(client, auth_headers):
    """Resource listings include owner_trust field."""
    community_id = _create_community(client, auth_headers)
    client.post(
        "/resources",
        headers=auth_headers,
        json={"title": "Drill", "category": "tool", "community_id": community_id},
    )

    res = client.get("/resources", headers=auth_headers)
    assert res.status_code == 200
    items = res.json()["items"]
    assert len(items) >= 1
    assert "owner_trust" in items[0]
    assert items[0]["owner_trust"]["reputation_level"] is not None


def test_skill_detail_includes_owner_trust(client, auth_headers):
    """Skill detail endpoint includes owner_trust."""
    community_id = _create_community(client, auth_headers)
    skill_id = _create_skill(client, auth_headers, community_id)

    res = client.get(f"/skills/{skill_id}")
    assert res.status_code == 200
    data = res.json()
    assert "owner_trust" in data
    assert "badges" in data["owner_trust"]


def test_resource_detail_includes_owner_trust(client, auth_headers):
    """Resource detail endpoint includes owner_trust."""
    community_id = _create_community(client, auth_headers)
    r = client.post(
        "/resources",
        headers=auth_headers,
        json={"title": "Saw", "category": "tool", "community_id": community_id},
    )
    resource_id = r.json()["id"]

    res = client.get(f"/resources/{resource_id}")
    assert res.status_code == 200
    data = res.json()
    assert "owner_trust" in data
    assert "badges" in data["owner_trust"]
