"""Mesh sync endpoint — ingests messages received via BLE mesh when internet returns."""

import datetime
import math
import re
import time
from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.community import Community, CommunityMember
from app.models.crisis import CrisisVote, EmergencyTicket, TicketComment
from app.models.message import Message
from app.models.mesh import MeshDeviceKey, MeshSyncedMessage
from app.models.mesh_checkin import MeshCheckin
from app.models.resource import Resource
from app.models.user import User
from app.schemas.resource import VALID_CATEGORIES
from app.schemas.mesh import (
    MeshCheckinOut,
    MeshKeyOut,
    MeshKeyRegister,
    MeshMessageIn,
    MeshMetricsIn,
    MeshPublicKeyOut,
    MeshSyncRequest,
    MeshSyncResponse,
)
from app.services.activity import record_activity
from app.services.crisis_votes import apply_vote_threshold, is_noop_vote
from app.services.mesh_signing import (
    CanonicalizationError,
    InvalidPublicKey,
    b64url_encode,
    key_id_for,
    load_spki,
    parse_public_key,
    registration_input,
    signing_input,
    verify_p1363,
)
from app.services.mode import effective_mode

router = APIRouter(prefix="/mesh", tags=["mesh"])

_NON_PERSISTED_TYPES = frozenset({"heartbeat", "ack"})

# Actions that only make sense from their author: a relay must not cast its own
# vote or report its own location on behalf of whoever it heard them from.
_AUTHOR_ONLY_TYPES = frozenset({"crisis_vote", "location_checkin"})

# Phone clocks drift while offline, so tolerate some skew into the future
_MAX_FUTURE_SKEW_MS = 60 * 60 * 1000


def _text(value) -> str:
    """Return a stripped string, or "" for non-strings (mesh payloads are untrusted)."""
    return value.strip() if isinstance(value, str) else ""


class _Rejected(Exception):
    """A message refused by policy: counted in ``rejected``, never retried by clients."""


@dataclass
class _Attribution:
    """Who a mesh message's content is attributed to."""

    author: User
    # The author's signature was verified with their registered key
    verified: bool
    # Unverified relays: the sender the packet claims (shown as unverified)
    claimed_sender: str | None = None


def _attribute(db: Session, msg: MeshMessageIn, syncer: User) -> _Attribution:
    """Verify the message signature; fall back to the syncing user when it is missing or invalid."""
    if msg.sig and msg.key_id and msg.author_user_id:
        key = db.query(MeshDeviceKey).filter(MeshDeviceKey.key_id == msg.key_id).first()
        if key is not None and key.revoked_at is None and key.user_id == msg.author_user_id:
            try:
                signed = signing_input(
                    msg_type=msg.type,
                    community_id=msg.community_id,
                    ts=msg.ts,
                    msg_id=msg.id,
                    data=msg.data,
                    author_user_id=msg.author_user_id,
                )
            except CanonicalizationError:
                signed = None
            if signed is not None and verify_p1363(load_spki(key.public_key), msg.sig, signed):
                author = db.query(User).filter(User.id == key.user_id).first()
                if author is not None and author.is_active:
                    key.last_used_at = datetime.datetime.utcnow()
                    return _Attribution(author=author, verified=True)

    # Unsigned or invalid: the syncing user vouches for it, labelled as a relay
    # when the packet claims someone else wrote it
    claimed = msg.sender_name.strip()
    if msg.author_user_id and msg.author_user_id != syncer.id:
        claimed = claimed or f"user #{msg.author_user_id}"
    elif claimed.casefold() == (syncer.display_name or "").strip().casefold():
        claimed = ""
    return _Attribution(author=syncer, verified=False, claimed_sender=claimed[:100] or None)


def _relay_note(attr: _Attribution) -> str:
    """Prefix for stored text so readers can see relayed content is unverified."""
    if not attr.claimed_sender:
        return ""
    return (
        f"[Relayed via mesh by {attr.author.display_name}; "
        f'original sender "{attr.claimed_sender}" is unverified]\n'
    )


def _relay_suffix(attr: _Attribution) -> str:
    return f', relayed from "{attr.claimed_sender}" (unverified)' if attr.claimed_sender else ""


def _rejection_reason(msg: MeshMessageIn) -> str | None:
    """Why a mesh message is refused outright, or None if it may be processed.

    Refused messages are not retried by clients (they are not in failed_ids).
    """
    now_ms = int(time.time() * 1000)
    if msg.ts < now_ms - settings.mesh_max_message_age_hours * 3600 * 1000:
        return "too old"
    if msg.ts > now_ms + _MAX_FUTURE_SKEW_MS:
        return "timestamp in the future"
    if msg.type == "crisis_status":
        # Mode changes are admin-only through POST /crisis/toggle; a mesh packet
        # must not be able to flip a community.
        return "crisis mode can only be changed online"
    return None


def _is_duplicate(db: Session, msg: MeshMessageIn, attr: _Attribution) -> bool:
    query = db.query(MeshSyncedMessage.id).filter(MeshSyncedMessage.mesh_message_id == msg.id)
    if attr.verified:
        # Keyed by the real author: an earlier (junk) sync of the same ID by
        # someone else cannot shadow the genuine message
        query = query.filter(MeshSyncedMessage.author_id == attr.author.id)
    return query.first() is not None


@router.post("/sync", response_model=MeshSyncResponse)
def sync_mesh_messages(
    body: MeshSyncRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Sync messages received via BLE mesh to the server.

    Each message is deduplicated by its unique mesh ID. Already-synced
    messages are skipped. Supported types: emergency_ticket, ticket_comment,
    crisis_vote, direct_message, resource_request/offer, location_checkin.
    Heartbeats/acks are acknowledged but not persisted. Messages refused by
    policy (see _rejection_reason) are counted in ``rejected``.
    """
    synced = 0
    verified = 0
    duplicates = 0
    errors = 0
    rejected = 0
    failed_ids: list[str] = []

    # Comments reference tickets synced from the same batch, so process them last
    # (stable sort keeps arrival order otherwise).
    for msg in sorted(body.messages, key=lambda m: m.type == "ticket_comment"):
        if _rejection_reason(msg):
            rejected += 1
            continue

        attr = _attribute(db, msg, current_user)
        # Votes and check-ins only count from their author: unsigned ones are
        # accepted only when the syncing user is the author
        if msg.type in _AUTHOR_ONLY_TYPES and not attr.verified and attr.claimed_sender:
            db.rollback()
            rejected += 1
            continue

        if _is_duplicate(db, msg, attr):
            db.rollback()
            duplicates += 1
            continue

        try:
            server_object_id, existing = _process_mesh_message(db, msg, attr)
            # Record as synced. Heartbeats/acks persist nothing, so they are not
            # recorded: otherwise any member could "squat" a real message's ID
            # with a junk heartbeat and make the genuine message a duplicate.
            if msg.type not in _NON_PERSISTED_TYPES:
                db.add(
                    MeshSyncedMessage(
                        mesh_message_id=msg.id,
                        message_type=msg.type,
                        community_id=msg.community_id,
                        synced_by_id=current_user.id,
                        author_id=attr.author.id,
                        verified=attr.verified,
                        server_object_id=server_object_id,
                    )
                )
            db.commit()
            if existing:
                # The same ticket already exists (REST replay or another relay)
                duplicates += 1
            else:
                synced += 1
                verified += int(attr.verified)
        except IntegrityError:
            # A concurrent sync of the same mesh ID won the race; the handler's
            # writes are rolled back together with the dedup record.
            db.rollback()
            duplicates += 1
        except _Rejected:
            db.rollback()
            rejected += 1
        except HTTPException:
            db.rollback()
            errors += 1
            failed_ids.append(msg.id)
        except Exception:
            db.rollback()
            errors += 1
            failed_ids.append(msg.id)

    return MeshSyncResponse(
        synced=synced,
        verified=verified,
        duplicates=duplicates,
        errors=errors,
        rejected=rejected,
        failed_ids=failed_ids,
    )


def _process_mesh_message(
    db: Session, msg: MeshMessageIn, attr: _Attribution
) -> tuple[int | None, bool]:
    """Process a single mesh message based on its type.

    Returns (server_object_id, existing): ``existing`` is True when the message
    resolved to an object that already existed (idempotent ticket create).
    """
    community = db.query(Community).filter(Community.id == msg.community_id).first()
    if not community or not community.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Community not found"
        )

    # The author must belong to the community: for a verified message the
    # signer (whoever carried it online), otherwise the syncing user
    membership = (
        db.query(CommunityMember)
        .filter(
            CommunityMember.community_id == msg.community_id,
            CommunityMember.user_id == attr.author.id,
        )
        .first()
    )
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not a member"
        )

    if msg.type == "emergency_ticket":
        return _sync_emergency_ticket(db, msg, attr, community)
    elif msg.type == "ticket_comment":
        return _sync_ticket_comment(db, msg, attr), False
    elif msg.type == "crisis_vote":
        _sync_crisis_vote(db, msg, attr.author, community)
        return None, False
    elif msg.type == "direct_message":
        return _sync_direct_message(db, msg, attr), False
    elif msg.type in ("resource_request", "resource_offer"):
        return _sync_resource(db, msg, attr), False
    elif msg.type == "location_checkin":
        return _sync_location_checkin(db, msg, attr.author), False
    # heartbeat: acknowledged but not persisted
    return None, False


_CLIENT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


def _sync_emergency_ticket(
    db: Session, msg: MeshMessageIn, attr: _Attribution, community: Community
) -> tuple[int, bool]:
    """Create an emergency ticket from a mesh message. Returns (ticket ID, already existed)."""
    user = attr.author
    data = msg.data
    ticket_type = data.get("ticket_type", "request")
    title = _text(data.get("title"))
    description = data.get("description", "")
    urgency = data.get("urgency", "medium")

    if not title:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Ticket title required",
        )

    # Validate ticket_type
    if ticket_type not in ("request", "offer", "emergency_ping"):
        ticket_type = "request"
    if urgency not in ("low", "medium", "high", "critical"):
        urgency = "medium"

    # Emergency pings require crisis mode
    if ticket_type == "emergency_ping" and effective_mode(community) != "red":
        ticket_type = "request"  # downgrade silently for mesh sync

    # The same client_id is sent with the REST create of this ticket: whichever
    # arrives second resolves to the ticket the first one created
    client_id = data.get("client_id")
    if not (isinstance(client_id, str) and _CLIENT_ID_RE.match(client_id)):
        client_id = None
    if client_id:
        existing = (
            db.query(EmergencyTicket)
            .filter(EmergencyTicket.author_id == user.id, EmergencyTicket.client_id == client_id)
            .first()
        )
        if existing is not None:
            return existing.id, True

    ticket = EmergencyTicket(
        community_id=msg.community_id,
        author_id=user.id,
        ticket_type=ticket_type,
        title=str(title)[:300],
        description=(_relay_note(attr) + str(description))[:5000],
        urgency=urgency,
        client_id=client_id,
    )
    db.add(ticket)
    db.flush()

    record_activity(
        db,
        event_type="ticket_created",
        summary=f'created {ticket_type} ticket "{title}" (via mesh sync{_relay_suffix(attr)})',
        actor_id=user.id,
        community_id=msg.community_id,
        commit=False,
    )

    return ticket.id, False


def _sync_ticket_comment(
    db: Session, msg: MeshMessageIn, attr: _Attribution
) -> int:
    """Create a ticket comment from a mesh message. Returns the comment ID."""
    user = attr.author
    data = msg.data
    body = _text(data.get("body"))
    ticket_mesh_id = data.get("ticket_mesh_id", "")

    if not body:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Comment body required",
        )

    if not ticket_mesh_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="ticket_mesh_id required",
        )

    # Look up the server-side ticket via the mesh message that created it,
    # preferring the copy synced with a verified signature
    synced_ticket = (
        db.query(MeshSyncedMessage)
        .filter(
            MeshSyncedMessage.mesh_message_id == str(ticket_mesh_id)[:100],
            MeshSyncedMessage.message_type == "emergency_ticket",
        )
        .order_by(MeshSyncedMessage.verified.desc(), MeshSyncedMessage.id)
        .first()
    )
    if not synced_ticket or not synced_ticket.server_object_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Referenced ticket not yet synced",
        )

    # Verify the ticket still exists
    ticket = (
        db.query(EmergencyTicket)
        .filter(EmergencyTicket.id == synced_ticket.server_object_id)
        .first()
    )
    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Referenced ticket no longer exists",
        )
    if ticket.community_id != msg.community_id:
        # The sender was only membership-checked against msg.community_id, so
        # never let a comment land on a ticket of a different community.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Ticket belongs to a different community",
        )

    comment = TicketComment(
        ticket_id=ticket.id,
        author_id=user.id,
        body=(_relay_note(attr) + str(body))[:5000],
    )
    db.add(comment)
    db.flush()

    record_activity(
        db,
        event_type="comment_created",
        summary=f"commented on ticket \"{ticket.title}\" (via mesh sync{_relay_suffix(attr)})",
        actor_id=user.id,
        community_id=msg.community_id,
        commit=False,
    )

    return comment.id


def _sync_direct_message(
    db: Session, msg: MeshMessageIn, attr: _Attribution
) -> int:
    """Create a direct message from a mesh message. Returns the message ID."""
    user = attr.author
    data = msg.data
    body = _text(data.get("body"))
    recipient_id = data.get("recipient_id")

    if not body:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Message body required",
        )

    if not recipient_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="recipient_id required",
        )

    # Verify recipient exists
    recipient = db.query(User).filter(User.id == recipient_id).first()
    if not recipient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recipient not found",
        )

    # Verify sender and recipient share at least one community
    sender_communities = {
        m.community_id
        for m in db.query(CommunityMember).filter(
            CommunityMember.user_id == user.id
        ).all()
    }
    recipient_communities = {
        m.community_id
        for m in db.query(CommunityMember).filter(
            CommunityMember.user_id == recipient_id
        ).all()
    }
    if not sender_communities & recipient_communities:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Recipient not in a shared community",
        )

    message = Message(
        sender_id=user.id,
        recipient_id=recipient_id,
        body=(_relay_note(attr) + str(body))[:5000],
    )
    db.add(message)
    db.flush()

    return message.id


def _sync_resource(
    db: Session, msg: MeshMessageIn, attr: _Attribution
) -> int:
    """Create a resource listing from a mesh message. Returns the resource ID."""
    user = attr.author
    data = msg.data
    title = _text(data.get("title"))
    description = data.get("description", "")
    category = data.get("category", "other")

    if not title:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Resource title required",
        )

    # Same categories as REST-created resources; older clients sent "tools"
    if category == "tools":
        category = "tool"
    if category not in VALID_CATEGORIES:
        category = "other"

    resource = Resource(
        title=str(title)[:200],
        description=(_relay_note(attr) + str(description or ""))[:5000] or None,
        category=category,
        condition="good",
        is_available=True,
        owner_id=user.id,
        community_id=msg.community_id,
    )
    db.add(resource)
    db.flush()

    action = "shared" if msg.type == "resource_offer" else "requested"
    record_activity(
        db,
        event_type="resource_created",
        summary=f'{action} resource "{title}" (via mesh sync{_relay_suffix(attr)})',
        actor_id=user.id,
        community_id=msg.community_id,
        commit=False,
    )

    return resource.id


def _sync_location_checkin(
    db: Session, msg: MeshMessageIn, user: User
) -> int:
    """Persist a location check-in from a mesh message. Returns the checkin ID."""
    data = msg.data
    lat = data.get("lat")
    lng = data.get("lng")
    checkin_status = data.get("status", "")

    if lat is None or lng is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="lat and lng required",
        )

    try:
        lat = float(lat)
        lng = float(lng)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="lat and lng must be numbers",
        )

    if not (math.isfinite(lat) and math.isfinite(lng)) or not (
        -90 <= lat <= 90 and -180 <= lng <= 180
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="lat/lng out of range",
        )

    if checkin_status not in ("safe", "need_help", "evacuating"):
        checkin_status = "safe"

    note = data.get("note")

    checkin = MeshCheckin(
        community_id=msg.community_id,
        user_id=user.id,
        lat=lat,
        lng=lng,
        status=checkin_status,
        note=str(note)[:5000] if note else None,
    )
    db.add(checkin)
    db.flush()

    record_activity(
        db,
        event_type="checkin_created",
        summary=f'checked in as "{checkin_status}" (via mesh sync)',
        actor_id=user.id,
        community_id=msg.community_id,
        commit=False,
    )

    return checkin.id


@router.get("/checkins/{community_id}", response_model=list[MeshCheckinOut])
def get_community_checkins(
    community_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get recent location check-ins for a community (last 2 hours)."""
    import datetime as dt

    # Verify membership
    membership = (
        db.query(CommunityMember)
        .filter(
            CommunityMember.community_id == community_id,
            CommunityMember.user_id == current_user.id,
        )
        .first()
    )
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not a member"
        )

    cutoff = dt.datetime.utcnow() - dt.timedelta(hours=2)
    checkins = (
        db.query(MeshCheckin)
        .filter(
            MeshCheckin.community_id == community_id,
            MeshCheckin.checked_in_at >= cutoff,
        )
        .order_by(MeshCheckin.checked_in_at.desc())
        .all()
    )

    # Build response with display names
    user_ids = {c.user_id for c in checkins}
    users = {u.id: u for u in db.query(User).filter(User.id.in_(user_ids)).all()} if user_ids else {}

    return [
        MeshCheckinOut(
            id=c.id,
            community_id=c.community_id,
            user_id=c.user_id,
            display_name=users.get(c.user_id, User()).display_name or "Unknown",
            lat=c.lat,
            lng=c.lng,
            status=c.status,
            note=c.note,
            checked_in_at=c.checked_in_at.isoformat() if c.checked_in_at else "",
        )
        for c in checkins
    ]


@router.post("/metrics", response_model=dict)
def submit_mesh_metrics(
    body: MeshMetricsIn,
    current_user: User = Depends(get_current_user),
):
    """Accept client-side mesh session metrics for aggregate reporting.

    Currently logs metrics server-side. Future: persist to analytics DB.
    """
    import logging

    logger = logging.getLogger("mesh.metrics")
    logger.info(
        "Mesh metrics from user=%d: sent=%d recv=%d relayed=%d peers=%d acks=%d/%d errors=%d duration=%dms",
        current_user.id,
        body.messages_sent,
        body.messages_received,
        body.messages_relayed,
        body.peak_peer_count,
        body.acks_sent,
        body.acks_received,
        body.errors,
        body.session_duration_ms,
    )
    return {"status": "ok"}


_MAX_ACTIVE_KEYS_PER_USER = 20


@router.post("/keys", response_model=MeshKeyOut, status_code=status.HTTP_201_CREATED)
def register_mesh_key(
    body: MeshKeyRegister,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Register this device's ECDSA P-256 public key for signing mesh messages.

    Accepts SPKI DER (base64/base64url) or a public JWK. ``proof`` must be the
    key's signature over ``NG-MESH-KEY-V1\n{user_id}\n{key_id}``. Re-registering
    an active key of your own is idempotent (200).
    """
    try:
        public_key, spki = parse_public_key(body.public_key)
    except InvalidPublicKey as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Invalid public key: {exc}")
    key_id = key_id_for(spki)
    if not verify_p1363(public_key, body.proof, registration_input(current_user.id, key_id)):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid proof of possession for this key",
        )

    existing = db.query(MeshDeviceKey).filter(MeshDeviceKey.key_id == key_id).first()
    if existing is not None:
        if existing.user_id != current_user.id or existing.revoked_at is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This key cannot be registered")
        if body.device_name and body.device_name != existing.device_name:
            existing.device_name = body.device_name
            db.commit()
            db.refresh(existing)
        response.status_code = status.HTTP_200_OK
        return existing

    active = (
        db.query(MeshDeviceKey)
        .filter(MeshDeviceKey.user_id == current_user.id, MeshDeviceKey.revoked_at.is_(None))
        .count()
    )
    if active >= _MAX_ACTIVE_KEYS_PER_USER:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Too many active mesh keys; revoke an unused device first",
        )

    key = MeshDeviceKey(
        user_id=current_user.id,
        key_id=key_id,
        public_key=b64url_encode(spki),
        device_name=body.device_name.strip(),
    )
    db.add(key)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This key cannot be registered")
    db.refresh(key)
    return key


@router.get("/keys/me", response_model=list[MeshKeyOut])
def list_my_mesh_keys(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """All mesh signing keys registered for your account, including revoked ones."""
    return (
        db.query(MeshDeviceKey)
        .filter(MeshDeviceKey.user_id == current_user.id)
        .order_by(MeshDeviceKey.created_at.desc(), MeshDeviceKey.id.desc())
        .all()
    )


@router.delete("/keys/me/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_my_mesh_key(
    key_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Revoke one of your device keys. Messages signed with it no longer verify."""
    key = (
        db.query(MeshDeviceKey)
        .filter(MeshDeviceKey.key_id == key_id, MeshDeviceKey.user_id == current_user.id)
        .first()
    )
    if key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Key not found")
    if key.revoked_at is None:
        key.revoked_at = datetime.datetime.utcnow()
        db.commit()


@router.get("/keys/{user_id}", response_model=list[MeshPublicKeyOut])
def get_user_mesh_keys(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Active mesh signing keys of a user you share a community with (or yourself)."""
    if user_id != current_user.id:
        mine = db.query(CommunityMember.community_id).filter(CommunityMember.user_id == current_user.id)
        shared = (
            db.query(CommunityMember.id)
            .filter(CommunityMember.user_id == user_id, CommunityMember.community_id.in_(mine))
            .first()
        )
        if shared is None:
            raise HTTPException(status_code=404, detail="User not found")
    return (
        db.query(MeshDeviceKey)
        .filter(MeshDeviceKey.user_id == user_id, MeshDeviceKey.revoked_at.is_(None))
        .order_by(MeshDeviceKey.id)
        .all()
    )


def _sync_crisis_vote(
    db: Session, msg: MeshMessageIn, user: User, community: Community
) -> None:
    """Record a crisis vote from a mesh message (by its verified or syncing author)."""
    data = msg.data
    vote_type = data.get("vote_type", "")

    if vote_type not in ("activate", "deactivate"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid vote type",
        )
    if is_noop_vote(community.mode, vote_type):
        # Same rule as POST /crisis/vote (409 there); never retried
        raise _Rejected("vote would not change the mode")

    # Check for existing vote
    existing = (
        db.query(CrisisVote)
        .filter(
            CrisisVote.community_id == msg.community_id,
            CrisisVote.user_id == user.id,
        )
        .first()
    )
    if existing:
        if existing.vote_type == vote_type:
            return  # Same vote already exists, no-op
        existing.vote_type = vote_type
    else:
        vote = CrisisVote(
            community_id=msg.community_id,
            user_id=user.id,
            vote_type=vote_type,
        )
        db.add(vote)
    db.flush()
    # Honour the same 60% threshold as POST /crisis/vote
    apply_vote_threshold(db, msg.community_id, vote_type, user.id, commit=False)
