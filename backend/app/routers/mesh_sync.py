"""Mesh sync endpoint — ingests messages received via BLE mesh when internet returns."""

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.community import Community, CommunityMember
from app.models.crisis import CrisisVote, EmergencyTicket, TicketComment
from app.models.message import Message
from app.models.mesh import MeshSyncedMessage
from app.models.mesh_checkin import MeshCheckin
from app.models.resource import Resource
from app.models.user import User
from app.schemas.mesh import MeshCheckinOut, MeshMessageIn, MeshMetricsIn, MeshSyncRequest, MeshSyncResponse
from app.services.activity import record_activity

router = APIRouter(prefix="/mesh", tags=["mesh"])


@router.post("/sync", response_model=MeshSyncResponse)
def sync_mesh_messages(
    body: MeshSyncRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Sync messages received via BLE mesh to the server.

    Each message is deduplicated by its unique mesh ID. Already-synced
    messages are skipped. Supported types: emergency_ticket, ticket_comment,
    crisis_vote, crisis_status, direct_message. Other types (heartbeat)
    are acknowledged but not persisted.
    """
    synced = 0
    duplicates = 0
    errors = 0

    for msg in body.messages:
        # Check for duplicate
        existing = (
            db.query(MeshSyncedMessage)
            .filter(MeshSyncedMessage.mesh_message_id == msg.id)
            .first()
        )
        if existing:
            duplicates += 1
            continue

        try:
            server_object_id = _process_mesh_message(db, msg, current_user)
            # Record as synced
            db.add(
                MeshSyncedMessage(
                    mesh_message_id=msg.id,
                    message_type=msg.type,
                    community_id=msg.community_id,
                    synced_by_id=current_user.id,
                    server_object_id=server_object_id,
                )
            )
            db.commit()
            synced += 1
        except HTTPException:
            db.rollback()
            errors += 1
        except Exception:
            db.rollback()
            errors += 1

    return MeshSyncResponse(synced=synced, duplicates=duplicates, errors=errors)


def _process_mesh_message(
    db: Session, msg: MeshMessageIn, current_user: User
) -> int | None:
    """Process a single mesh message based on its type. Returns server_object_id if applicable."""
    # Verify community exists
    community = db.query(Community).filter(Community.id == msg.community_id).first()
    if not community or not community.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Community not found"
        )

    # Verify user is a member of the community
    membership = (
        db.query(CommunityMember)
        .filter(
            CommunityMember.community_id == msg.community_id,
            CommunityMember.user_id == current_user.id,
        )
        .first()
    )
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not a member"
        )

    if msg.type == "emergency_ticket":
        return _sync_emergency_ticket(db, msg, current_user, community)
    elif msg.type == "ticket_comment":
        return _sync_ticket_comment(db, msg, current_user)
    elif msg.type == "crisis_vote":
        _sync_crisis_vote(db, msg, current_user)
        return None
    elif msg.type == "direct_message":
        return _sync_direct_message(db, msg, current_user)
    elif msg.type == "crisis_status":
        _sync_crisis_status(db, msg, current_user, community, membership)
        return None
    elif msg.type in ("resource_request", "resource_offer"):
        return _sync_resource(db, msg, current_user, community)
    elif msg.type == "location_checkin":
        return _sync_location_checkin(db, msg, current_user)
    # heartbeat: acknowledged but not persisted
    return None


def _sync_emergency_ticket(
    db: Session, msg: MeshMessageIn, user: User, community: Community
) -> int:
    """Create an emergency ticket from a mesh message. Returns the ticket ID."""
    data = msg.data
    ticket_type = data.get("ticket_type", "request")
    title = data.get("title", "")
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
    if ticket_type == "emergency_ping" and community.mode != "red":
        ticket_type = "request"  # downgrade silently for mesh sync

    ticket = EmergencyTicket(
        community_id=msg.community_id,
        author_id=user.id,
        ticket_type=ticket_type,
        title=str(title)[:300],
        description=str(description)[:5000],
        urgency=urgency,
    )
    db.add(ticket)
    db.flush()

    record_activity(
        db,
        event_type="ticket_created",
        summary=f'created {ticket_type} ticket "{title}" (via mesh sync)',
        actor_id=user.id,
        community_id=msg.community_id,
    )

    return ticket.id


def _sync_ticket_comment(
    db: Session, msg: MeshMessageIn, user: User
) -> int:
    """Create a ticket comment from a mesh message. Returns the comment ID."""
    data = msg.data
    body = data.get("body", "")
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

    # Look up the server-side ticket via the mesh message that created it
    synced_ticket = (
        db.query(MeshSyncedMessage)
        .filter(
            MeshSyncedMessage.mesh_message_id == ticket_mesh_id,
            MeshSyncedMessage.message_type == "emergency_ticket",
        )
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

    comment = TicketComment(
        ticket_id=ticket.id,
        author_id=user.id,
        body=str(body)[:5000],
    )
    db.add(comment)
    db.flush()

    record_activity(
        db,
        event_type="comment_created",
        summary=f"commented on ticket \"{ticket.title}\" (via mesh sync)",
        actor_id=user.id,
        community_id=msg.community_id,
    )

    return comment.id


def _sync_direct_message(
    db: Session, msg: MeshMessageIn, user: User
) -> int:
    """Create a direct message from a mesh message. Returns the message ID."""
    data = msg.data
    body = data.get("body", "")
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
        body=str(body)[:5000],
    )
    db.add(message)
    db.flush()

    return message.id


def _sync_crisis_status(
    db: Session, msg: MeshMessageIn, user: User, community: Community,
    membership: CommunityMember,
) -> None:
    """Update community crisis mode from a mesh message. Leader/admin only."""
    data = msg.data
    new_mode = data.get("new_mode", "")

    if new_mode not in ("blue", "red"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid mode, must be 'blue' or 'red'",
        )

    if membership.role not in ("leader", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only leaders and admins can change crisis mode",
        )

    if community.mode == new_mode:
        return  # Already in requested mode, no-op

    community.mode = new_mode
    db.flush()

    record_activity(
        db,
        event_type="crisis_mode_changed",
        summary=f"switched community to {new_mode} sky mode (via mesh sync)",
        actor_id=user.id,
        community_id=msg.community_id,
    )


def _sync_resource(
    db: Session, msg: MeshMessageIn, user: User, community: Community
) -> int:
    """Create a resource listing from a mesh message. Returns the resource ID."""
    data = msg.data
    title = data.get("title", "")
    description = data.get("description", "")
    category = data.get("category", "other")

    if not title:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Resource title required",
        )

    valid_categories = {
        "tools", "vehicle", "electronics", "furniture", "food",
        "clothing", "sports", "kitchen", "garden", "books",
        "toys", "other",
    }
    if category not in valid_categories:
        category = "other"

    resource = Resource(
        title=str(title)[:200],
        description=str(description)[:5000] if description else None,
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
        summary=f'{action} resource "{title}" (via mesh sync)',
        actor_id=user.id,
        community_id=msg.community_id,
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


@router.put("/keys/me", response_model=dict)
def set_my_mesh_key(
    public_key: str = Body(..., max_length=2000, embed=True),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Store the current user's mesh encryption public key."""
    current_user.mesh_public_key = public_key
    db.commit()
    return {"status": "ok"}


@router.get("/keys/{user_id}", response_model=dict)
def get_user_mesh_key(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a user's mesh encryption public key."""
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if not target.mesh_public_key:
        raise HTTPException(status_code=404, detail="User has no mesh key")
    return {"user_id": user_id, "public_key": target.mesh_public_key}


def _sync_crisis_vote(
    db: Session, msg: MeshMessageIn, user: User
) -> None:
    """Record a crisis vote from a mesh message."""
    data = msg.data
    vote_type = data.get("vote_type", "")

    if vote_type not in ("activate", "deactivate"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid vote type",
        )

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
