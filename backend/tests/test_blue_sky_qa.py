"""Regression tests for Blue Sky QA findings (privacy, authorization, validation, merge, timezones)."""

import datetime


def _register(client, email, name="User"):
    res = client.post(
        "/auth/register",
        json={"email": email, "password": "Password123", "display_name": name},
    )
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _join(client, headers, community_id):
    res = client.post(f"/communities/{community_id}/join", headers=headers)
    assert res.status_code == 200
    return res


def _resource(client, headers, community_id, title="Drill"):
    res = client.post(
        "/resources",
        headers=headers,
        json={"title": title, "category": "tool", "community_id": community_id},
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


# ── Privacy: public user payloads never expose email / telegram id ───────────


def _assert_no_pii(obj):
    if isinstance(obj, dict):
        assert "email" not in obj
        assert "telegram_chat_id" not in obj
        for v in obj.values():
            _assert_no_pii(v)
    elif isinstance(obj, list):
        for v in obj:
            _assert_no_pii(v)


def test_public_endpoints_do_not_leak_email(client, auth_headers, community_id):
    rid = _resource(client, auth_headers, community_id)
    borrower = _register(client, "b@test.com", "Borrower")
    _join(client, borrower, community_id)
    client.post(
        "/bookings",
        headers=borrower,
        json={"resource_id": rid, "start_date": "2026-03-01", "end_date": "2026-03-02"},
    )
    client.post(
        "/skills",
        headers=auth_headers,
        json={"title": "Plumbing", "category": "repairs", "skill_type": "offer", "community_id": community_id},
    )

    # Anonymous callers
    for url in (
        f"/resources/{rid}",
        f"/resources?community_id={community_id}",
        "/skills",
        f"/communities/{community_id}",
        f"/communities/{community_id}/members",
        f"/activity?community_id={community_id}",
        f"/bookings/resource/{rid}/calendar?month=3&year=2026",
    ):
        res = client.get(url)
        assert res.status_code == 200, url
        assert res.json(), url
        _assert_no_pii(res.json())


def test_me_endpoint_still_returns_email(client, auth_headers):
    res = client.get("/users/me", headers=auth_headers)
    assert res.json()["email"] == "test@example.com"


# ── Email case-insensitivity ─────────────────────────────────────────────────


def test_register_email_is_case_insensitive(client):
    first = client.post(
        "/auth/register",
        json={"email": "Case@Example.com", "password": "Password123", "display_name": "A"},
    )
    assert first.status_code == 201
    dup = client.post(
        "/auth/register",
        json={"email": "case@example.com", "password": "Password123", "display_name": "B"},
    )
    assert dup.status_code == 409


def test_login_email_is_case_insensitive(client):
    client.post(
        "/auth/register",
        json={"email": "Mixed@Example.com", "password": "Password123", "display_name": "A"},
    )
    for email in ("mixed@example.com", "MIXED@EXAMPLE.COM", "Mixed@Example.com"):
        res = client.post("/auth/login", json={"email": email, "password": "Password123"})
        assert res.status_code == 200, email


def test_change_email_duplicate_is_case_insensitive(client, auth_headers):
    client.post(
        "/auth/register",
        json={"email": "taken@example.com", "password": "Password123", "display_name": "T"},
    )
    res = client.post(
        "/users/me/change-email",
        headers=auth_headers,
        json={"new_email": "Taken@Example.com", "password": "Testpass123"},
    )
    assert res.status_code == 422


# ── change-password / change-email: wrong password must not look like an expired session ──


def test_change_password_wrong_current_is_400(client, auth_headers):
    res = client.post(
        "/users/me/change-password",
        headers=auth_headers,
        json={"current_password": "Wrongpass123", "new_password": "Newpass123"},
    )
    assert res.status_code == 400


def test_change_email_wrong_password_is_400(client, auth_headers):
    res = client.post(
        "/users/me/change-email",
        headers=auth_headers,
        json={"new_email": "new@example.com", "password": "Wrongpass123"},
    )
    assert res.status_code == 400


# ── Whitespace-only text is rejected ─────────────────────────────────────────


def test_whitespace_display_name_rejected(client, auth_headers):
    res = client.post(
        "/auth/register",
        json={"email": "ws@example.com", "password": "Password123", "display_name": "   "},
    )
    assert res.status_code == 422
    res = client.patch("/users/me", headers=auth_headers, json={"display_name": "   "})
    assert res.status_code == 422


def test_whitespace_titles_rejected(client, auth_headers, community_id):
    res = client.post(
        "/resources", headers=auth_headers, json={"title": "   ", "category": "tool", "community_id": community_id}
    )
    assert res.status_code == 422
    res = client.post(
        "/skills",
        headers=auth_headers,
        json={"title": "  ", "category": "tech", "skill_type": "offer", "community_id": community_id},
    )
    assert res.status_code == 422


def test_titles_are_stripped(client, auth_headers, community_id):
    res = client.post(
        "/resources",
        headers=auth_headers,
        json={"title": "  Drill  ", "category": "tool", "community_id": community_id},
    )
    assert res.json()["title"] == "Drill"


# ── Posting into a community requires membership ─────────────────────────────


def test_create_resource_in_foreign_community_forbidden(client, auth_headers, community_id):
    outsider = _register(client, "out@test.com", "Outsider")
    res = client.post(
        "/resources", headers=outsider, json={"title": "Spam", "category": "tool", "community_id": community_id}
    )
    assert res.status_code == 403


def test_create_resource_in_missing_community_404(client, auth_headers):
    res = client.post(
        "/resources", headers=auth_headers, json={"title": "Ghost", "category": "tool", "community_id": 9999}
    )
    assert res.status_code == 404


def test_create_skill_in_foreign_community_forbidden(client, auth_headers, community_id):
    outsider = _register(client, "out@test.com", "Outsider")
    res = client.post(
        "/skills",
        headers=outsider,
        json={"title": "Spam", "category": "tech", "skill_type": "offer", "community_id": community_id},
    )
    assert res.status_code == 403


# ── Deleting resources / skills ──────────────────────────────────────────────


def test_delete_resource_with_active_booking_blocked(client, auth_headers, community_id):
    rid = _resource(client, auth_headers, community_id)
    borrower = _register(client, "b@test.com", "Borrower")
    _join(client, borrower, community_id)
    booking = client.post(
        "/bookings",
        headers=borrower,
        json={"resource_id": rid, "start_date": "2026-03-01", "end_date": "2026-03-02"},
    ).json()

    res = client.delete(f"/resources/{rid}", headers=auth_headers)
    assert res.status_code == 409
    assert client.get(f"/resources/{rid}").status_code == 200

    client.patch(f"/bookings/{booking['id']}", headers=auth_headers, json={"status": "rejected"})
    res = client.delete(f"/resources/{rid}", headers=auth_headers)
    assert res.status_code == 204


def test_delete_skill_with_messages_and_reviews(client, auth_headers, community_id):
    skill = client.post(
        "/skills",
        headers=auth_headers,
        json={"title": "Plumbing", "category": "repairs", "skill_type": "offer", "community_id": community_id},
    ).json()
    other = _register(client, "o@test.com", "Other")
    _join(client, other, community_id)
    me = client.get("/users/me", headers=auth_headers).json()
    client.post(
        "/messages", headers=other, json={"recipient_id": me["id"], "body": "hi", "skill_id": skill["id"]}
    )
    client.post("/reviews/skill", headers=other, json={"skill_id": skill["id"], "rating": 5})

    res = client.delete(f"/skills/{skill['id']}", headers=auth_headers)
    assert res.status_code == 204
    # The endorsement and the message survive the listing
    msgs = client.get("/messages", headers=auth_headers).json()
    assert msgs["total"] == 1 and msgs["items"][0]["skill_id"] is None


# ── Merge moves content and rejects dead targets ─────────────────────────────


def test_merge_moves_content_to_target(client, auth_headers):
    source = client.post(
        "/communities", headers=auth_headers, json={"name": "Src", "postal_code": "1", "city": "X"}
    ).json()["id"]
    other_admin = _register(client, "t@test.com", "Target Admin")
    target = client.post(
        "/communities", headers=other_admin, json={"name": "Tgt", "postal_code": "1", "city": "X"}
    ).json()["id"]

    rid = _resource(client, auth_headers, source)
    client.post(
        "/skills",
        headers=auth_headers,
        json={"title": "S", "category": "tech", "skill_type": "offer", "community_id": source},
    )
    client.post(
        "/events",
        headers=auth_headers,
        json={"title": "E", "category": "meetup", "start_at": "2030-01-01T10:00:00", "community_id": source},
    )

    res = client.post("/communities/merge", headers=auth_headers, json={"source_id": source, "target_id": target})
    assert res.status_code == 200

    assert client.get(f"/resources/{rid}").json()["community_id"] == target
    assert client.get(f"/resources?community_id={target}").json()["total"] == 1
    assert client.get(f"/skills?community_id={target}").json()["total"] == 1
    assert client.get(f"/events?community_id={target}").json()["total"] == 1
    assert client.get(f"/resources?community_id={source}").json()["total"] == 0


def test_merge_into_merged_target_rejected(client, auth_headers):
    a = client.post("/communities", headers=auth_headers, json={"name": "A", "postal_code": "1", "city": "X"}).json()["id"]
    b = client.post("/communities", headers=auth_headers, json={"name": "B", "postal_code": "1", "city": "X"}).json()["id"]
    c = client.post("/communities", headers=auth_headers, json={"name": "C", "postal_code": "1", "city": "X"}).json()["id"]
    assert client.post("/communities/merge", headers=auth_headers, json={"source_id": a, "target_id": b}).status_code == 200
    res = client.post("/communities/merge", headers=auth_headers, json={"source_id": c, "target_id": a})
    assert res.status_code == 409


# ── Events: time validation and timezone handling ────────────────────────────


def _event(community_id, **kw):
    body = {
        "title": "Meet",
        "category": "meetup",
        "start_at": "2030-01-01T10:00:00",
        "community_id": community_id,
    }
    body.update(kw)
    return body


def test_event_end_before_start_rejected(client, auth_headers, community_id):
    res = client.post(
        "/events",
        headers=auth_headers,
        json=_event(community_id, end_at="2030-01-01T09:00:00"),
    )
    assert res.status_code == 422


def test_event_end_before_start_rejected_with_mixed_timezones(client, auth_headers, community_id):
    res = client.post(
        "/events",
        headers=auth_headers,
        json=_event(community_id, start_at="2030-01-01T10:00:00Z", end_at="2030-01-01T09:00:00"),
    )
    assert res.status_code == 422


def test_event_update_end_before_existing_start_rejected(client, auth_headers, community_id):
    eid = client.post("/events", headers=auth_headers, json=_event(community_id)).json()["id"]
    res = client.patch(f"/events/{eid}", headers=auth_headers, json={"end_at": "2030-01-01T08:00:00"})
    assert res.status_code == 422
    assert client.get(f"/events/{eid}").json()["end_at"] is None


def test_event_datetimes_are_serialised_as_utc(client, auth_headers, community_id):
    res = client.post(
        "/events",
        headers=auth_headers,
        json=_event(community_id, start_at="2030-01-01T10:00:00+02:00"),
    )
    assert res.status_code == 201
    # +02:00 is converted to UTC and marked with Z so browsers do not treat it as local time
    assert res.json()["start_at"] == "2030-01-01T08:00:00Z"
    assert res.json()["created_at"].endswith("Z")


def test_event_max_attendees_cannot_drop_below_attendees(client, auth_headers, community_id):
    eid = client.post("/events", headers=auth_headers, json=_event(community_id)).json()["id"]
    other = _register(client, "o@test.com", "Other")
    client.post(f"/events/{eid}/attend", headers=other)
    client.post(f"/events/{eid}/attend", headers=auth_headers)
    res = client.patch(f"/events/{eid}", headers=auth_headers, json={"max_attendees": 1})
    assert res.status_code == 409


# ── Invite / community validation ────────────────────────────────────────────


def test_invite_rejects_non_positive_limits(client, auth_headers, community_id):
    res = client.post("/invites", headers=auth_headers, json={"community_id": community_id, "max_uses": 0})
    assert res.status_code == 422
    res = client.post("/invites", headers=auth_headers, json={"community_id": community_id, "expires_in_hours": -5})
    assert res.status_code == 422


def test_community_coordinates_validated(client, auth_headers):
    res = client.post(
        "/communities",
        headers=auth_headers,
        json={"name": "Bad", "postal_code": "1", "city": "X", "latitude": 999, "longitude": 10},
    )
    assert res.status_code == 422


# ── Data import sanitises imported values ────────────────────────────────────


def test_import_sanitises_invalid_values(client, auth_headers):
    res = client.post(
        "/federation/migrate/import",
        headers=auth_headers,
        json={
            "display_name": "x",
            "resources": [{"title": "t" * 300, "category": "zzz", "condition": "broken"}],
            "skills": [{"title": "", "category": "zzz", "skill_type": "bogus"}],
        },
    )
    assert res.status_code == 201
    export = client.get("/federation/export/my-data", headers=auth_headers).json()
    assert len(export["resources"][0]["title"]) == 200
    assert export["resources"][0]["category"] == "other"
    assert export["resources"][0]["condition"] is None
    assert export["skills"][0]["title"] == "Imported Skill"
    assert export["skills"][0]["category"] == "other"
    assert export["skills"][0]["skill_type"] == "offer"
