"""Tests for in-app messaging endpoints."""


def _register(client, email, name="User"):
    """Helper: register a user and return auth headers."""
    res = client.post(
        "/auth/register",
        json={"email": email, "password": "Password123", "display_name": name},
    )
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _get_user_id(client, headers):
    res = client.get("/users/me", headers=headers)
    return res.json()["id"]


def _make_community_pair(client, alice_headers, bob_headers):
    """Create a community with alice and bob as members so they can message."""
    res = client.post(
        "/communities",
        headers=alice_headers,
        json={"name": "Msg Test", "postal_code": "10115", "city": "Berlin"},
    )
    cid = res.json()["id"]
    client.post(f"/communities/{cid}/join", headers=bob_headers)
    return cid


def _make_community_trio(client, alice_headers, bob_headers, carol_headers):
    """Create a community with alice, bob and carol as members."""
    res = client.post(
        "/communities",
        headers=alice_headers,
        json={"name": "Trio Test", "postal_code": "10115", "city": "Berlin"},
    )
    cid = res.json()["id"]
    client.post(f"/communities/{cid}/join", headers=bob_headers)
    client.post(f"/communities/{cid}/join", headers=carol_headers)
    return cid


# ── Send message ────────────────────────────────────────────────────


def test_send_message(client):
    alice = _register(client, "alice@test.com", "Alice")
    bob = _register(client, "bob@test.com", "Bob")
    bob_id = _get_user_id(client, bob)
    _make_community_pair(client, alice, bob)

    res = client.post(
        "/messages",
        headers=alice,
        json={"recipient_id": bob_id, "body": "Hello Bob!"},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["body"] == "Hello Bob!"
    assert data["recipient_id"] == bob_id
    assert data["is_read"] is False
    assert data["sender"]["display_name"] == "Alice"


def test_send_message_blocked_without_shared_community(client):
    alice = _register(client, "alice@test.com", "Alice")
    bob = _register(client, "bob@test.com", "Bob")
    bob_id = _get_user_id(client, bob)

    res = client.post(
        "/messages",
        headers=alice,
        json={"recipient_id": bob_id, "body": "Hello!"},
    )
    assert res.status_code == 403
    assert "communities" in res.json()["detail"].lower()


def test_send_message_to_self_rejected(client):
    alice = _register(client, "alice@test.com", "Alice")
    alice_id = _get_user_id(client, alice)

    res = client.post(
        "/messages",
        headers=alice,
        json={"recipient_id": alice_id, "body": "Talking to myself"},
    )
    assert res.status_code == 422


def test_send_message_recipient_not_found(client):
    alice = _register(client, "alice@test.com", "Alice")

    res = client.post(
        "/messages",
        headers=alice,
        json={"recipient_id": 9999, "body": "Hello?"},
    )
    assert res.status_code == 404


def test_send_message_requires_auth(client):
    res = client.post(
        "/messages",
        json={"recipient_id": 1, "body": "Hello"},
    )
    assert res.status_code == 403


def test_send_message_with_skill_id(client, auth_headers):
    bob = _register(client, "bob@test.com", "Bob")
    bob_id = _get_user_id(client, bob)
    cid = _make_community_pair(client, auth_headers, bob)

    # Create a skill for context
    s = client.post(
        "/skills",
        headers=auth_headers,
        json={"title": "Python tutoring", "category": "tutoring", "skill_type": "offer", "community_id": cid},
    )
    skill_id = s.json()["id"]

    res = client.post(
        "/messages",
        headers=bob,
        json={"recipient_id": _get_user_id(client, auth_headers), "body": "Hi, I'd like to learn Python!", "skill_id": skill_id},
    )
    assert res.status_code == 201
    assert res.json()["skill_id"] == skill_id


def test_list_messages_filter_by_skill(client, auth_headers):
    bob = _register(client, "bob@test.com", "Bob")
    bob_id = _get_user_id(client, bob)
    cid = _make_community_pair(client, auth_headers, bob)

    s = client.post(
        "/skills",
        headers=auth_headers,
        json={"title": "Cooking basics", "category": "cooking", "skill_type": "offer", "community_id": cid},
    )
    skill_id = s.json()["id"]

    client.post("/messages", headers=auth_headers, json={"recipient_id": bob_id, "body": "About cooking class", "skill_id": skill_id})
    client.post("/messages", headers=auth_headers, json={"recipient_id": bob_id, "body": "Unrelated message"})

    res = client.get(f"/messages?skill_id={skill_id}", headers=auth_headers)
    assert res.json()["total"] == 1
    assert res.json()["items"][0]["body"] == "About cooking class"


def test_send_message_with_booking_id(client, auth_headers):
    bob = _register(client, "bob@test.com", "Bob")
    bob_id = _get_user_id(client, bob)
    cid = _make_community_pair(client, auth_headers, bob)

    # Create resource and booking for context
    r = client.post(
        "/resources",
        headers=auth_headers,
        json={"title": "Drill", "category": "tool", "community_id": cid},
    )
    resource_id = r.json()["id"]
    b = client.post(
        "/bookings",
        headers=bob,
        json={
            "resource_id": resource_id,
            "start_date": "2026-04-01",
            "end_date": "2026-04-05",
        },
    )
    booking_id = b.json()["id"]

    res = client.post(
        "/messages",
        headers=auth_headers,
        json={
            "recipient_id": bob_id,
            "body": "About your booking request...",
            "booking_id": booking_id,
        },
    )
    assert res.status_code == 201
    assert res.json()["booking_id"] == booking_id


# ── Contacts ───────────────────────────────────────────────────────


def test_list_messageable_contacts(client):
    alice = _register(client, "alice@test.com", "Alice")
    bob = _register(client, "bob@test.com", "Bob")
    _make_community_pair(client, alice, bob)

    res = client.get("/messages/contacts", headers=alice)
    assert res.status_code == 200
    names = {c["display_name"] for c in res.json()}
    assert "Bob" in names


def test_contacts_empty_without_community(client):
    alice = _register(client, "alice@test.com", "Alice")

    res = client.get("/messages/contacts", headers=alice)
    assert res.status_code == 200
    assert res.json() == []


# ── List messages ───────────────────────────────────────────────────


def test_list_messages(client):
    alice = _register(client, "alice@test.com", "Alice")
    bob = _register(client, "bob@test.com", "Bob")
    bob_id = _get_user_id(client, bob)
    alice_id = _get_user_id(client, alice)
    _make_community_pair(client, alice, bob)

    # Alice sends to Bob
    client.post(
        "/messages",
        headers=alice,
        json={"recipient_id": bob_id, "body": "Hi Bob!"},
    )
    # Bob sends to Alice
    client.post(
        "/messages",
        headers=bob,
        json={"recipient_id": alice_id, "body": "Hi Alice!"},
    )

    # Alice sees both messages
    res = client.get("/messages", headers=alice)
    assert res.status_code == 200
    assert res.json()["total"] == 2

    # Bob sees both messages
    res = client.get("/messages", headers=bob)
    assert res.json()["total"] == 2


def test_list_messages_filter_by_partner(client):
    alice = _register(client, "alice@test.com", "Alice")
    bob = _register(client, "bob@test.com", "Bob")
    carol = _register(client, "carol@test.com", "Carol")
    bob_id = _get_user_id(client, bob)
    carol_id = _get_user_id(client, carol)
    _make_community_trio(client, alice, bob, carol)

    client.post("/messages", headers=alice, json={"recipient_id": bob_id, "body": "Hi Bob"})
    client.post("/messages", headers=alice, json={"recipient_id": carol_id, "body": "Hi Carol"})

    res = client.get(f"/messages?partner_id={bob_id}", headers=alice)
    assert res.json()["total"] == 1
    assert res.json()["items"][0]["body"] == "Hi Bob"


def test_list_messages_filter_by_booking(client, auth_headers):
    bob = _register(client, "bob@test.com", "Bob")
    bob_id = _get_user_id(client, bob)
    cid = _make_community_pair(client, auth_headers, bob)

    # Create resource and booking
    r = client.post("/resources", headers=auth_headers, json={"title": "Saw", "category": "tool", "community_id": cid})
    resource_id = r.json()["id"]
    b = client.post(
        "/bookings",
        headers=bob,
        json={"resource_id": resource_id, "start_date": "2026-04-01", "end_date": "2026-04-05"},
    )
    booking_id = b.json()["id"]

    # Send messages with and without booking context
    client.post("/messages", headers=auth_headers, json={"recipient_id": bob_id, "body": "About drill", "booking_id": booking_id})
    client.post("/messages", headers=auth_headers, json={"recipient_id": bob_id, "body": "General chat"})

    res = client.get(f"/messages?booking_id={booking_id}", headers=auth_headers)
    assert res.json()["total"] == 1
    assert res.json()["items"][0]["body"] == "About drill"


# ── Conversations ───────────────────────────────────────────────────


def test_list_conversations(client):
    alice = _register(client, "alice@test.com", "Alice")
    bob = _register(client, "bob@test.com", "Bob")
    carol = _register(client, "carol@test.com", "Carol")
    bob_id = _get_user_id(client, bob)
    carol_id = _get_user_id(client, carol)
    _make_community_trio(client, alice, bob, carol)

    client.post("/messages", headers=alice, json={"recipient_id": bob_id, "body": "Hi Bob"})
    client.post("/messages", headers=alice, json={"recipient_id": carol_id, "body": "Hi Carol"})

    res = client.get("/messages/conversations", headers=alice)
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 2
    names = {c["partner"]["display_name"] for c in data}
    assert names == {"Bob", "Carol"}


# ── Unread count ────────────────────────────────────────────────────


def test_unread_count(client):
    alice = _register(client, "alice@test.com", "Alice")
    bob = _register(client, "bob@test.com", "Bob")
    bob_id = _get_user_id(client, bob)
    _make_community_pair(client, alice, bob)

    # No unread initially
    res = client.get("/messages/unread", headers=bob)
    assert res.json()["count"] == 0

    # Alice sends to Bob
    client.post("/messages", headers=alice, json={"recipient_id": bob_id, "body": "Hello!"})
    client.post("/messages", headers=alice, json={"recipient_id": bob_id, "body": "Are you there?"})

    res = client.get("/messages/unread", headers=bob)
    assert res.json()["count"] == 2


# ── Mark as read ────────────────────────────────────────────────────


def test_mark_message_as_read(client):
    alice = _register(client, "alice@test.com", "Alice")
    bob = _register(client, "bob@test.com", "Bob")
    bob_id = _get_user_id(client, bob)
    _make_community_pair(client, alice, bob)

    create_res = client.post("/messages", headers=alice, json={"recipient_id": bob_id, "body": "Read me"})
    msg_id = create_res.json()["id"]

    res = client.patch(f"/messages/{msg_id}/read", headers=bob)
    assert res.status_code == 200
    assert res.json()["is_read"] is True


def test_mark_message_read_not_recipient(client):
    alice = _register(client, "alice@test.com", "Alice")
    bob = _register(client, "bob@test.com", "Bob")
    bob_id = _get_user_id(client, bob)
    _make_community_pair(client, alice, bob)

    create_res = client.post("/messages", headers=alice, json={"recipient_id": bob_id, "body": "Can't read this"})
    msg_id = create_res.json()["id"]

    # Alice (sender) tries to mark as read — should fail
    res = client.patch(f"/messages/{msg_id}/read", headers=alice)
    assert res.status_code == 403


def test_mark_message_read_not_found(client):
    alice = _register(client, "alice@test.com", "Alice")
    res = client.patch("/messages/9999/read", headers=alice)
    assert res.status_code == 404


# ── Mark conversation read ──────────────────────────────────────────


def test_mark_conversation_read(client):
    alice = _register(client, "alice@test.com", "Alice")
    bob = _register(client, "bob@test.com", "Bob")
    bob_id = _get_user_id(client, bob)
    alice_id = _get_user_id(client, alice)
    _make_community_pair(client, alice, bob)

    client.post("/messages", headers=alice, json={"recipient_id": bob_id, "body": "Msg 1"})
    client.post("/messages", headers=alice, json={"recipient_id": bob_id, "body": "Msg 2"})

    # Bob marks all from Alice as read
    res = client.post(f"/messages/conversation/{alice_id}/read", headers=bob)
    assert res.status_code == 200

    # Unread count should be 0
    res = client.get("/messages/unread", headers=bob)
    assert res.json()["count"] == 0


def test_contacts_and_messages_do_not_expose_email(client):
    """Members see each other's names, never their email addresses."""
    alice = _register(client, "alice@test.com", "Alice")
    bob = _register(client, "bob@test.com", "Bob")
    bob_id = _get_user_id(client, bob)
    _make_community_pair(client, alice, bob)

    contacts = client.get("/messages/contacts", headers=alice).json()
    assert contacts and all("email" not in c for c in contacts)

    sent = client.post("/messages", json={"recipient_id": bob_id, "body": "Hi"}, headers=alice)
    assert sent.status_code == 201, sent.text
    assert "email" not in sent.json()["sender"] and "email" not in sent.json()["recipient"]

    conversations = client.get("/messages/conversations", headers=bob).json()
    assert conversations and "email" not in conversations[0]["partner"]
