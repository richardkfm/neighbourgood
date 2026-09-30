"""Tests for the data export (lender side, no foreign emails) and owner edits of resources/skills."""

import json


def _register(client, email, name="User"):
    res = client.post(
        "/auth/register",
        json={"email": email, "password": "Password123", "display_name": name},
    )
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _community(client, headers):
    res = client.post(
        "/communities",
        headers=headers,
        json={"name": "Hood", "postal_code": "12345", "city": "Town"},
    )
    return res.json()["id"]


def _resource(client, headers, cid, title="Drill"):
    res = client.post(
        "/resources", headers=headers, json={"title": title, "category": "tool", "community_id": cid}
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _booking(client, headers, rid, start, end):
    res = client.post(
        "/bookings", headers=headers, json={"resource_id": rid, "start_date": start, "end_date": end}
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


# ── Export ────────────────────────────────────────────────────────


def test_export_includes_lender_side_bookings_separately(client, auth_headers):
    cid = _community(client, auth_headers)
    borrower = _register(client, "borrower@example.com", "Bea Borrower")
    client.post(f"/communities/{cid}/join", headers=borrower)

    # I lend "Drill"; someone else lends "Saw" to me
    drill = _resource(client, auth_headers, cid, "Drill")
    saw = _resource(client, borrower, cid, "Saw")
    _booking(client, borrower, drill, "2031-01-01", "2031-01-03")
    _booking(client, auth_headers, saw, "2031-02-01", "2031-02-02")

    data = client.get("/federation/export/my-data", headers=auth_headers).json()

    assert [b["resource_title"] for b in data["bookings"]] == ["Saw"]
    assert {b["role"] for b in data["bookings"]} == {"borrower"}

    assert [b["resource_title"] for b in data["lending_bookings"]] == ["Drill"]
    lent = data["lending_bookings"][0]
    assert lent["role"] == "lender"
    assert lent["borrower_display_name"] == "Bea Borrower"
    assert lent["start_date"] == "2031-01-01"
    assert lent["status"] == "pending"


def test_export_lists_are_empty_when_no_bookings(client, auth_headers):
    data = client.get("/federation/export/my-data", headers=auth_headers).json()
    assert data["bookings"] == []
    assert data["lending_bookings"] == []


def test_export_never_contains_other_users_emails(client, auth_headers):
    cid = _community(client, auth_headers)
    other = _register(client, "secret.neighbour@example.com", "Nosy Neighbour")
    client.post(f"/communities/{cid}/join", headers=other)
    me = client.get("/users/me", headers=auth_headers).json()
    other_id = client.get("/users/me", headers=other).json()["id"]

    mine = _resource(client, auth_headers, cid, "Mine")
    theirs = _resource(client, other, cid, "Theirs")
    lend_bid = _booking(client, other, mine, "2031-01-01", "2031-01-02")
    borrow_bid = _booking(client, auth_headers, theirs, "2031-03-01", "2031-03-02")
    client.patch(f"/bookings/{lend_bid}", headers=auth_headers, json={"status": "approved"})
    client.patch(f"/bookings/{lend_bid}", headers=other, json={"status": "completed"})
    client.post("/reviews", headers=auth_headers, json={"booking_id": lend_bid, "rating": 5})
    client.post("/messages", headers=other, json={"recipient_id": me["id"], "body": "hi there"})
    client.post("/messages", headers=auth_headers, json={"recipient_id": other_id, "body": "yo"})
    assert borrow_bid

    res = client.get("/federation/export/my-data", headers=auth_headers)
    assert res.status_code == 200
    text = json.dumps(res.json())
    assert "secret.neighbour@example.com" not in text
    assert "example.com" not in text.replace("test@example.com", "")
    # own email is fine, and the conversation is there
    assert res.json()["user"]["email"] == "test@example.com"
    assert len(res.json()["messages"]) == 2


def test_export_only_contains_my_lending_bookings(client, auth_headers):
    cid = _community(client, auth_headers)
    other = _register(client, "other@example.com", "Other")
    third = _register(client, "third@example.com", "Third")
    for h in (other, third):
        client.post(f"/communities/{cid}/join", headers=h)
    others_item = _resource(client, other, cid, "Others")
    _booking(client, third, others_item, "2031-01-01", "2031-01-02")

    data = client.get("/federation/export/my-data", headers=auth_headers).json()
    assert data["bookings"] == []
    assert data["lending_bookings"] == []


# ── Editing resources ─────────────────────────────────────────────


def test_owner_can_edit_resource_fields(client, auth_headers):
    cid = _community(client, auth_headers)
    rid = _resource(client, auth_headers, cid)
    res = client.patch(
        f"/resources/{rid}",
        headers=auth_headers,
        json={
            "title": "Better Drill",
            "description": "Cordless",
            "category": "electronics",
            "condition": "fair",
            "is_available": False,
            "reorder_threshold": 2,
        },
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["title"] == "Better Drill"
    assert data["description"] == "Cordless"
    assert data["category"] == "electronics"
    assert data["condition"] == "fair"
    assert data["is_available"] is False
    assert data["reorder_threshold"] == 2


def test_resource_description_and_condition_can_be_cleared_with_null(client, auth_headers):
    cid = _community(client, auth_headers)
    rid = client.post(
        "/resources",
        headers=auth_headers,
        json={"title": "Drill", "category": "tool", "community_id": cid,
              "description": "old text", "condition": "good"},
    ).json()["id"]
    res = client.patch(
        f"/resources/{rid}", headers=auth_headers, json={"description": None, "condition": None}
    )
    assert res.status_code == 200
    assert res.json()["description"] is None
    assert res.json()["condition"] is None


def test_resource_omitted_fields_are_untouched(client, auth_headers):
    cid = _community(client, auth_headers)
    rid = client.post(
        "/resources",
        headers=auth_headers,
        json={"title": "Drill", "category": "tool", "community_id": cid,
              "description": "keep me", "condition": "good"},
    ).json()["id"]
    res = client.patch(f"/resources/{rid}", headers=auth_headers, json={"title": "Renamed"})
    assert res.json()["description"] == "keep me"
    assert res.json()["condition"] == "good"


def test_resource_edit_by_non_owner_403(client, auth_headers):
    cid = _community(client, auth_headers)
    rid = _resource(client, auth_headers, cid)
    other = _register(client, "other@example.com", "Other")
    client.post(f"/communities/{cid}/join", headers=other)
    res = client.patch(f"/resources/{rid}", headers=other, json={"title": "Hijacked"})
    assert res.status_code == 403
    assert client.get(f"/resources/{rid}").json()["title"] == "Drill"


def test_resource_edit_unauthenticated_403(client, auth_headers):
    cid = _community(client, auth_headers)
    rid = _resource(client, auth_headers, cid)
    assert client.patch(f"/resources/{rid}", json={"title": "x"}).status_code == 403


def test_resource_edit_not_found_404(client, auth_headers):
    assert client.patch("/resources/99999", headers=auth_headers, json={"title": "x"}).status_code == 404


def test_resource_edit_validation_422(client, auth_headers):
    cid = _community(client, auth_headers)
    rid = _resource(client, auth_headers, cid)
    bad_payloads = [
        {"title": ""},
        {"title": "x" * 201},
        {"description": "x" * 5001},
        {"category": "nonsense"},
        {"condition": "shiny"},
        {"reorder_threshold": -1},
    ]
    for payload in bad_payloads:
        res = client.patch(f"/resources/{rid}", headers=auth_headers, json=payload)
        assert res.status_code == 422, payload


# ── Editing skills ────────────────────────────────────────────────


def _skill(client, headers, cid):
    res = client.post(
        "/skills",
        headers=headers,
        json={"title": "Piano", "category": "music", "skill_type": "offer",
              "description": "Lessons", "community_id": cid},
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def test_owner_can_edit_skill(client, auth_headers):
    cid = _community(client, auth_headers)
    sid = _skill(client, auth_headers, cid)
    res = client.patch(
        f"/skills/{sid}",
        headers=auth_headers,
        json={"title": "Guitar", "description": "Acoustic", "category": "tech", "skill_type": "request"},
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert (data["title"], data["description"], data["category"], data["skill_type"]) == (
        "Guitar", "Acoustic", "tech", "request",
    )


def test_skill_description_can_be_cleared_with_null(client, auth_headers):
    cid = _community(client, auth_headers)
    sid = _skill(client, auth_headers, cid)
    res = client.patch(f"/skills/{sid}", headers=auth_headers, json={"description": None})
    assert res.status_code == 200
    assert res.json()["description"] is None


def test_skill_edit_by_non_owner_403(client, auth_headers):
    cid = _community(client, auth_headers)
    sid = _skill(client, auth_headers, cid)
    other = _register(client, "other@example.com", "Other")
    client.post(f"/communities/{cid}/join", headers=other)
    assert client.patch(f"/skills/{sid}", headers=other, json={"title": "x"}).status_code == 403


def test_skill_edit_unauthenticated_and_not_found(client, auth_headers):
    cid = _community(client, auth_headers)
    sid = _skill(client, auth_headers, cid)
    assert client.patch(f"/skills/{sid}", json={"title": "x"}).status_code == 403
    assert client.patch("/skills/99999", headers=auth_headers, json={"title": "x"}).status_code == 404


def test_skill_edit_validation_422(client, auth_headers):
    cid = _community(client, auth_headers)
    sid = _skill(client, auth_headers, cid)
    for payload in ({"title": ""}, {"category": "nonsense"}, {"skill_type": "trade"},
                    {"description": "x" * 5001}):
        res = client.patch(f"/skills/{sid}", headers=auth_headers, json=payload)
        assert res.status_code == 422, payload
