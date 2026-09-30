"""Tests for skill exchange endpoints."""


def _register(client, email, name="User"):
    res = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "Password123",
            "display_name": name,
        },
    )
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


# ── List / Categories ──────────────────────────────────────────────


def test_list_skills_empty(client):
    res = client.get("/skills")
    assert res.status_code == 200
    data = res.json()
    assert data["items"] == []
    assert data["total"] == 0


def test_list_skill_categories(client):
    res = client.get("/skills/categories")
    assert res.status_code == 200
    cats = res.json()
    values = [c["value"] for c in cats]
    assert "tutoring" in values
    assert "cooking" in values
    assert "tech" in values
    assert all("label" in c and "icon" in c for c in cats)


# ── CRUD ───────────────────────────────────────────────────────────


def test_create_skill_offer(client, auth_headers, community_id):
    res = client.post(
        "/skills",
        headers=auth_headers,
        json={
            "title": "Python Tutoring",
            "description": "Happy to help with Python basics",
            "category": "tutoring",
            "skill_type": "offer",
            "community_id": community_id,
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["title"] == "Python Tutoring"
    assert data["category"] == "tutoring"
    assert data["skill_type"] == "offer"
    assert data["owner"]["display_name"] == "Test User"


def test_create_skill_request(client, auth_headers, community_id):
    res = client.post(
        "/skills",
        headers=auth_headers,
        json={
            "title": "Need guitar lessons",
            "category": "music",
            "skill_type": "request",
            "community_id": community_id,
        },
    )
    assert res.status_code == 201
    assert res.json()["skill_type"] == "request"


def test_create_skill_requires_auth(client):
    res = client.post(
        "/skills",
        json={"title": "Cooking", "category": "cooking", "skill_type": "offer", "community_id": 1},
    )
    assert res.status_code == 403


def test_create_skill_invalid_category(client, auth_headers, community_id):
    res = client.post(
        "/skills",
        headers=auth_headers,
        json={"title": "X", "category": "nonexistent", "skill_type": "offer", "community_id": community_id},
    )
    assert res.status_code == 422


def test_create_skill_invalid_type(client, auth_headers, community_id):
    res = client.post(
        "/skills",
        headers=auth_headers,
        json={"title": "X", "category": "cooking", "skill_type": "invalid", "community_id": community_id},
    )
    assert res.status_code == 422


def test_get_skill(client, auth_headers, community_id):
    create = client.post(
        "/skills",
        headers=auth_headers,
        json={"title": "Bike Repair", "category": "repairs", "skill_type": "offer", "community_id": community_id},
    )
    skill_id = create.json()["id"]

    res = client.get(f"/skills/{skill_id}")
    assert res.status_code == 200
    assert res.json()["title"] == "Bike Repair"


def test_get_skill_not_found(client):
    res = client.get("/skills/999")
    assert res.status_code == 404


def test_update_skill(client, auth_headers, community_id):
    create = client.post(
        "/skills",
        headers=auth_headers,
        json={"title": "Gardening help", "category": "gardening", "skill_type": "offer", "community_id": community_id},
    )
    skill_id = create.json()["id"]

    res = client.patch(
        f"/skills/{skill_id}",
        headers=auth_headers,
        json={"title": "Gardening & Composting"},
    )
    assert res.status_code == 200
    assert res.json()["title"] == "Gardening & Composting"


def test_update_skill_not_owner(client, auth_headers, community_id):
    create = client.post(
        "/skills",
        headers=auth_headers,
        json={"title": "Cooking class", "category": "cooking", "skill_type": "offer", "community_id": community_id},
    )
    skill_id = create.json()["id"]

    other = _register(client, "other@test.com", "Other")
    res = client.patch(
        f"/skills/{skill_id}",
        headers=other,
        json={"title": "Stolen"},
    )
    assert res.status_code == 403


def test_delete_skill(client, auth_headers, community_id):
    create = client.post(
        "/skills",
        headers=auth_headers,
        json={"title": "Old skill", "category": "other", "skill_type": "offer", "community_id": community_id},
    )
    skill_id = create.json()["id"]

    res = client.delete(f"/skills/{skill_id}", headers=auth_headers)
    assert res.status_code == 204

    res = client.get(f"/skills/{skill_id}")
    assert res.status_code == 404


def test_delete_skill_not_owner(client, auth_headers, community_id):
    create = client.post(
        "/skills",
        headers=auth_headers,
        json={"title": "Protected", "category": "tech", "skill_type": "offer", "community_id": community_id},
    )
    skill_id = create.json()["id"]

    other = _register(client, "hacker@test.com", "Hacker")
    res = client.delete(f"/skills/{skill_id}", headers=other)
    assert res.status_code == 403


# ── Filters and Search ─────────────────────────────────────────────


def test_filter_by_category(client, auth_headers, community_id):
    client.post(
        "/skills", headers=auth_headers,
        json={"title": "Cooking", "category": "cooking", "skill_type": "offer", "community_id": community_id},
    )
    client.post(
        "/skills", headers=auth_headers,
        json={"title": "Coding", "category": "tech", "skill_type": "offer", "community_id": community_id},
    )

    res = client.get("/skills?category=cooking")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert data["items"][0]["category"] == "cooking"


def test_filter_by_skill_type(client, auth_headers, community_id):
    client.post(
        "/skills", headers=auth_headers,
        json={"title": "Offer gardening", "category": "gardening", "skill_type": "offer", "community_id": community_id},
    )
    client.post(
        "/skills", headers=auth_headers,
        json={"title": "Need gardening", "category": "gardening", "skill_type": "request", "community_id": community_id},
    )

    res = client.get("/skills?skill_type=request")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert data["items"][0]["skill_type"] == "request"


def test_search_skills(client, auth_headers, community_id):
    client.post(
        "/skills", headers=auth_headers,
        json={"title": "Piano Lessons", "category": "music", "skill_type": "offer", "community_id": community_id},
    )
    client.post(
        "/skills", headers=auth_headers,
        json={"title": "Yoga Classes", "category": "fitness", "skill_type": "offer", "community_id": community_id},
    )

    res = client.get("/skills?q=piano")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert "Piano" in data["items"][0]["title"]
