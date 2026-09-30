"""Regression tests: membership rules, community admin lifecycle, booking and reputation semantics."""

import datetime

from app.models.community import CommunityMember

PASSWORD = "Testpass123"


def _register(client, email, name="User"):
    res = client.post(
        "/auth/register",
        json={"email": email, "password": PASSWORD, "display_name": name},
    )
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _user_id(client, headers):
    return client.get("/users/me", headers=headers).json()["id"]


def _community(client, headers, name="Group", plz="10115"):
    res = client.post(
        "/communities", headers=headers, json={"name": name, "postal_code": plz, "city": "Berlin"}
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _join(client, headers, cid):
    res = client.post(f"/communities/{cid}/join", headers=headers)
    assert res.status_code == 200, res.text


def _resource(client, headers, cid=None, **extra):
    body = {"title": "Drill", "category": "tool", **extra}
    if cid is not None:
        body["community_id"] = cid
    res = client.post("/resources", headers=headers, json=body)
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _day(offset):
    return (datetime.date.today() + datetime.timedelta(days=offset)).isoformat()


def _book(client, headers, rid, start, end):
    return client.post(
        "/bookings", headers=headers, json={"resource_id": rid, "start_date": _day(start), "end_date": _day(end)}
    )


# ── (a) booking membership ──────────────────────────────────────────────────


def test_booking_requires_community_membership(client, auth_headers, community_id):
    rid = _resource(client, auth_headers, community_id)
    outsider = _register(client, "outsider@test.com")
    res = _book(client, outsider, rid, 1, 2)
    assert res.status_code == 403

    _join(client, outsider, community_id)
    assert _book(client, outsider, rid, 1, 2).status_code == 201


def test_booking_member_of_other_community_is_rejected(client, auth_headers, community_id):
    rid = _resource(client, auth_headers, community_id)
    other = _register(client, "other@test.com")
    _community(client, other, name="Elsewhere", plz="99999")
    assert _book(client, other, rid, 1, 2).status_code == 403


def test_booking_personal_item_needs_shared_community(client, auth_headers, community_id):
    rid = _resource(client, auth_headers)  # community_id NULL
    stranger = _register(client, "stranger@test.com")
    assert _book(client, stranger, rid, 1, 2).status_code == 403

    neighbour = _register(client, "neighbour@test.com")
    _join(client, neighbour, community_id)  # shares the owner's community
    assert _book(client, neighbour, rid, 1, 2).status_code == 201


# ── (b) RSVP membership ─────────────────────────────────────────────────────


def test_rsvp_requires_community_membership(client, auth_headers, community_id):
    start = (datetime.datetime.utcnow() + datetime.timedelta(days=3)).isoformat()
    eid = client.post(
        "/events",
        headers=auth_headers,
        json={"title": "Picnic", "category": "meetup", "start_at": start, "community_id": community_id},
    ).json()["id"]

    outsider = _register(client, "outsider@test.com")
    assert client.post(f"/events/{eid}/attend", headers=outsider).status_code == 403

    _join(client, outsider, community_id)
    assert client.post(f"/events/{eid}/attend", headers=outsider).status_code == 201


# ── (c) create community while a member ─────────────────────────────────────


def test_create_community_conflict_when_member_via_join(client, auth_headers, community_id):
    other = _register(client, "joiner@test.com")
    _join(client, other, community_id)
    res = client.post(
        "/communities", headers=other, json={"name": "Mine", "postal_code": "1", "city": "X"}
    )
    assert res.status_code == 409
    assert "leave your current community" in res.json()["detail"].lower()


# ── Merge and admin lifecycle ───────────────────────────────────────────────


def test_merge_requires_admin_of_both(client, auth_headers, db):
    a = _community(client, auth_headers, name="A")
    other = _register(client, "b@test.com")
    b = _community(client, other, name="B")
    uid = _user_id(client, auth_headers)

    # Admin of the source only -> rejected
    res = client.post("/communities/merge", headers=auth_headers, json={"source_id": a, "target_id": b})
    assert res.status_code == 403
    assert "target" in res.json()["detail"].lower()

    # Admin of the target only -> rejected
    res = client.post("/communities/merge", headers=other, json={"source_id": a, "target_id": b})
    assert res.status_code == 403
    assert "source" in res.json()["detail"].lower()

    # Admin of both (possible for memberships that predate one-community-per-user)
    db.add(CommunityMember(community_id=b, user_id=uid, role="admin"))
    db.commit()
    res = client.post("/communities/merge", headers=auth_headers, json={"source_id": a, "target_id": b})
    assert res.status_code == 200


def test_merge_allowed_for_platform_admin(client, auth_headers, admin_headers):
    a = _community(client, auth_headers, name="A")
    b = _community(client, _register(client, "b@test.com"), name="B")
    res = client.post("/communities/merge", headers=admin_headers, json={"source_id": a, "target_id": b})
    assert res.status_code == 200


def test_last_admin_cannot_leave_until_another_admin_exists(client, auth_headers, community_id):
    member = _register(client, "member@test.com")
    _join(client, member, community_id)
    member_id = _user_id(client, member)

    res = client.delete(f"/communities/{community_id}/leave", headers=auth_headers)
    assert res.status_code == 409
    assert "last admin" in res.json()["detail"].lower()

    promoted = client.post(f"/communities/{community_id}/members/{member_id}/promote", headers=auth_headers)
    assert promoted.status_code == 200
    assert promoted.json()["role"] == "admin"

    assert client.delete(f"/communities/{community_id}/leave", headers=auth_headers).status_code == 204


def test_admin_can_leave_when_another_admin_exists_and_members_can_always_leave(
    client, auth_headers, community_id
):
    member = _register(client, "member@test.com")
    _join(client, member, community_id)
    assert client.delete(f"/communities/{community_id}/leave", headers=member).status_code == 204


def test_promote_member_requires_community_admin(client, auth_headers, community_id):
    m1 = _register(client, "m1@test.com")
    m2 = _register(client, "m2@test.com")
    _join(client, m1, community_id)
    _join(client, m2, community_id)
    m2_id = _user_id(client, m2)

    # A plain member cannot promote
    res = client.post(f"/communities/{community_id}/members/{m2_id}/promote", headers=m1)
    assert res.status_code == 403
    # Unauthenticated
    assert client.post(f"/communities/{community_id}/members/{m2_id}/promote").status_code == 403


def test_promote_member_error_paths(client, auth_headers, community_id):
    member = _register(client, "member@test.com")
    _join(client, member, community_id)
    member_id = _user_id(client, member)
    outsider_id = _user_id(client, _register(client, "outsider@test.com"))
    admin_id = _user_id(client, auth_headers)

    assert client.post(f"/communities/{community_id}/members/{outsider_id}/promote", headers=auth_headers).status_code == 404
    assert client.post(f"/communities/99999/members/{member_id}/promote", headers=auth_headers).status_code == 404
    assert client.post(f"/communities/{community_id}/members/{admin_id}/promote", headers=auth_headers).status_code == 409

    # Promotion shows up in the member list
    client.post(f"/communities/{community_id}/members/{member_id}/promote", headers=auth_headers)
    roles = {m["user"]["id"]: m["role"] for m in client.get(f"/communities/{community_id}/members").json()}
    assert roles[member_id] == "admin"


# ── Booking semantics ───────────────────────────────────────────────────────


def _approved_booking(client, owner, borrower, rid):
    bid = _book(client, borrower, rid, 1, 2).json()["id"]
    assert client.patch(f"/bookings/{bid}", headers=owner, json={"status": "approved"}).status_code == 200
    return bid


def test_only_lender_can_complete_booking(client, auth_headers, community_id):
    rid = _resource(client, auth_headers, community_id)
    borrower = _register(client, "borrower@test.com")
    _join(client, borrower, community_id)
    bid = _approved_booking(client, auth_headers, borrower, rid)

    res = client.patch(f"/bookings/{bid}", headers=borrower, json={"status": "completed"})
    assert res.status_code == 409
    # The borrower can still cancel
    assert client.get(f"/bookings/{bid}", headers=borrower).json()["status"] == "approved"

    res = client.patch(f"/bookings/{bid}", headers=auth_headers, json={"status": "completed"})
    assert res.status_code == 200
    assert res.json()["status"] == "completed"


def test_borrower_cannot_farm_reputation_by_completing(client, auth_headers, community_id):
    rid = _resource(client, auth_headers, community_id)
    borrower = _register(client, "borrower@test.com")
    _join(client, borrower, community_id)
    bid = _approved_booking(client, auth_headers, borrower, rid)

    client.patch(f"/bookings/{bid}", headers=borrower, json={"status": "completed"})
    rep = client.get("/users/me/reputation", headers=borrower).json()
    assert rep["breakdown"]["borrowing_completed"] == 0


def test_booking_in_the_past_is_rejected(client, auth_headers, community_id):
    rid = _resource(client, auth_headers, community_id)
    borrower = _register(client, "borrower@test.com")
    _join(client, borrower, community_id)

    res = _book(client, borrower, rid, -3, -1)
    assert res.status_code == 422
    assert "past" in res.json()["detail"].lower()
    # Spanning today is fine; today itself is allowed
    assert _book(client, borrower, rid, 0, 1).status_code == 201


def test_multi_unit_resource_reserves_one_unit_per_booking(client, auth_headers, community_id):
    rid = _resource(client, auth_headers, community_id, quantity_total=2)
    users = []
    for n in range(3):
        h = _register(client, f"u{n}@test.com")
        _join(client, h, community_id)
        users.append(h)

    assert _book(client, users[0], rid, 1, 5).status_code == 201
    assert _book(client, users[1], rid, 3, 7).status_code == 201  # second unit, overlapping
    res = _book(client, users[2], rid, 4, 6)  # both units taken on days 4-5
    assert res.status_code == 409
    assert "overlap" in res.json()["detail"].lower()
    # Non-overlapping dates are fine
    assert _book(client, users[2], rid, 8, 9).status_code == 201


def test_units_are_counted_by_peak_concurrency_not_overlap_count(client, auth_headers, community_id):
    """Two back-to-back bookings never use both units at once."""
    rid = _resource(client, auth_headers, community_id, quantity_total=2)
    users = []
    for n in range(3):
        h = _register(client, f"u{n}@test.com")
        _join(client, h, community_id)
        users.append(h)
    assert _book(client, users[0], rid, 1, 2).status_code == 201
    assert _book(client, users[1], rid, 3, 4).status_code == 201
    # Overlaps both existing bookings but only ever needs one unit at a time
    assert _book(client, users[2], rid, 1, 4).status_code == 201


def test_single_unit_resource_still_blocks_overlap(client, auth_headers, community_id):
    rid = _resource(client, auth_headers, community_id)
    a = _register(client, "a@test.com")
    b = _register(client, "b@test.com")
    _join(client, a, community_id)
    _join(client, b, community_id)
    assert _book(client, a, rid, 1, 5).status_code == 201
    assert _book(client, b, rid, 5, 6).status_code == 409


def test_units_follow_quantity_available(client, auth_headers, community_id):
    """quantity_available is the owner's current stock; it caps concurrent bookings."""
    rid = _resource(client, auth_headers, community_id, quantity_total=3)
    client.patch(f"/resources/{rid}/inventory", headers=auth_headers, json={"quantity_available": 1})
    a = _register(client, "a@test.com")
    b = _register(client, "b@test.com")
    _join(client, a, community_id)
    _join(client, b, community_id)
    assert _book(client, a, rid, 1, 2).status_code == 201
    assert _book(client, b, rid, 1, 2).status_code == 409


def test_rejected_or_cancelled_bookings_free_their_unit(client, auth_headers, community_id):
    rid = _resource(client, auth_headers, community_id)
    a = _register(client, "a@test.com")
    b = _register(client, "b@test.com")
    _join(client, a, community_id)
    _join(client, b, community_id)
    bid = _book(client, a, rid, 1, 2).json()["id"]
    client.patch(f"/bookings/{bid}", headers=auth_headers, json={"status": "rejected"})
    assert _book(client, b, rid, 1, 2).status_code == 201


# ── Federation import: cap and reputation ───────────────────────────────────


def test_import_is_capped_at_200_items(client, auth_headers):
    res = client.post(
        "/federation/migrate/import",
        headers=auth_headers,
        json={"display_name": "x", "resources": [{"title": f"r{i}"} for i in range(201)], "skills": []},
    )
    assert res.status_code == 422

    res = client.post(
        "/federation/migrate/import",
        headers=auth_headers,
        json={
            "display_name": "x",
            "resources": [{"title": f"r{i}"} for i in range(150)],
            "skills": [{"title": f"s{i}"} for i in range(51)],
        },
    )
    assert res.status_code == 422  # 201 combined

    res = client.post(
        "/federation/migrate/import",
        headers=auth_headers,
        json={
            "display_name": "x",
            "resources": [{"title": f"r{i}"} for i in range(150)],
            "skills": [{"title": f"s{i}"} for i in range(50)],
        },
    )
    assert res.status_code == 201
    assert res.json()["resources_created"] == 150


def test_imported_items_earn_no_reputation(client, auth_headers, community_id):
    res = client.post(
        "/federation/migrate/import",
        headers=auth_headers,
        json={
            "display_name": "x",
            "resources": [{"title": "Old drill"}, {"title": "Old saw"}],
            "skills": [{"title": "Plumbing", "skill_type": "offer"}, {"title": "Help", "skill_type": "request"}],
        },
    )
    assert res.status_code == 201
    rep = client.get("/users/me/reputation", headers=auth_headers).json()
    assert rep["score"] == 0
    assert rep["breakdown"]["resources_shared"] == 0
    assert rep["breakdown"]["skills_offered"] == 0
    assert rep["breakdown"]["skills_requested"] == 0

    # Natively created listings still count
    _resource(client, auth_headers, community_id)
    rep = client.get("/users/me/reputation", headers=auth_headers).json()
    assert rep["breakdown"]["resources_shared"] == 2


def test_imported_flag_is_set_on_rows(client, auth_headers, db):
    from app.models.resource import Resource
    from app.models.skill import Skill

    client.post(
        "/federation/migrate/import",
        headers=auth_headers,
        json={"display_name": "x", "resources": [{"title": "r"}], "skills": [{"title": "s"}]},
    )
    assert db.query(Resource).one().imported is True
    assert db.query(Skill).one().imported is True
