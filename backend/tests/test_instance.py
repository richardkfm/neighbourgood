"""Tests for /instance/info endpoint."""


def test_instance_info(client):
    """Instance info returns metadata and counts."""
    res = client.get("/instance/info")
    assert res.status_code == 200
    data = res.json()
    assert data["name"] == "My NeighbourGood"
    assert data["version"] == "1.9.5.1"
    assert data["platform_mode"] == "blue"
    assert "admin_name" in data
    assert "admin_contact" in data
    assert data["community_count"] == 0
    assert data["user_count"] == 0


def test_instance_info_counts_users(client, auth_headers):
    """Instance info counts registered users."""
    res = client.get("/instance/info")
    assert res.json()["user_count"] == 1


def test_instance_info_counts_communities(client, auth_headers):
    """Instance info counts active communities."""
    client.post(
        "/communities",
        json={"name": "Test Community", "postal_code": "12345", "city": "Teststadt"},
        headers=auth_headers,
    )
    res = client.get("/instance/info")
    assert res.json()["community_count"] == 1
