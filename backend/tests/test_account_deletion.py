"""Tests for DELETE /users/me (account deletion / anonymisation)."""

import datetime

from sqlalchemy import text

from app.models.activity import Activity
from app.models.booking import Booking
from app.models.community import Community, CommunityMember
from app.models.crisis import CrisisVote, EmergencyTicket
from app.models.event import Event, EventAttendee
from app.models.invite import Invite
from app.models.message import Message
from app.models.password_reset import PasswordResetToken
from app.models.resource import Resource
from app.models.review import Review
from app.models.skill import Skill
from app.models.user import User
from app.models.webhook import TelegramLinkToken, Webhook
from app.routers import users as users_router
from app.services.auth import verify_password

PASSWORD = "Testpass123"


def _register(client, email, name="User", password=PASSWORD):
    res = client.post(
        "/auth/register",
        json={"email": email, "password": password, "display_name": name, "neighbourhood": "Nowhere"},
    )
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _delete(client, headers, password=PASSWORD):
    return client.request("DELETE", "/users/me", headers=headers, json={"password": password})


def _me(client, headers):
    return client.get("/users/me", headers=headers).json()


def _community(client, headers, name="Hood"):
    res = client.post(
        "/communities", headers=headers, json={"name": name, "postal_code": "12345", "city": "Town"}
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _resource(client, headers, community_id, title="Drill"):
    res = client.post(
        "/resources",
        headers=headers,
        json={"title": title, "category": "tool", "community_id": community_id},
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _skill(client, headers, community_id, title="Piano"):
    res = client.post(
        "/skills",
        headers=headers,
        json={"title": title, "category": "music", "skill_type": "offer", "community_id": community_id},
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _booking(client, headers, resource_id, start="2031-05-01", end="2031-05-03"):
    res = client.post(
        "/bookings",
        headers=headers,
        json={"resource_id": resource_id, "start_date": start, "end_date": end},
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _set_status(client, headers, booking_id, new_status):
    res = client.patch(f"/bookings/{booking_id}", headers=headers, json={"status": new_status})
    assert res.status_code == 200, res.text


def _fk_violations(db):
    return db.execute(text("PRAGMA foreign_key_check")).fetchall()


# ── Auth / validation ─────────────────────────────────────────────


def test_delete_unauthenticated(client):
    res = client.request("DELETE", "/users/me", json={"password": PASSWORD})
    assert res.status_code == 403


def test_delete_requires_password_field(client, auth_headers):
    res = client.request("DELETE", "/users/me", headers=auth_headers, json={})
    assert res.status_code == 422
    res = client.request("DELETE", "/users/me", headers=auth_headers)
    assert res.status_code == 422


def test_delete_wrong_password_is_400_and_keeps_session(client, auth_headers, db):
    res = _delete(client, auth_headers, "Wrongpass999")
    assert res.status_code == 400
    # 400 (not 401): the client must not treat it as an expired session
    assert _delete(client, auth_headers, "").status_code == 422
    me = client.get("/users/me", headers=auth_headers)
    assert me.status_code == 200
    assert me.json()["display_name"] == "Test User"
    assert db.query(User).filter(User.email == "test@example.com").one().is_active is True


def test_token_stops_working_after_delete(client, auth_headers):
    assert _delete(client, auth_headers).status_code == 204
    assert client.get("/users/me", headers=auth_headers).status_code == 401


# ── Anonymisation ─────────────────────────────────────────────────


def test_user_is_anonymised(client, auth_headers, db):
    me = _me(client, auth_headers)
    user = db.query(User).filter(User.id == me["id"]).one()
    user.telegram_chat_id = "12345"
    user.language_code = "fr"
    user.mesh_public_key = "abc"
    db.commit()

    assert _delete(client, auth_headers).status_code == 204

    db.expire_all()
    user = db.query(User).filter(User.id == me["id"]).one()
    assert user.display_name == "Deleted user"
    assert user.email == f"deleted-{me['id']}@invalid"
    assert user.neighbourhood is None
    assert user.telegram_chat_id is None
    assert user.language_code == "en"
    assert user.mesh_public_key is None
    assert user.is_active is False
    assert not verify_password(PASSWORD, user.hashed_password)


def test_placeholder_emails_are_unique_per_user(client, db):
    a = _register(client, "a@example.com", "A")
    b = _register(client, "b@example.com", "B")
    assert _delete(client, a).status_code == 204
    assert _delete(client, b).status_code == 204
    emails = [u.email for u in db.query(User).all()]
    assert len(emails) == len(set(emails)) == 2
    assert all(e.startswith("deleted-") and e.endswith("@invalid") for e in emails)


def test_cannot_log_in_after_delete_and_email_can_be_reused(client, auth_headers):
    assert _delete(client, auth_headers).status_code == 204
    login = client.post("/auth/login", json={"email": "test@example.com", "password": PASSWORD})
    assert login.status_code == 401
    again = client.post(
        "/auth/register",
        json={"email": "test@example.com", "password": PASSWORD, "display_name": "Fresh Start"},
    )
    assert again.status_code == 201


def test_deleted_user_cannot_request_password_reset_link(client, auth_headers, db):
    assert _delete(client, auth_headers).status_code == 204
    res = client.post("/auth/password-reset/request", json={"email": "test@example.com"})
    assert res.status_code == 202
    assert db.query(PasswordResetToken).count() == 0


# ── Resources and bookings ────────────────────────────────────────


def test_resources_without_history_are_deleted(client, auth_headers, db):
    cid = _community(client, auth_headers)
    rid = _resource(client, auth_headers, cid)
    assert _delete(client, auth_headers).status_code == 204
    assert client.get(f"/resources/{rid}").status_code == 404
    assert db.query(Resource).count() == 0


def test_resource_with_booking_history_becomes_tombstone(client, auth_headers, db):
    cid = _community(client, auth_headers)
    rid = _resource(client, auth_headers, cid, "Secret Drill")
    borrower = _register(client, "borrower@example.com", "Borrower")
    client.post(f"/communities/{cid}/join", headers=borrower)
    bid = _booking(client, borrower, rid)
    _set_status(client, auth_headers, bid, "approved")
    _set_status(client, auth_headers, bid, "completed")
    assert client.post(
        "/reviews", headers=borrower, json={"booking_id": bid, "rating": 5, "comment": "great"}
    ).status_code == 201

    assert _delete(client, auth_headers).status_code == 204

    res = client.get(f"/resources/{rid}")
    assert res.status_code == 200
    data = res.json()
    assert data["title"] == "Deleted listing"
    assert data["description"] is None
    assert data["is_available"] is False
    assert data["community_id"] is None
    assert data["owner"]["display_name"] == "Deleted user"
    # the borrower's history and review are intact
    bookings = client.get("/bookings", headers=borrower).json()["items"]
    assert [b["status"] for b in bookings] == ["completed"]
    assert db.query(Review).count() == 1
    # and it no longer shows up in listings
    assert client.get("/resources", headers=borrower).json()["total"] == 0
    assert _fk_violations(db) == []


def test_bookings_on_deleted_users_resources_are_cancelled_and_borrowers_notified(
    client, auth_headers, db, monkeypatch
):
    sent: list[tuple] = []
    monkeypatch.setattr(users_router, "notify_booking_status", lambda *a: sent.append(a))

    cid = _community(client, auth_headers)
    rid = _resource(client, auth_headers, cid, "Ladder")
    b1 = _register(client, "b1@example.com", "B1")
    b2 = _register(client, "b2@example.com", "B2")
    for b in (b1, b2):
        client.post(f"/communities/{cid}/join", headers=b)
    pending = _booking(client, b1, rid, "2031-06-01", "2031-06-02")
    approved = _booking(client, b2, rid, "2031-07-01", "2031-07-02")
    _set_status(client, auth_headers, approved, "approved")

    assert _delete(client, auth_headers).status_code == 204

    db.expire_all()
    assert db.get(Booking, pending).status == "cancelled"
    assert db.get(Booking, approved).status == "cancelled"
    assert sorted(sent) == [
        ("b1@example.com", "Ladder", "cancelled"),
        ("b2@example.com", "Ladder", "cancelled"),
    ]


def test_own_pending_and_approved_borrowings_are_cancelled_history_kept(client, auth_headers, db):
    owner = _register(client, "owner@example.com", "Owner")
    cid = _community(client, owner)
    client.post(f"/communities/{cid}/join", headers=auth_headers)
    r1 = _resource(client, owner, cid, "One")
    r2 = _resource(client, owner, cid, "Two")
    r3 = _resource(client, owner, cid, "Three")
    pending = _booking(client, auth_headers, r1, "2031-01-01", "2031-01-02")
    approved = _booking(client, auth_headers, r2, "2031-02-01", "2031-02-02")
    _set_status(client, owner, approved, "approved")
    done = _booking(client, auth_headers, r3, "2031-03-01", "2031-03-02")
    _set_status(client, owner, done, "approved")
    _set_status(client, owner, done, "completed")

    assert _delete(client, auth_headers).status_code == 204

    db.expire_all()
    assert db.get(Booking, pending).status == "cancelled"
    assert db.get(Booking, approved).status == "cancelled"
    assert db.get(Booking, done).status == "completed"
    # the lender still sees all three, borrower shown as Deleted user
    items = client.get("/bookings", headers=owner).json()["items"]
    assert len(items) == 3
    assert {i["borrower"]["display_name"] for i in items} == {"Deleted user"}


# ── Skills ────────────────────────────────────────────────────────


def test_skills_deleted_and_messages_reviews_detached(client, auth_headers, db):
    cid = _community(client, auth_headers)
    sid = _skill(client, auth_headers, cid)
    other = _register(client, "other@example.com", "Other")
    client.post(f"/communities/{cid}/join", headers=other)
    me = _me(client, auth_headers)
    assert client.post(
        "/reviews/skill", headers=other, json={"skill_id": sid, "rating": 4, "comment": "nice"}
    ).status_code == 201
    msg = client.post(
        "/messages",
        headers=other,
        json={"recipient_id": me["id"], "body": "Teach me", "skill_id": sid},
    )
    assert msg.status_code == 201, msg.text

    assert _delete(client, auth_headers).status_code == 204

    db.expire_all()
    assert db.query(Skill).count() == 0
    assert db.query(Review).count() == 1
    assert db.query(Review).one().skill_id is None
    assert db.query(Message).one().skill_id is None
    assert _fk_violations(db) == []


# ── Communities ───────────────────────────────────────────────────


def test_last_admin_leaving_promotes_longest_standing_member(client, auth_headers, db):
    cid = _community(client, auth_headers)
    first = _register(client, "first@example.com", "First")
    second = _register(client, "second@example.com", "Second")
    client.post(f"/communities/{cid}/join", headers=first)
    client.post(f"/communities/{cid}/join", headers=second)
    first_id = _me(client, first)["id"]
    second_id = _me(client, second)["id"]
    # make "second" the earliest joiner explicitly
    db.query(CommunityMember).filter(CommunityMember.user_id == second_id).update(
        {CommunityMember.joined_at: datetime.datetime(2020, 1, 1)}
    )
    db.query(CommunityMember).filter(CommunityMember.user_id == first_id).update(
        {CommunityMember.joined_at: datetime.datetime(2021, 1, 1)}
    )
    db.commit()

    assert _delete(client, auth_headers).status_code == 204

    db.expire_all()
    roles = {m.user_id: m.role for m in db.query(CommunityMember).filter_by(community_id=cid)}
    assert roles == {second_id: "admin", first_id: "member"}
    assert db.get(Community, cid).is_active is True


def test_other_admin_present_means_no_promotion(client, auth_headers, db):
    cid = _community(client, auth_headers)
    co_admin = _register(client, "coadmin@example.com", "Co")
    plain = _register(client, "plain@example.com", "Plain")
    client.post(f"/communities/{cid}/join", headers=co_admin)
    client.post(f"/communities/{cid}/join", headers=plain)
    co_id = _me(client, co_admin)["id"]
    plain_id = _me(client, plain)["id"]
    db.query(CommunityMember).filter(CommunityMember.user_id == co_id).update(
        {CommunityMember.role: "admin"}
    )
    db.commit()

    assert _delete(client, auth_headers).status_code == 204

    db.expire_all()
    roles = {m.user_id: m.role for m in db.query(CommunityMember).filter_by(community_id=cid)}
    assert roles == {co_id: "admin", plain_id: "member"}


def test_member_leaving_does_not_change_roles(client, auth_headers, db):
    admin = _register(client, "admin@example.com", "Admin")
    cid = _community(client, admin)
    client.post(f"/communities/{cid}/join", headers=auth_headers)
    assert _delete(client, auth_headers).status_code == 204
    db.expire_all()
    members = db.query(CommunityMember).filter_by(community_id=cid).all()
    assert [m.role for m in members] == ["admin"]
    assert db.get(Community, cid).is_active is True


def test_community_with_no_members_left_is_deactivated(client, auth_headers, db):
    cid = _community(client, auth_headers)
    assert _delete(client, auth_headers).status_code == 204
    db.expire_all()
    assert db.query(CommunityMember).count() == 0
    community = db.get(Community, cid)
    assert community.is_active is False
    # the row stays (created_by_id still points at the anonymised user)
    assert _fk_violations(db) == []


# ── Personal artefacts removed ────────────────────────────────────


def test_webhooks_telegram_tokens_reset_tokens_votes_invites_removed(client, auth_headers, db):
    me = _me(client, auth_headers)
    other = _register(client, "other@example.com", "Other")
    other_id = _me(client, other)["id"]
    cid = _community(client, auth_headers)

    db.add_all(
        [
            Webhook(owner_type="user", owner_id=me["id"], url="https://example.com/h", secret="s" * 16,
                    event_types='["message.new"]'),
            Webhook(owner_type="user", owner_id=other_id, url="https://example.com/o", secret="s" * 16,
                    event_types='["message.new"]'),
            # a community webhook whose owner_id happens to equal the user id must survive
            Webhook(owner_type="community", owner_id=me["id"], url="https://example.com/c",
                    secret="s" * 16, event_types='["message.new"]'),
            TelegramLinkToken(token="t1" * 8, token_type="user", owner_id=me["id"],
                              expires_at=datetime.datetime(2099, 1, 1)),
            TelegramLinkToken(token="t2" * 8, token_type="user", owner_id=other_id,
                              expires_at=datetime.datetime(2099, 1, 1)),
            PasswordResetToken(user_id=me["id"], token_hash="h" * 64,
                               expires_at=datetime.datetime(2099, 1, 1)),
            CrisisVote(community_id=cid, user_id=me["id"], vote_type="activate"),
            Invite(code="abc123", community_id=cid, created_by_id=me["id"]),
        ]
    )
    db.commit()

    assert _delete(client, auth_headers).status_code == 204

    db.expire_all()
    assert [(w.owner_type, w.owner_id) for w in db.query(Webhook).order_by(Webhook.id)] == [
        ("user", other_id),
        ("community", me["id"]),
    ]
    assert [t.owner_id for t in db.query(TelegramLinkToken)] == [other_id]
    assert db.query(PasswordResetToken).count() == 0
    assert db.query(CrisisVote).count() == 0
    assert db.query(Invite).count() == 0
    assert _fk_violations(db) == []


def test_personal_activity_removed_crisis_activity_kept(client, auth_headers, db):
    me = _me(client, auth_headers)
    cid = _community(client, auth_headers)
    _resource(client, auth_headers, cid)  # writes a resource_shared activity
    db.add(Activity(event_type="ticket_created", summary="opened a ticket", actor_id=me["id"],
                    community_id=cid))
    db.commit()
    assert db.query(Activity).filter(Activity.event_type == "resource_shared").count() == 1

    assert _delete(client, auth_headers).status_code == 204

    db.expire_all()
    assert {a.event_type for a in db.query(Activity)} == {"ticket_created"}
    assert _fk_violations(db) == []


# ── Events ────────────────────────────────────────────────────────


def test_upcoming_events_deleted_past_kept_and_rsvps_removed(client, auth_headers, db):
    me = _me(client, auth_headers)
    cid = _community(client, auth_headers)
    other = _register(client, "other@example.com", "Other")
    client.post(f"/communities/{cid}/join", headers=other)

    def mk(headers, title, delta):
        res = client.post(
            "/events",
            headers=headers,
            json={
                "title": title,
                "category": "meetup",
                "start_at": (datetime.datetime.utcnow() + delta).isoformat(),
                "community_id": cid,
            },
        )
        assert res.status_code == 201, res.text
        return res.json()["id"]

    upcoming = mk(auth_headers, "Upcoming", datetime.timedelta(days=5))
    past = mk(auth_headers, "Past", datetime.timedelta(days=-5))
    others_event = mk(other, "Others", datetime.timedelta(days=6))
    assert client.post(f"/events/{upcoming}/attend", headers=other).status_code == 201
    assert client.post(f"/events/{others_event}/attend", headers=auth_headers).status_code == 201

    assert _delete(client, auth_headers).status_code == 204

    db.expire_all()
    titles = {e.title for e in db.query(Event)}
    assert titles == {"Past", "Others"}
    assert db.query(EventAttendee).count() == 0  # the upcoming event's RSVP went with it, mine was removed
    assert db.get(Event, past).organizer_id == me["id"]
    assert _fk_violations(db) == []


# ── Things that must stay ─────────────────────────────────────────


def test_messages_reviews_and_tickets_stay_and_show_deleted_user(client, auth_headers, db):
    me = _me(client, auth_headers)
    cid = _community(client, auth_headers)
    other = _register(client, "other@example.com", "Other")
    client.post(f"/communities/{cid}/join", headers=other)
    other_id = _me(client, other)["id"]

    assert client.post(
        "/messages", headers=auth_headers, json={"recipient_id": other_id, "body": "hello"}
    ).status_code == 201
    ticket = client.post(
        f"/communities/{cid}/tickets",
        headers=auth_headers,
        json={"ticket_type": "request", "title": "Need help", "description": "x", "urgency": "low"},
    )
    assert ticket.status_code == 201, ticket.text

    rid = _resource(client, other, cid)
    client.post(f"/communities/{cid}/join", headers=auth_headers)
    bid = _booking(client, auth_headers, rid)
    _set_status(client, other, bid, "approved")
    _set_status(client, other, bid, "completed")
    assert client.post(
        "/reviews", headers=auth_headers, json={"booking_id": bid, "rating": 4, "comment": "ok"}
    ).status_code == 201

    assert _delete(client, auth_headers).status_code == 204

    db.expire_all()
    assert db.query(Message).count() == 1
    assert db.query(Review).count() == 1
    assert db.query(EmergencyTicket).count() == 1
    thread = client.get(f"/messages?partner_id={me['id']}", headers=other).json()
    assert thread["items"][0]["sender"]["display_name"] == "Deleted user"
    reviews = client.get(f"/reviews/user/{other_id}").json()
    assert reviews[0]["reviewer"]["display_name"] == "Deleted user"
    tickets = client.get(f"/communities/{cid}/tickets", headers=other).json()
    assert tickets["items"][0]["author"]["display_name"] == "Deleted user"
    assert "test@example.com" not in str(tickets)


def test_ticket_assigned_to_deleted_user_is_released(client, auth_headers, db):
    me = _me(client, auth_headers)
    cid = _community(client, auth_headers)
    other = _register(client, "other@example.com", "Other")
    client.post(f"/communities/{cid}/join", headers=other)
    created = client.post(
        f"/communities/{cid}/tickets",
        headers=other,
        json={"ticket_type": "request", "title": "Need help", "description": "x", "urgency": "low"},
    ).json()
    ticket = db.get(EmergencyTicket, created["id"])
    ticket.assigned_to_id = me["id"]
    ticket.status = "in_progress"
    db.commit()

    assert _delete(client, auth_headers).status_code == 204

    db.expire_all()
    ticket = db.get(EmergencyTicket, created["id"])
    assert ticket.assigned_to_id is None
    assert ticket.status == "open"


def test_full_scenario_leaves_no_foreign_key_violations(client, auth_headers, db):
    """A user who owns a bit of everything can be deleted cleanly (no orphans)."""
    cid = _community(client, auth_headers)
    other = _register(client, "other@example.com", "Other")
    client.post(f"/communities/{cid}/join", headers=other)
    rid = _resource(client, auth_headers, cid)
    _resource(client, auth_headers, cid, "Unused")
    sid = _skill(client, auth_headers, cid)
    bid = _booking(client, other, rid)
    _set_status(client, auth_headers, bid, "approved")
    client.post("/reviews/skill", headers=other, json={"skill_id": sid, "rating": 5})

    assert _delete(client, auth_headers).status_code == 204
    assert _fk_violations(db) == []
