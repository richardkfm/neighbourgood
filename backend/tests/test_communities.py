"""Tests for community endpoints: CRUD, membership, search, merge, suggestions."""


def _register(client, email, name="User"):
    """Helper: register a user and return auth headers."""
    res = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "Password123",
            "display_name": name,
        },
    )
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _create_community(client, headers, name="Nachbarschaft Mitte", plz="10115", city="Berlin"):
    """Helper: create a community and return its data."""
    res = client.post(
        "/communities",
        headers=headers,
        json={
            "name": name,
            "description": f"Community in {city}",
            "postal_code": plz,
            "city": city,
        },
    )
    return res.json()


def _other_creator(client, n, **kwargs):
    """Register a fresh user, have them create a community, return (headers, community)."""
    headers = _register(client, f"creator{n}@test.com", f"Creator {n}")
    return headers, _create_community(client, headers, **kwargs)


# ── Create ─────────────────────────────────────────────────────────


def test_create_community(client, auth_headers):
    res = client.post(
        "/communities",
        headers=auth_headers,
        json={
            "name": "Kiez Kreuzberg",
            "description": "Sharing in Kreuzberg",
            "postal_code": "10999",
            "city": "Berlin",
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["name"] == "Kiez Kreuzberg"
    assert data["postal_code"] == "10999"
    assert data["city"] == "Berlin"
    assert data["is_active"] is True
    assert data["member_count"] == 1  # Creator is auto-member


def test_create_community_blocked_when_already_member(client, auth_headers):
    _create_community(client, auth_headers, name="First")
    res = client.post(
        "/communities",
        headers=auth_headers,
        json={"name": "Second", "postal_code": "10999", "city": "Berlin"},
    )
    assert res.status_code == 409
    assert "leave your current community" in res.json()["detail"].lower()


def test_create_community_allowed_after_leaving(client, auth_headers):
    first = _create_community(client, auth_headers, name="First")
    # Sole member may leave (nobody else to manage the community)
    assert client.delete(f"/communities/{first['id']}/leave", headers=auth_headers).status_code == 204
    second = _create_community(client, auth_headers, name="Second", plz="10999")
    assert second["name"] == "Second"


def test_create_community_requires_auth(client):
    res = client.post(
        "/communities",
        json={"name": "Test", "postal_code": "12345", "city": "Berlin"},
    )
    assert res.status_code == 403


# ── Get ────────────────────────────────────────────────────────────


def test_get_community(client, auth_headers):
    created = _create_community(client, auth_headers)
    res = client.get(f"/communities/{created['id']}")
    assert res.status_code == 200
    assert res.json()["name"] == "Nachbarschaft Mitte"


def test_get_community_not_found(client):
    res = client.get("/communities/9999")
    assert res.status_code == 404


# ── Update ─────────────────────────────────────────────────────────


def test_update_community_as_admin(client, auth_headers):
    created = _create_community(client, auth_headers)
    res = client.patch(
        f"/communities/{created['id']}",
        headers=auth_headers,
        json={"name": "Nachbarschaft Mitte (updated)"},
    )
    assert res.status_code == 200
    assert res.json()["name"] == "Nachbarschaft Mitte (updated)"


def test_update_community_non_admin_forbidden(client, auth_headers):
    created = _create_community(client, auth_headers)
    other = _register(client, "other@test.com", "Other")

    # Join as member
    client.post(f"/communities/{created['id']}/join", headers=other)

    # Try to update as non-admin
    res = client.patch(
        f"/communities/{created['id']}",
        headers=other,
        json={"name": "Hijacked"},
    )
    assert res.status_code == 403


# ── Membership ─────────────────────────────────────────────────────


def test_join_community(client, auth_headers):
    created = _create_community(client, auth_headers)
    other = _register(client, "joiner@test.com", "Joiner")

    res = client.post(f"/communities/{created['id']}/join", headers=other)
    assert res.status_code == 200
    assert res.json()["role"] == "member"


def test_join_community_already_member(client, auth_headers):
    created = _create_community(client, auth_headers)
    other = _register(client, "joiner@test.com", "Joiner")

    client.post(f"/communities/{created['id']}/join", headers=other)
    res = client.post(f"/communities/{created['id']}/join", headers=other)
    assert res.status_code == 409
    assert "Already a member" in res.json()["detail"]


def test_join_community_blocked_when_already_in_different_community(client, auth_headers):
    community_a = _create_community(client, auth_headers, name="Group A", plz="10115", city="Berlin")
    _, community_b = _other_creator(client, 2, name="Group B", plz="10999", city="Berlin")
    other = _register(client, "joiner@test.com", "Joiner")

    res_a = client.post(f"/communities/{community_a['id']}/join", headers=other)
    assert res_a.status_code == 200

    res_b = client.post(f"/communities/{community_b['id']}/join", headers=other)
    assert res_b.status_code == 409
    assert "already a member of a community" in res_b.json()["detail"]


def test_join_community_after_leaving_allowed(client, auth_headers):
    community_a = _create_community(client, auth_headers, name="Group A", plz="10115", city="Berlin")
    _, community_b = _other_creator(client, 2, name="Group B", plz="10999", city="Berlin")
    other = _register(client, "switcher@test.com", "Switcher")

    client.post(f"/communities/{community_a['id']}/join", headers=other)
    leave_res = client.delete(f"/communities/{community_a['id']}/leave", headers=other)
    assert leave_res.status_code == 204

    res_b = client.post(f"/communities/{community_b['id']}/join", headers=other)
    assert res_b.status_code == 200


def test_leave_community(client, auth_headers):
    created = _create_community(client, auth_headers)
    other = _register(client, "leaver@test.com", "Leaver")

    client.post(f"/communities/{created['id']}/join", headers=other)
    res = client.delete(f"/communities/{created['id']}/leave", headers=other)
    assert res.status_code == 204


def test_leave_community_not_member(client, auth_headers):
    created = _create_community(client, auth_headers)
    other = _register(client, "stranger@test.com", "Stranger")

    res = client.delete(f"/communities/{created['id']}/leave", headers=other)
    assert res.status_code == 404


def test_list_members(client, auth_headers):
    created = _create_community(client, auth_headers)
    other = _register(client, "member@test.com", "Member")
    client.post(f"/communities/{created['id']}/join", headers=other)

    res = client.get(f"/communities/{created['id']}/members")
    assert res.status_code == 200
    members = res.json()
    assert len(members) == 2
    roles = {m["role"] for m in members}
    assert "admin" in roles
    assert "member" in roles


def test_my_communities(client, auth_headers):
    _create_community(client, auth_headers, name="Group A", plz="10115")
    _other_creator(client, 2, name="Group B", plz="10999")

    res = client.get("/communities/my/memberships", headers=auth_headers)
    assert res.status_code == 200
    names = {c["name"] for c in res.json()}
    assert names == {"Group A"}


# ── Search ─────────────────────────────────────────────────────────


def test_search_communities_by_name(client, auth_headers):
    _create_community(client, auth_headers, name="Kiez Kreuzberg", plz="10999", city="Berlin")
    _other_creator(client, 2, name="Dorf Gemeinschaft", plz="01234", city="Dresden")

    res = client.get("/communities/search?q=kreuzberg")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert data["items"][0]["name"] == "Kiez Kreuzberg"


def test_search_communities_by_postal_code(client, auth_headers):
    _create_community(client, auth_headers, name="Group A", plz="10115", city="Berlin")
    _other_creator(client, 2, name="Group B", plz="10999", city="Berlin")

    res = client.get("/communities/search?postal_code=10115")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert data["items"][0]["postal_code"] == "10115"


def test_search_communities_by_city(client, auth_headers):
    _create_community(client, auth_headers, name="Group A", plz="10115", city="Berlin")
    _other_creator(client, 2, name="Group B", plz="01234", city="Dresden")

    res = client.get("/communities/search?city=Berlin")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert data["items"][0]["city"] == "Berlin"


def test_search_all_communities(client, auth_headers):
    _create_community(client, auth_headers, name="Group A", plz="10115", city="Berlin")
    _other_creator(client, 2, name="Group B", plz="01234", city="Dresden")

    res = client.get("/communities/search")
    assert res.status_code == 200
    assert res.json()["total"] == 2


# ── Merge ──────────────────────────────────────────────────────────


def test_merge_communities(client, auth_headers, admin_headers):
    source = _create_community(client, auth_headers, name="Small Group", plz="10115", city="Berlin")
    _, target = _other_creator(client, 2, name="Big Group", plz="10115", city="Berlin")

    # Add a unique member to source
    other = _register(client, "source_member@test.com", "SourceMember")
    client.post(f"/communities/{source['id']}/join", headers=other)

    res = client.post(
        "/communities/merge",
        headers=admin_headers,
        json={"source_id": source["id"], "target_id": target["id"]},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == target["id"]
    # Target now has its creator plus the source's two members
    assert data["member_count"] == 3

    # Source should be inactive and merged
    source_res = client.get(f"/communities/{source['id']}")
    assert source_res.json()["is_active"] is False
    assert source_res.json()["merged_into_id"] == target["id"]


def test_merge_self_fails(client, auth_headers):
    community = _create_community(client, auth_headers)
    res = client.post(
        "/communities/merge",
        headers=auth_headers,
        json={"source_id": community["id"], "target_id": community["id"]},
    )
    assert res.status_code == 422


def test_merge_already_merged_fails(client, auth_headers, admin_headers):
    a = _create_community(client, auth_headers, name="A", plz="10115", city="Berlin")
    _, b = _other_creator(client, 2, name="B", plz="10115", city="Berlin")
    _, c = _other_creator(client, 3, name="C", plz="10115", city="Berlin")

    # Merge A into B
    client.post(
        "/communities/merge",
        headers=admin_headers,
        json={"source_id": a["id"], "target_id": b["id"]},
    )

    # Try to merge A into C (already merged)
    res = client.post(
        "/communities/merge",
        headers=admin_headers,
        json={"source_id": a["id"], "target_id": c["id"]},
    )
    assert res.status_code == 409


def test_merge_non_admin_forbidden(client, auth_headers):
    source = _create_community(client, auth_headers, name="Source", plz="10115", city="Berlin")
    other = _register(client, "nonadmin@test.com", "NonAdmin")
    target = _create_community(client, other, name="Target", plz="10115", city="Berlin")

    # Other is admin of target but not of source
    res = client.post(
        "/communities/merge",
        headers=other,
        json={"source_id": source["id"], "target_id": target["id"]},
    )
    assert res.status_code == 403


def test_join_merged_community_redirects(client, auth_headers, admin_headers):
    source = _create_community(client, auth_headers, name="Old Group", plz="10115", city="Berlin")
    _, target = _other_creator(client, 2, name="New Group", plz="10115", city="Berlin")

    client.post(
        "/communities/merge",
        headers=admin_headers,
        json={"source_id": source["id"], "target_id": target["id"]},
    )

    other = _register(client, "newbie@test.com", "Newbie")
    res = client.post(f"/communities/{source['id']}/join", headers=other)
    assert res.status_code == 409
    assert str(target["id"]) in res.json()["detail"]


def test_merge_migrated_member_not_blocked_and_memberships_filtered(client, auth_headers, admin_headers):
    source = _create_community(client, auth_headers, name="Old Group", plz="10115", city="Berlin")
    _, target = _other_creator(client, 2, name="New Group", plz="10115", city="Berlin")

    member = _register(client, "migrated@test.com", "Migrated")
    join_res = client.post(f"/communities/{source['id']}/join", headers=member)
    assert join_res.status_code == 200

    merge_res = client.post(
        "/communities/merge",
        headers=admin_headers,
        json={"source_id": source["id"], "target_id": target["id"]},
    )
    assert merge_res.status_code == 200

    # The member now has a stale row in the merged (inactive) source community
    # plus a fresh row in the active target — /my/memberships must only report
    # the active one, and repeated calls must return a stable order.
    res1 = client.get("/communities/my/memberships", headers=member)
    res2 = client.get("/communities/my/memberships", headers=member)
    assert res1.status_code == 200 and res2.status_code == 200
    names1 = [c["name"] for c in res1.json()]
    names2 = [c["name"] for c in res2.json()]
    assert names1 == ["New Group"]
    assert names1 == names2


# ── Merge Suggestions ──────────────────────────────────────────────


def test_merge_suggestions_same_plz(client, auth_headers):
    a = _create_community(client, auth_headers, name="Group A", plz="10115", city="Berlin")
    _other_creator(client, 2, name="Group B", plz="10115", city="Berlin")
    _other_creator(client, 3, name="Group C", plz="99999", city="Hamburg")

    res = client.get(
        f"/communities/merge/suggestions?community_id={a['id']}",
        headers=auth_headers,
    )
    assert res.status_code == 200
    suggestions = res.json()
    assert len(suggestions) == 1
    assert suggestions[0]["reason"].startswith("Same postal code")


def test_merge_suggestions_same_city(client, auth_headers):
    a = _create_community(client, auth_headers, name="Group A", plz="10115", city="Berlin")
    _other_creator(client, 2, name="Group B", plz="10999", city="Berlin")

    res = client.get(
        f"/communities/merge/suggestions?community_id={a['id']}",
        headers=auth_headers,
    )
    assert res.status_code == 200
    suggestions = res.json()
    assert len(suggestions) == 1
    assert suggestions[0]["reason"].startswith("Same city")


def test_search_excludes_merged(client, auth_headers, admin_headers):
    source = _create_community(client, auth_headers, name="Old", plz="10115", city="Berlin")
    _, target = _other_creator(client, 2, name="New", plz="10115", city="Berlin")

    client.post(
        "/communities/merge",
        headers=admin_headers,
        json={"source_id": source["id"], "target_id": target["id"]},
    )

    res = client.get("/communities/search?postal_code=10115")
    data = res.json()
    assert data["total"] == 1
    assert data["items"][0]["name"] == "New"
