"""Tests for community invite code endpoints."""


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


# ── Create invite ──────────────────────────────────────────────────


def test_create_invite(client, auth_headers):
    """Community member can create an invite code."""
    community_id = _create_community(client, auth_headers)
    res = client.post(
        "/invites",
        headers=auth_headers,
        json={"community_id": community_id},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["community_id"] == community_id
    assert len(data["code"]) > 10
    assert data["use_count"] == 0
    assert data["is_active"] is True


def test_create_invite_with_max_uses(client, auth_headers):
    """Invite can have a max_uses limit."""
    community_id = _create_community(client, auth_headers)
    res = client.post(
        "/invites",
        headers=auth_headers,
        json={"community_id": community_id, "max_uses": 5},
    )
    assert res.status_code == 201
    assert res.json()["max_uses"] == 5


def test_create_invite_with_expiry(client, auth_headers):
    """Invite can have an expiry time."""
    community_id = _create_community(client, auth_headers)
    res = client.post(
        "/invites",
        headers=auth_headers,
        json={"community_id": community_id, "expires_in_hours": 24},
    )
    assert res.status_code == 201
    assert res.json()["expires_at"] is not None


def test_create_invite_non_member(client, auth_headers):
    """Non-member cannot create an invite."""
    community_id = _create_community(client, auth_headers)
    other = _register(client, "other@test.com", "Other")
    res = client.post(
        "/invites",
        headers=other,
        json={"community_id": community_id},
    )
    assert res.status_code == 403


def test_create_invite_requires_auth(client, auth_headers):
    """Invite creation requires authentication."""
    community_id = _create_community(client, auth_headers)
    res = client.post("/invites", json={"community_id": community_id})
    assert res.status_code == 403


# ── List invites ───────────────────────────────────────────────────


def test_list_invites(client, auth_headers):
    """Member can list active invites for their community."""
    community_id = _create_community(client, auth_headers)
    client.post(
        "/invites", headers=auth_headers,
        json={"community_id": community_id},
    )
    client.post(
        "/invites", headers=auth_headers,
        json={"community_id": community_id},
    )
    res = client.get(f"/invites?community_id={community_id}", headers=auth_headers)
    assert res.status_code == 200
    assert len(res.json()) == 2


def test_list_invites_non_member(client, auth_headers):
    """Non-member cannot list invites."""
    community_id = _create_community(client, auth_headers)
    other = _register(client, "other@test.com", "Other")
    res = client.get(f"/invites?community_id={community_id}", headers=other)
    assert res.status_code == 403


# ── Redeem invite ──────────────────────────────────────────────────


def test_redeem_invite(client, auth_headers):
    """Invite code joins a user to the community."""
    community_id = _create_community(client, auth_headers)
    invite = client.post(
        "/invites", headers=auth_headers,
        json={"community_id": community_id},
    )
    code = invite.json()["code"]

    joiner = _register(client, "joiner@test.com", "Joiner")
    res = client.post(f"/invites/{code}/redeem", headers=joiner)
    assert res.status_code == 200
    data = res.json()
    assert data["community_id"] == community_id
    assert "Welcome" in data["message"]

    # Verify membership
    members = client.get(f"/communities/{community_id}/members")
    names = [m["user"]["display_name"] for m in members.json()]
    assert "Joiner" in names


def test_redeem_invite_already_member(client, auth_headers):
    """Redeeming when already a member returns a friendly message."""
    community_id = _create_community(client, auth_headers)
    invite = client.post(
        "/invites", headers=auth_headers,
        json={"community_id": community_id},
    )
    code = invite.json()["code"]

    # Creator is already a member
    res = client.post(f"/invites/{code}/redeem", headers=auth_headers)
    assert res.status_code == 200
    assert "already a member" in res.json()["message"]


def test_redeem_invite_blocked_when_already_in_different_community(client, auth_headers):
    """Redeeming an invite for a different community is blocked while already a member elsewhere."""
    community_a_id = _create_community(client, auth_headers, name="Community A")
    other = _register(client, "otheradmin@test.com", "OtherAdmin")
    community_b_id = _create_community(client, other, name="Community B")

    joiner = _register(client, "joiner@test.com", "Joiner")
    res_a = client.post(f"/communities/{community_a_id}/join", headers=joiner)
    assert res_a.status_code == 200

    invite_b = client.post(
        "/invites", headers=other,
        json={"community_id": community_b_id},
    )
    code = invite_b.json()["code"]

    res_b = client.post(f"/invites/{code}/redeem", headers=joiner)
    assert res_b.status_code == 409
    assert "already a member of a community" in res_b.json()["detail"]


def test_redeem_invite_increments_use_count(client, auth_headers):
    """Redeeming increments the use_count."""
    community_id = _create_community(client, auth_headers)
    invite = client.post(
        "/invites", headers=auth_headers,
        json={"community_id": community_id},
    )
    code = invite.json()["code"]
    invite_id = invite.json()["id"]

    joiner = _register(client, "joiner@test.com", "Joiner")
    client.post(f"/invites/{code}/redeem", headers=joiner)

    # Check use_count via list
    invites = client.get(f"/invites?community_id={community_id}", headers=auth_headers)
    invite_data = [i for i in invites.json() if i["id"] == invite_id][0]
    assert invite_data["use_count"] == 1


def test_redeem_invite_max_uses_exceeded(client, auth_headers):
    """Invite with max_uses=1 can only be used once."""
    community_id = _create_community(client, auth_headers)
    invite = client.post(
        "/invites", headers=auth_headers,
        json={"community_id": community_id, "max_uses": 1},
    )
    code = invite.json()["code"]

    joiner1 = _register(client, "j1@test.com", "J1")
    client.post(f"/invites/{code}/redeem", headers=joiner1)

    joiner2 = _register(client, "j2@test.com", "J2")
    res = client.post(f"/invites/{code}/redeem", headers=joiner2)
    assert res.status_code == 410


def test_redeem_invalid_code(client, auth_headers):
    """Invalid invite code returns 404."""
    res = client.post("/invites/bogus-code/redeem", headers=auth_headers)
    assert res.status_code == 404


# ── Revoke invite ──────────────────────────────────────────────────


def test_revoke_invite(client, auth_headers):
    """Creator can revoke their own invite."""
    community_id = _create_community(client, auth_headers)
    invite = client.post(
        "/invites", headers=auth_headers,
        json={"community_id": community_id},
    )
    invite_id = invite.json()["id"]

    res = client.delete(f"/invites/{invite_id}", headers=auth_headers)
    assert res.status_code == 204

    # Revoked invite code should not work
    code = invite.json()["code"]
    joiner = _register(client, "joiner@test.com", "Joiner")
    res = client.post(f"/invites/{code}/redeem", headers=joiner)
    assert res.status_code == 404


def test_revoke_invite_not_owner(client, auth_headers):
    """Non-creator non-admin cannot revoke an invite."""
    community_id = _create_community(client, auth_headers)
    invite = client.post(
        "/invites", headers=auth_headers,
        json={"community_id": community_id},
    )
    invite_id = invite.json()["id"]

    other = _register(client, "other@test.com", "Other")
    res = client.delete(f"/invites/{invite_id}", headers=other)
    assert res.status_code == 403
