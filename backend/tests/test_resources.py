"""Tests for resource CRUD endpoints."""


def test_list_resources_empty(client):
    res = client.get("/resources")
    assert res.status_code == 200
    data = res.json()
    assert data["items"] == []
    assert data["total"] == 0


def test_create_resource(client, auth_headers, community_id):
    res = client.post(
        "/resources",
        headers=auth_headers,
        json={
            "title": "Electric Drill",
            "description": "Bosch 18V, works great",
            "category": "tool",
            "condition": "good",
            "community_id": community_id,
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["title"] == "Electric Drill"
    assert data["category"] == "tool"
    assert data["is_available"] is True
    assert data["owner"]["display_name"] == "Test User"


def test_create_resource_invalid_category(client, auth_headers, community_id):
    res = client.post(
        "/resources",
        headers=auth_headers,
        json={"title": "Thing", "category": "invalid_cat", "community_id": community_id},
    )
    assert res.status_code == 422


def test_get_resource_by_id(client, auth_headers, community_id):
    create_res = client.post(
        "/resources",
        headers=auth_headers,
        json={"title": "Projector", "category": "electronics", "condition": "new", "community_id": community_id},
    )
    resource_id = create_res.json()["id"]

    res = client.get(f"/resources/{resource_id}")
    assert res.status_code == 200
    assert res.json()["title"] == "Projector"


def test_get_resource_not_found(client):
    res = client.get("/resources/9999")
    assert res.status_code == 404


def test_update_resource(client, auth_headers, community_id):
    create_res = client.post(
        "/resources",
        headers=auth_headers,
        json={"title": "Ladder", "category": "tool", "community_id": community_id},
    )
    resource_id = create_res.json()["id"]

    res = client.patch(
        f"/resources/{resource_id}",
        headers=auth_headers,
        json={"title": "Tall Ladder", "is_available": False},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["title"] == "Tall Ladder"
    assert data["is_available"] is False


def test_delete_resource(client, auth_headers, community_id):
    create_res = client.post(
        "/resources",
        headers=auth_headers,
        json={"title": "Old Chair", "category": "furniture", "community_id": community_id},
    )
    resource_id = create_res.json()["id"]

    res = client.delete(f"/resources/{resource_id}", headers=auth_headers)
    assert res.status_code == 204

    res = client.get(f"/resources/{resource_id}")
    assert res.status_code == 404


def test_filter_by_category(client, auth_headers, community_id):
    client.post(
        "/resources",
        headers=auth_headers,
        json={"title": "Wrench", "category": "tool", "community_id": community_id},
    )
    client.post(
        "/resources",
        headers=auth_headers,
        json={"title": "Sofa", "category": "furniture", "community_id": community_id},
    )

    res = client.get("/resources?category=tool")
    data = res.json()
    assert data["total"] == 1
    assert data["items"][0]["category"] == "tool"


def test_create_resource_requires_auth(client):
    res = client.post("/resources", json={"title": "X", "category": "tool", "community_id": 1})
    assert res.status_code == 403
