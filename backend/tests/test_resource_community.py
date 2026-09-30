"""Tests for community-scoped resources."""


def _register(client, email="test@example.com"):
    res = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "Testpass123",
            "display_name": "User",
            "neighbourhood": "Test",
        },
    )
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _create_community(client, headers, name="Testgemeinschaft", plz="12345"):
    res = client.post(
        "/communities",
        json={"name": name, "postal_code": plz, "city": "Teststadt"},
        headers=headers,
    )
    return res.json()["id"]


def test_create_resource_with_community(client, auth_headers):
    """Resource can be created with a community_id."""
    cid = _create_community(client, auth_headers)
    res = client.post(
        "/resources",
        json={"title": "Drill", "category": "tool", "community_id": cid},
        headers=auth_headers,
    )
    assert res.status_code == 201
    assert res.json()["community_id"] == cid


def test_create_resource_without_community(client, auth_headers):
    """Resource without community_id is allowed (personal item)."""
    res = client.post(
        "/resources",
        json={"title": "Saw", "category": "tool"},
        headers=auth_headers,
    )
    assert res.status_code == 201
    assert res.json()["community_id"] is None


def test_filter_resources_by_community(client, auth_headers):
    """GET /resources?community_id= filters correctly."""
    cid1 = _create_community(client, auth_headers, name="Community A")
    other_owner = _register(client, "other-owner@test.com")
    cid2 = _create_community(client, other_owner, name="Community B", plz="54321")

    # Create one resource in each community
    client.post(
        "/resources",
        json={"title": "Community Drill", "category": "tool", "community_id": cid1},
        headers=auth_headers,
    )
    client.post(
        "/resources",
        json={"title": "Other Saw", "category": "tool", "community_id": cid2},
        headers=other_owner,
    )

    # Filter by community
    res = client.get(f"/resources?community_id={cid1}")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "Community Drill"

    # Without filter returns both
    res = client.get("/resources")
    assert res.json()["total"] == 2


def test_filter_by_nonexistent_community(client, auth_headers):
    """Filtering by a community with no resources returns empty list."""
    cid = _create_community(client, auth_headers)
    client.post(
        "/resources",
        json={"title": "Drill", "category": "tool", "community_id": cid},
        headers=auth_headers,
    )
    res = client.get("/resources?community_id=9999")
    assert res.status_code == 200
    assert res.json()["total"] == 0


def test_resource_out_includes_community_id(client, auth_headers):
    """GET /resources/{id} includes community_id in response."""
    cid = _create_community(client, auth_headers)
    create_res = client.post(
        "/resources",
        json={"title": "Drill", "category": "tool", "community_id": cid},
        headers=auth_headers,
    )
    rid = create_res.json()["id"]

    res = client.get(f"/resources/{rid}")
    assert res.status_code == 200
    assert res.json()["community_id"] == cid
