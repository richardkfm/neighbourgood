"""Tests for smart matching: skill matches, resource suggestions, unmet needs, AI enhancement."""

from unittest.mock import MagicMock, patch


# ── Helpers ──────────────────────────────────────────────────────────────────


def _create_community(client, auth_headers, name="Match Community"):
    res = client.post(
        "/communities",
        headers=auth_headers,
        json={"name": name, "postal_code": "10115", "city": "Berlin"},
    )
    assert res.status_code == 201, res.text
    return res.json()


def _create_skill(client, headers, community_id, title, category, skill_type):
    res = client.post(
        "/skills",
        headers=headers,
        json={
            "title": title,
            "category": category,
            "skill_type": skill_type,
            "community_id": community_id,
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def _create_resource(client, headers, title, category, community_id=None):
    payload = {"title": title, "category": category, "condition": "good"}
    if community_id:
        payload["community_id"] = community_id
    res = client.post("/resources", headers=headers, json=payload)
    assert res.status_code == 201, res.text
    return res.json()


def _register_user(client, n=2):
    res = client.post(
        "/auth/register",
        json={
            "email": f"match_user{n}@example.com",
            "password": "Testpass123",
            "display_name": f"Match User {n}",
        },
    )
    assert res.status_code == 201, res.text
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _join_community(client, headers, community_id):
    res = client.post(f"/communities/{community_id}/join", headers=headers)
    assert res.status_code in (200, 201), res.text


# ── /matching/status ─────────────────────────────────────────────────────────


def test_matching_status_no_ai(client, auth_headers):
    res = client.get("/matching/status", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["ai_available"] is False
    assert data["ai_provider"] is None
    assert data["ai_model"] is None


def test_matching_status_with_ai_configured(client, auth_headers):
    with patch("app.routers.matching.settings") as mock_settings, \
         patch("app.routers.matching.get_ai_client") as mock_get_ai:
        mock_settings.ai_provider = "ollama"
        mock_settings.ai_model = "llama3.2"
        mock_get_ai.return_value = MagicMock()
        res = client.get("/matching/status", headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert data["ai_available"] is True
        assert data["ai_provider"] == "ollama"
        assert data["ai_model"] == "llama3.2"


def test_matching_status_unauthenticated(client):
    res = client.get("/matching/status")
    assert res.status_code == 403


# ── /matching/suggestions — skill matching ───────────────────────────────────


def test_skill_matching_basic(client, auth_headers):
    """Skill offer in same community + category matches a skill request."""
    community = _create_community(client, auth_headers)
    cid = community["id"]

    # User 1 (test user) creates a skill request
    _create_skill(client, auth_headers, cid, "Need guitar lessons", "music", "request")

    # User 2 creates a matching skill offer
    user2_headers = _register_user(client, n=10)
    _join_community(client, user2_headers, cid)
    _create_skill(client, user2_headers, cid, "Guitar teacher available", "music", "offer")

    res = client.get(f"/matching/suggestions?community_id={cid}", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert len(data) >= 1
    skill_matches = [s for s in data if s["match_type"] == "skill_match"]
    assert len(skill_matches) >= 1
    assert skill_matches[0]["item_type"] == "skill"
    assert skill_matches[0]["category"] == "music"
    assert skill_matches[0]["score"] > 0
    assert skill_matches[0]["ai_enhanced"] is False


def test_skill_matching_different_community(client, auth_headers):
    """Skills in different communities should not match."""
    c1 = _create_community(client, auth_headers, "Community A")
    user2_headers = _register_user(client, n=11)
    c2 = _create_community(client, user2_headers, "Community B")

    _create_skill(client, auth_headers, c1["id"], "Need cooking help", "cooking", "request")

    _create_skill(client, user2_headers, c2["id"], "Chef available", "cooking", "offer")

    # Suggestions for community A should not include the offer from community B
    res = client.get(f"/matching/suggestions?community_id={c1['id']}", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    skill_matches = [s for s in data if s["match_type"] == "skill_match"]
    assert len(skill_matches) == 0


def test_skill_matching_different_category(client, auth_headers):
    """Skills in different categories should not match."""
    community = _create_community(client, auth_headers)
    cid = community["id"]

    _create_skill(client, auth_headers, cid, "Need cooking help", "cooking", "request")

    user2_headers = _register_user(client, n=12)
    _join_community(client, user2_headers, cid)
    _create_skill(client, user2_headers, cid, "Guitar lessons", "music", "offer")

    res = client.get(f"/matching/suggestions?community_id={cid}", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    skill_matches = [s for s in data if s["match_type"] == "skill_match"]
    assert len(skill_matches) == 0


def test_own_offers_excluded(client, auth_headers):
    """A user's own skill offers should not appear as suggestions."""
    community = _create_community(client, auth_headers)
    cid = community["id"]

    _create_skill(client, auth_headers, cid, "Need music help", "music", "request")
    _create_skill(client, auth_headers, cid, "I teach music", "music", "offer")

    res = client.get(f"/matching/suggestions?community_id={cid}", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    skill_matches = [s for s in data if s["match_type"] == "skill_match"]
    # Own offer should not match own request
    assert len(skill_matches) == 0


# ── /matching/suggestions — resource suggestions ─────────────────────────────


def test_resource_suggestions_from_history(client, auth_headers, db):
    """User with booking history gets suggestions in same categories."""
    community = _create_community(client, auth_headers)
    cid = community["id"]

    # User 2 creates a resource that user 1 books
    user2_headers = _register_user(client, n=20)
    _join_community(client, user2_headers, cid)
    r1 = _create_resource(client, user2_headers, "Power Drill", "tool", cid)

    # User 1 books the resource
    import datetime
    res = client.post(
        "/bookings",
        headers=auth_headers,
        json={
            "resource_id": r1["id"],
            "start_date": str(datetime.date.today()),
            "end_date": str(datetime.date.today() + datetime.timedelta(days=1)),
            "message": "Need it please",
        },
    )
    assert res.status_code == 201

    # User 2 adds another tool resource
    _create_resource(client, user2_headers, "Circular Saw", "tool", cid)

    # User 1 should get the circular saw as a suggestion
    res = client.get(f"/matching/suggestions?community_id={cid}", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    resource_suggestions = [s for s in data if s["match_type"] == "resource_suggestion"]
    assert len(resource_suggestions) >= 1
    titles = [s["item_title"] for s in resource_suggestions]
    assert "Circular Saw" in titles


def test_resource_suggestions_no_history(client, auth_headers):
    """User with no booking history gets no resource suggestions."""
    community = _create_community(client, auth_headers)
    cid = community["id"]

    user2_headers = _register_user(client, n=21)
    _join_community(client, user2_headers, cid)
    _create_resource(client, user2_headers, "Unused Item", "tool", cid)

    res = client.get(f"/matching/suggestions?community_id={cid}", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    resource_suggestions = [s for s in data if s["match_type"] == "resource_suggestion"]
    assert len(resource_suggestions) == 0


# ── /matching/suggestions — auth & validation ────────────────────────────────


def test_suggestions_unauthenticated(client):
    res = client.get("/matching/suggestions")
    assert res.status_code == 403


def test_suggestions_not_member(client, auth_headers):
    """Requesting suggestions for a community you don't belong to is forbidden."""
    # Create community as different user
    user2_headers = _register_user(client, n=30)
    c = _create_community(client, user2_headers, "Other Community")

    res = client.get(f"/matching/suggestions?community_id={c['id']}", headers=auth_headers)
    assert res.status_code == 403


# ── /matching/unmet-needs ────────────────────────────────────────────────────


def test_unmet_needs_red_sky(client, auth_headers):
    """Emergency requests without offers returned in crisis mode."""
    community = _create_community(client, auth_headers)
    cid = community["id"]

    # Toggle to Red Sky mode
    res = client.post(
        f"/communities/{cid}/crisis/toggle",
        headers=auth_headers,
        json={"mode": "red"},
    )
    assert res.status_code == 200

    # Create an emergency request ticket
    res = client.post(
        f"/communities/{cid}/tickets",
        headers=auth_headers,
        json={
            "title": "Need drinking water",
            "ticket_type": "request",
            "description": "Urgent water needed",
            "urgency": "critical",
        },
    )
    assert res.status_code == 201

    res = client.get(f"/matching/unmet-needs?community_id={cid}", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert len(data) >= 1
    assert data[0]["title"] == "Need drinking water"
    assert data[0]["urgency"] == "critical"
    assert data[0]["offer_count"] == 0


def test_unmet_needs_blue_sky_rejected(client, auth_headers):
    """Unmet needs endpoint requires Red Sky mode."""
    community = _create_community(client, auth_headers)
    cid = community["id"]

    res = client.get(f"/matching/unmet-needs?community_id={cid}", headers=auth_headers)
    assert res.status_code == 400
    assert "Red Sky" in res.json()["detail"]


def test_unmet_needs_requires_leader(client, auth_headers):
    """Only leaders/admins can view unmet needs."""
    community = _create_community(client, auth_headers)
    cid = community["id"]

    # Toggle to Red Sky
    client.post(
        f"/communities/{cid}/crisis/toggle",
        headers=auth_headers,
        json={"mode": "red"},
    )

    # Regular member tries to access
    user2_headers = _register_user(client, n=40)
    _join_community(client, user2_headers, cid)

    res = client.get(f"/matching/unmet-needs?community_id={cid}", headers=user2_headers)
    assert res.status_code == 403


def test_unmet_needs_unauthenticated(client):
    res = client.get("/matching/unmet-needs?community_id=1")
    assert res.status_code == 403


def test_unmet_needs_community_not_found(client, auth_headers):
    res = client.get("/matching/unmet-needs?community_id=99999", headers=auth_headers)
    assert res.status_code == 404


# ── AI enhancement (mocked) ─────────────────────────────────────────────────


def test_ai_enhancement_mocked(client, auth_headers):
    """When AI is configured, suggestions get enhanced reasons and ai_enhanced=true."""
    community = _create_community(client, auth_headers)
    cid = community["id"]

    _create_skill(client, auth_headers, cid, "Need help with Python", "tech", "request")

    user2_headers = _register_user(client, n=50)
    _join_community(client, user2_headers, cid)
    _create_skill(client, user2_headers, cid, "Python tutor", "tech", "offer")

    ai_response = '[{"item_title": "Python tutor", "score": 0.95, "reason": "Great match for Python learning"}]'

    mock_client = MagicMock()
    mock_client.chat.return_value = ai_response

    with patch("app.routers.matching.get_ai_client", return_value=mock_client):
        res = client.get(f"/matching/suggestions?community_id={cid}", headers=auth_headers)

    assert res.status_code == 200
    data = res.json()
    enhanced = [s for s in data if s["ai_enhanced"]]
    assert len(enhanced) >= 1
    assert enhanced[0]["reason"] == "Great match for Python learning"
    assert enhanced[0]["score"] == 0.95


def test_ai_failure_falls_back(client, auth_headers):
    """When AI call fails, rule-based results are returned unchanged."""
    community = _create_community(client, auth_headers)
    cid = community["id"]

    _create_skill(client, auth_headers, cid, "Need gardening help", "gardening", "request")

    user2_headers = _register_user(client, n=51)
    _join_community(client, user2_headers, cid)
    _create_skill(client, user2_headers, cid, "Garden expert", "gardening", "offer")

    mock_client = MagicMock()
    mock_client.chat.return_value = None  # AI failure

    with patch("app.routers.matching.get_ai_client", return_value=mock_client):
        res = client.get(f"/matching/suggestions?community_id={cid}", headers=auth_headers)

    assert res.status_code == 200
    data = res.json()
    # Results should still be returned (rule-based)
    assert len(data) >= 1
    # ai_enhanced should be False since AI failed
    assert all(s["ai_enhanced"] is False for s in data)


# ── Empty results ────────────────────────────────────────────────────────────


def test_suggestions_empty_no_communities(client, auth_headers):
    """User in no communities gets empty suggestions."""
    res = client.get("/matching/suggestions", headers=auth_headers)
    assert res.status_code == 200
    assert res.json() == []


def test_unmet_needs_with_matching_offers(client, auth_headers):
    """Emergency requests with matching offers show offer_count > 0."""
    community = _create_community(client, auth_headers)
    cid = community["id"]

    client.post(
        f"/communities/{cid}/crisis/toggle",
        headers=auth_headers,
        json={"mode": "red"},
    )

    # Create a request
    client.post(
        f"/communities/{cid}/tickets",
        headers=auth_headers,
        json={
            "title": "Need water filters",
            "ticket_type": "request",
            "description": "Water purification needed",
            "urgency": "high",
        },
    )

    # Create a matching offer
    client.post(
        f"/communities/{cid}/tickets",
        headers=auth_headers,
        json={
            "title": "Have water purification tablets",
            "ticket_type": "offer",
            "description": "Clean water supply available",
            "urgency": "medium",
        },
    )

    res = client.get(f"/matching/unmet-needs?community_id={cid}", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert len(data) >= 1
    # The word "water" overlaps between request and offer
    assert data[0]["offer_count"] >= 1
