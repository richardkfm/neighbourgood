"""Mesh message signatures: canonical format, key registration, verified attribution."""

import base64
import hashlib
import json
import time
import uuid

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

from app.models.crisis import CrisisVote, EmergencyTicket
from app.models.mesh_checkin import MeshCheckin
from app.services.mesh_signing import (
    CanonicalizationError,
    canonical_json,
    key_id_for,
    load_spki,
    registration_input,
    signing_input,
    verify_p1363,
)

# ── Cross-language test vector ───────────────────────────────────
# Generated with the browser implementation (frontend/src/lib/bluetooth/signing.ts);
# the same vector is checked in frontend/tests/mesh-signing.test.mjs.

VECTOR_SPKI = (
    "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEUl9KvnTu5X-wkKzPd5AW6xPknX1iyUuE2pUzPF5NdTD_"
    "3gr9_nioxag13oYcS1eQnX2x2DKDbazA7cjJ6UyXtw"
)
VECTOR_KEY_ID = "3H_Ue8LOIqm7abYuhd694bThLhod9RHeqXtTZZgZn9U"
VECTOR_DATA_JSON = (
    '{"title":"Water needed \\"urgently\\"","description":"Line1\\nLine2\\t\\u0001 caf\\u00e9 '
    '\\ud83d\\ude00 \\\\ end","urgency":"high","ticket_type":"request","lat":52.52,"lng":-13.405,'
    '"tiny":0.000001,"tinier":1e-7,"count":5,"neg":-0,"big":9007199254740991,'
    '"float":0.30000000000000004,"flags":[true,false,null],"nested":{"z":1,"a":{"b":[]},'
    '"\\u00e9":"e-acute","Z":"upper","aa":2}}'
)
VECTOR_FIELDS = {
    "msg_type": "emergency_ticket",
    "community_id": 7,
    "ts": 1790000000123,
    "msg_id": "3f1c2d4e-5a6b-4c7d-8e9f-0a1b2c3d4e5f",
    "author_user_id": 42,
}
VECTOR_CANONICAL = (
    'NG-MESH-SIG-V1\n{"author_user_id":42,"community_id":7,"data":{"big":9007199254740991,'
    '"count":5,"description":"Line1\\nLine2\\t\\u0001 café 😀 \\\\ end","flags":[true,false,null],'
    '"float":0.30000000000000004,"lat":52.52,"lng":-13.405,"neg":0,"nested":{"Z":"upper",'
    '"a":{"b":[]},"aa":2,"z":1,"é":"e-acute"},"ticket_type":"request","tinier":1e-7,'
    '"tiny":0.000001,"title":"Water needed \\"urgently\\"","urgency":"high"},'
    '"id":"3f1c2d4e-5a6b-4c7d-8e9f-0a1b2c3d4e5f","ts":1790000000123,"type":"emergency_ticket"}'
)
VECTOR_SHA256 = "6a18f6ff3ac6771a9ebc955680f394476a0de9348405029b65a18e687278e8b8"
VECTOR_SIG = "HewX0900UtZ6ZxshaoSbja2SSDOjqn3NcKyVsFhNJBoLWmg4F4tE_9FvYqAOhBfmp29aV-Nye7h2rt73qWiZVg"
VECTOR_REG_PROOF_USER_42 = (
    "BGbXOGZ08qqQLksg-0ntsE1wZUyHeVWX0H9sC4obHeKDzf7J4uJhb82Bb-NCu1-bucHeu9K79T9IrQyr0lDR_w"
)


def _vector_input() -> bytes:
    return signing_input(data=json.loads(VECTOR_DATA_JSON), **VECTOR_FIELDS)


def test_vector_canonical_form():
    signed = _vector_input()
    assert signed.decode("utf-8") == VECTOR_CANONICAL
    assert hashlib.sha256(signed).hexdigest() == VECTOR_SHA256


def test_vector_key_id_and_signature_from_browser():
    spki = base64.urlsafe_b64decode(VECTOR_SPKI + "=" * (-len(VECTOR_SPKI) % 4))
    assert key_id_for(spki) == VECTOR_KEY_ID
    key = load_spki(VECTOR_SPKI)
    assert verify_p1363(key, VECTOR_SIG, _vector_input())
    assert verify_p1363(key, VECTOR_REG_PROOF_USER_42, registration_input(42, VECTOR_KEY_ID))
    # Any change to a signed field breaks the signature
    tampered = dict(VECTOR_FIELDS, author_user_id=43)
    assert not verify_p1363(key, VECTOR_SIG, signing_input(data=json.loads(VECTOR_DATA_JSON), **tampered))


@pytest.mark.parametrize(
    "value, expected",
    [
        (0.1, "0.1"), (1e-7, "1e-7"), (0.000001, "0.000001"), (1.5e-10, "1.5e-10"),
        (-0.0, "0"), (5.0, "5"), (123.456, "123.456"), (-13.405, "-13.405"),
        (2**53 - 1, "9007199254740991"), ("\x7f ", '"\x7f "'),
        ({"b": 1, "a": 2, "B": 3}, '{"B":3,"a":2,"b":1}'),
        ({"\U0001F600": 1, "￿": 2}, '{"￿":2,"\U0001F600":1}'),
    ],
)
def test_canonical_values(value, expected):
    assert canonical_json(value) == expected


@pytest.mark.parametrize("value", [float("nan"), float("inf"), 2**53, 1e21, "\ud800", {1: "x"}, object()])
def test_canonical_rejects(value):
    with pytest.raises(CanonicalizationError):
        canonical_json(value)


def test_canonical_rejects_deep_nesting():
    value: list = []
    for _ in range(40):
        value = [value]
    with pytest.raises(CanonicalizationError):
        canonical_json(value)


# ── Helpers ───────────────────────────────────────────────────────


class DeviceKey:
    def __init__(self, curve=None):
        self.private = ec.generate_private_key(curve or ec.SECP256R1())
        self.spki = self.private.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        self.key_id = key_id_for(self.spki)

    @property
    def spki_b64(self) -> str:
        return base64.b64encode(self.spki).decode()

    def jwk(self) -> dict:
        nums = self.private.public_key().public_numbers()

        def enc(n: int) -> str:
            return base64.urlsafe_b64encode(n.to_bytes(32, "big")).rstrip(b"=").decode()

        return {"kty": "EC", "crv": "P-256", "x": enc(nums.x), "y": enc(nums.y)}

    def sign(self, message: bytes) -> str:
        r, s = decode_dss_signature(self.private.sign(message, ec.ECDSA(hashes.SHA256())))
        raw = r.to_bytes(32, "big") + s.to_bytes(32, "big")
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    def proof(self, user_id: int) -> str:
        return self.sign(registration_input(user_id, self.key_id))


def _user_id(client, headers) -> int:
    return client.get("/users/me", headers=headers).json()["id"]


def _register(client, headers, key: DeviceKey, user_id: int | None = None, **extra):
    uid = user_id if user_id is not None else _user_id(client, headers)
    body = {"public_key": key.spki_b64, "proof": key.proof(uid), "device_name": "Phone"}
    body.update(extra)
    return client.post("/mesh/keys", json=body, headers=headers)


def _msg(msg_type, community_id, data, sender_name="Test User", **fields):
    msg = {
        "ng": 1,
        "type": msg_type,
        "community_id": community_id,
        "sender_name": sender_name,
        "ts": int(time.time() * 1000),
        "id": str(uuid.uuid4()),
        "data": data,
    }
    msg.update(fields)
    return msg


def _signed(key: DeviceKey, author_id: int, msg: dict) -> dict:
    signed = signing_input(
        msg_type=msg["type"],
        community_id=msg["community_id"],
        ts=msg["ts"],
        msg_id=msg["id"],
        data=msg["data"],
        author_user_id=author_id,
    )
    return dict(msg, author_user_id=author_id, key_id=key.key_id, sig=key.sign(signed))


def _sync(client, headers, *msgs):
    res = client.post("/mesh/sync", json={"messages": list(msgs)}, headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


@pytest.fixture()
def two_members(client, auth_headers, community_id, register_user):
    """Author (default test user) and a relayer, both members of the community."""
    relayer = register_user(2)
    client.post(f"/communities/{community_id}/join", headers=relayer)
    return {
        "author": auth_headers,
        "author_id": _user_id(client, auth_headers),
        "relayer": relayer,
        "relayer_id": _user_id(client, relayer),
    }


# ── Key registration ─────────────────────────────────────────────


def test_register_key_spki_and_idempotent(client, auth_headers):
    key = DeviceKey()
    res = _register(client, auth_headers, key)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["key_id"] == key.key_id
    assert body["device_name"] == "Phone"
    assert body["created_at"].endswith("Z")
    assert body["revoked_at"] is None

    again = _register(client, auth_headers, key)
    assert again.status_code == 200
    assert again.json()["key_id"] == key.key_id


def test_register_key_jwk_object_and_string(client, auth_headers):
    uid = _user_id(client, auth_headers)
    k1, k2 = DeviceKey(), DeviceKey()
    res = client.post(
        "/mesh/keys", json={"public_key": k1.jwk(), "proof": k1.proof(uid)}, headers=auth_headers
    )
    assert res.status_code == 201, res.text
    assert res.json()["key_id"] == k1.key_id  # key_id is over the SPKI, whatever the input format
    res = client.post(
        "/mesh/keys",
        json={"public_key": json.dumps(k2.jwk()), "proof": k2.proof(uid)},
        headers=auth_headers,
    )
    assert res.status_code == 201, res.text


def test_register_several_devices_and_list(client, auth_headers):
    keys = [DeviceKey(), DeviceKey()]
    for k in keys:
        assert _register(client, auth_headers, k).status_code == 201
    listed = client.get("/mesh/keys/me", headers=auth_headers).json()
    assert {k["key_id"] for k in listed} == {k.key_id for k in keys}


@pytest.mark.parametrize(
    "public_key",
    [
        "not a key",
        "eyJrdHkiOiJFQyIsImNydiI6IlAtMjU2IiwieCI6InRlc3QiLCJ5IjoidGVzdCJ9",  # the old "any string"
        {"kty": "EC", "crv": "P-256", "x": "dGVzdA", "y": "dGVzdA"},
        {"kty": "EC", "crv": "P-256", "x": "A" * 43, "y": "A" * 43},  # not on the curve
        {"kty": "RSA", "n": "AQAB", "e": "AQAB"},
        '{"kty": "EC"',
    ],
)
def test_register_key_rejects_invalid(client, auth_headers, public_key):
    res = client.post("/mesh/keys", json={"public_key": public_key, "proof": "AAAA"}, headers=auth_headers)
    assert res.status_code == 422


def test_register_key_rejects_other_curves_and_private_jwk(client, auth_headers):
    uid = _user_id(client, auth_headers)
    p384 = DeviceKey(ec.SECP384R1())
    res = client.post("/mesh/keys", json={"public_key": p384.spki_b64, "proof": "AAAA"}, headers=auth_headers)
    assert res.status_code == 422
    rsa_spki = rsa.generate_private_key(public_exponent=65537, key_size=2048).public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    res = client.post(
        "/mesh/keys", json={"public_key": base64.b64encode(rsa_spki).decode(), "proof": "AAAA"}, headers=auth_headers
    )
    assert res.status_code == 422
    key = DeviceKey()
    private_jwk = dict(key.jwk(), d="AAAA")
    res = client.post("/mesh/keys", json={"public_key": private_jwk, "proof": key.proof(uid)}, headers=auth_headers)
    assert res.status_code == 422


def test_register_key_requires_proof_for_this_account(client, auth_headers, register_user):
    """Registering someone else's public key (to hijack their signatures) fails."""
    key = DeviceKey()
    victim_headers = register_user(3)
    victim_id = _user_id(client, victim_headers)
    # Proof made for the victim's account cannot be reused by the attacker
    res = client.post(
        "/mesh/keys", json={"public_key": key.spki_b64, "proof": key.proof(victim_id)}, headers=auth_headers
    )
    assert res.status_code == 422
    assert _register(client, victim_headers, key).status_code == 201
    # And once registered, it is not available to anyone else
    uid = _user_id(client, auth_headers)
    res = client.post("/mesh/keys", json={"public_key": key.spki_b64, "proof": key.proof(uid)}, headers=auth_headers)
    assert res.status_code == 409


def test_revoke_key(client, auth_headers):
    key = DeviceKey()
    _register(client, auth_headers, key)
    assert client.delete(f"/mesh/keys/me/{key.key_id}", headers=auth_headers).status_code == 204
    listed = client.get("/mesh/keys/me", headers=auth_headers).json()
    assert listed[0]["revoked_at"] is not None
    # A revoked key cannot come back
    assert _register(client, auth_headers, key).status_code == 409
    assert client.delete("/mesh/keys/me/unknown", headers=auth_headers).status_code == 404


def test_public_keys_visible_to_community_members_only(client, two_members, register_user):
    key = DeviceKey()
    _register(client, two_members["author"], key)
    aid = two_members["author_id"]
    res = client.get(f"/mesh/keys/{aid}", headers=two_members["relayer"])
    assert res.status_code == 200
    assert [k["key_id"] for k in res.json()] == [key.key_id]
    outsider = register_user(9)
    assert client.get(f"/mesh/keys/{aid}", headers=outsider).status_code == 404


def test_keys_require_auth(client):
    assert client.get("/mesh/keys/me").status_code == 403
    assert client.post("/mesh/keys", json={"public_key": "x", "proof": "y"}).status_code == 403


# ── Verified sync ─────────────────────────────────────────────────


def _ticket(db, title):
    return db.query(EmergencyTicket).filter(EmergencyTicket.title == title).one()


def test_signed_own_message_is_verified(client, db, two_members, community_id):
    key = DeviceKey()
    _register(client, two_members["author"], key)
    msg = _signed(key, two_members["author_id"], _msg("emergency_ticket", community_id, {"title": "Own"}))
    result = _sync(client, two_members["author"], msg)
    assert result["synced"] == 1 and result["verified"] == 1
    ticket = _ticket(db, "Own")
    assert ticket.author_id == two_members["author_id"]
    assert "unverified" not in ticket.description


def test_relayed_and_signed_is_attributed_to_author(client, db, two_members, community_id):
    key = DeviceKey()
    _register(client, two_members["author"], key)
    msg = _signed(
        key, two_members["author_id"], _msg("emergency_ticket", community_id, {"title": "Relayed", "description": "d"})
    )
    result = _sync(client, two_members["relayer"], msg)
    assert result["verified"] == 1
    ticket = _ticket(db, "Relayed")
    assert ticket.author_id == two_members["author_id"]
    assert ticket.description == "d"  # no "unverified" relay label


def test_relayed_signed_vote_and_checkin_are_accepted(client, db, two_members, community_id):
    key = DeviceKey()
    _register(client, two_members["author"], key)
    aid = two_members["author_id"]
    vote = _signed(key, aid, _msg("crisis_vote", community_id, {"vote_type": "activate"}))
    checkin = _signed(key, aid, _msg("location_checkin", community_id, {"lat": 52.5, "lng": 13.4, "status": "safe"}))
    result = _sync(client, two_members["relayer"], vote, checkin)
    assert result["synced"] == 2 and result["verified"] == 2 and result["rejected"] == 0
    assert db.query(CrisisVote).filter(CrisisVote.user_id == aid).count() == 1
    assert db.query(MeshCheckin).filter(MeshCheckin.user_id == aid).count() == 1


def test_relayed_unsigned_vote_and_checkin_still_refused(client, db, two_members, community_id):
    vote = _msg("crisis_vote", community_id, {"vote_type": "activate"}, sender_name="Test User")
    checkin = _msg("location_checkin", community_id, {"lat": 1, "lng": 2}, sender_name="Test User")
    result = _sync(client, two_members["relayer"], vote, checkin)
    assert result["rejected"] == 2
    assert db.query(CrisisVote).count() == 0


def test_invalid_signature_falls_back_to_unverified(client, db, two_members, community_id):
    key = DeviceKey()
    _register(client, two_members["author"], key)
    aid = two_members["author_id"]
    msg = _signed(key, aid, _msg("emergency_ticket", community_id, {"title": "Tampered"}))
    msg["data"] = {"title": "Tampered", "description": "injected"}
    vote = _signed(key, aid, _msg("crisis_vote", community_id, {"vote_type": "activate"}))
    vote["data"] = {"vote_type": "activate", "x": 1}
    result = _sync(client, two_members["relayer"], msg, vote)
    assert result["verified"] == 0
    assert result["synced"] == 1 and result["rejected"] == 1  # the vote is author-only
    ticket = _ticket(db, "Tampered")
    assert ticket.author_id == two_members["relayer_id"]
    assert "unverified" in ticket.description


def test_signature_with_wrong_key_is_not_verified(client, db, two_members, community_id):
    registered, other = DeviceKey(), DeviceKey()
    _register(client, two_members["author"], registered)
    msg = _signed(other, two_members["author_id"], _msg("emergency_ticket", community_id, {"title": "Wrong"}))
    msg["key_id"] = registered.key_id  # claims the registered key, signed with another
    result = _sync(client, two_members["relayer"], msg)
    assert result["verified"] == 0
    assert _ticket(db, "Wrong").author_id == two_members["relayer_id"]


def test_key_of_another_user_does_not_verify(client, db, two_members, community_id):
    """author_user_id must match the key's owner."""
    key = DeviceKey()
    _register(client, two_members["relayer"], key)
    msg = _signed(key, two_members["author_id"], _msg("emergency_ticket", community_id, {"title": "Mismatch"}))
    result = _sync(client, two_members["relayer"], msg)
    assert result["verified"] == 0
    assert _ticket(db, "Mismatch").author_id == two_members["relayer_id"]


def test_revoked_key_is_not_verified(client, db, two_members, community_id):
    key = DeviceKey()
    _register(client, two_members["author"], key)
    client.delete(f"/mesh/keys/me/{key.key_id}", headers=two_members["author"])
    msg = _signed(key, two_members["author_id"], _msg("emergency_ticket", community_id, {"title": "Revoked"}))
    result = _sync(client, two_members["relayer"], msg)
    assert result["verified"] == 0
    ticket = _ticket(db, "Revoked")
    assert ticket.author_id == two_members["relayer_id"]
    assert "unverified" in ticket.description


def test_unsigned_relay_fallback(client, db, two_members, community_id):
    msg = _msg("emergency_ticket", community_id, {"title": "Unsigned"}, sender_name="Test User")
    result = _sync(client, two_members["relayer"], msg)
    assert result["synced"] == 1 and result["verified"] == 0
    ticket = _ticket(db, "Unsigned")
    assert ticket.author_id == two_members["relayer_id"]
    assert 'original sender "Test User" is unverified' in ticket.description


def test_message_id_squatting_does_not_block_signed_message(client, db, two_members, community_id):
    key = DeviceKey()
    _register(client, two_members["author"], key)
    genuine = _signed(key, two_members["author_id"], _msg("emergency_ticket", community_id, {"title": "Genuine"}))
    # The relayer syncs junk under the genuine message's ID first
    junk = _msg("emergency_ticket", community_id, {"title": "Junk"}, sender_name="User 2")
    junk["id"] = genuine["id"]
    assert _sync(client, two_members["relayer"], junk)["synced"] == 1

    result = _sync(client, two_members["relayer"], genuine)
    assert result["synced"] == 1 and result["verified"] == 1
    assert _ticket(db, "Genuine").author_id == two_members["author_id"]
    # Replaying the genuine message is a duplicate
    assert _sync(client, two_members["author"], genuine)["duplicates"] == 1


def test_signed_message_from_non_member_author_fails(client, register_user, auth_headers, community_id):
    outsider = register_user(4)
    key = DeviceKey()
    _register(client, outsider, key)
    msg = _signed(key, _user_id(client, outsider), _msg("emergency_ticket", community_id, {"title": "X"}))
    result = _sync(client, auth_headers, msg)
    assert result["errors"] == 1


# ── Ticket client_id idempotency ─────────────────────────────────


def _rest_ticket(client, headers, community_id, client_id, title="Rest"):
    return client.post(
        f"/communities/{community_id}/tickets",
        json={"ticket_type": "request", "title": title, "client_id": client_id},
        headers=headers,
    )


def test_rest_create_is_idempotent_per_client_id(client, auth_headers, community_id, register_user):
    cid = str(uuid.uuid4())
    first = _rest_ticket(client, auth_headers, community_id, cid)
    assert first.status_code == 201
    again = _rest_ticket(client, auth_headers, community_id, cid)
    assert again.status_code == 200
    assert again.json()["id"] == first.json()["id"]
    assert again.json()["client_id"] == cid
    # Another author may use the same client_id
    other = register_user(5)
    client.post(f"/communities/{community_id}/join", headers=other)
    assert _rest_ticket(client, other, community_id, cid).json()["id"] != first.json()["id"]


def test_rest_rejects_malformed_client_id(client, auth_headers, community_id):
    assert _rest_ticket(client, auth_headers, community_id, "bad id!").status_code == 422


def test_mesh_after_rest_returns_existing_ticket(client, db, two_members, community_id):
    key = DeviceKey()
    _register(client, two_members["author"], key)
    cid = str(uuid.uuid4())
    ticket_id = _rest_ticket(client, two_members["author"], community_id, cid, title="Both").json()["id"]
    msg = _signed(
        key, two_members["author_id"],
        _msg("emergency_ticket", community_id, {"title": "Both", "client_id": cid}),
    )
    result = _sync(client, two_members["relayer"], msg)
    assert result["duplicates"] == 1 and result["synced"] == 0
    assert db.query(EmergencyTicket).count() == 1
    # A comment on the mesh copy lands on the REST-created ticket
    comment = _msg("ticket_comment", community_id, {"ticket_mesh_id": msg["id"], "body": "on it"}, sender_name="User 2")
    assert _sync(client, two_members["relayer"], comment)["synced"] == 1
    comments = client.get(f"/communities/{community_id}/tickets/{ticket_id}/comments", headers=two_members["author"])
    assert len(comments.json()) == 1


def test_rest_after_mesh_returns_existing_ticket(client, db, two_members, community_id):
    key = DeviceKey()
    _register(client, two_members["author"], key)
    cid = str(uuid.uuid4())
    msg = _signed(
        key, two_members["author_id"],
        _msg("emergency_ticket", community_id, {"title": "MeshFirst", "client_id": cid}),
    )
    assert _sync(client, two_members["relayer"], msg)["synced"] == 1
    res = _rest_ticket(client, two_members["author"], community_id, cid, title="MeshFirst")
    assert res.status_code == 200
    assert db.query(EmergencyTicket).count() == 1


def test_unsigned_mesh_ticket_dedups_per_syncing_author(client, db, auth_headers, community_id):
    cid = str(uuid.uuid4())
    _rest_ticket(client, auth_headers, community_id, cid, title="Mine")
    msg = _msg("emergency_ticket", community_id, {"title": "Mine", "client_id": cid})
    assert _sync(client, auth_headers, msg)["duplicates"] == 1
    assert db.query(EmergencyTicket).count() == 1
