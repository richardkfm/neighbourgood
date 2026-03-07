"""Red Sky (crisis) mode endpoints – toggle, voting, emergency tickets, leaders."""

import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.dependencies import get_current_user
from app.models.community import Community, CommunityMember
from app.models.crisis import CrisisVote, EmergencyTicket, TicketComment
from app.models.user import User
from app.services.activity import record_activity
from app.services.webhooks import dispatch_event
from app.utils.authorization import (
    require_admin,
    require_admin_or_leader,
    require_community,
    require_membership,
)
from app.schemas.crisis import (
    CrisisModeStatus,
    CrisisModeToggle,
    CrisisVoteCreate,
    CrisisVoteOut,
    EmergencyTicketCreate,
    EmergencyTicketList,
    EmergencyTicketOut,
    EmergencyTicketUpdate,
    LeaderOut,
    TicketCommentCreate,
    TicketCommentOut,
)
from app.schemas.community import CommunityMemberOut

router = APIRouter(prefix="/communities/{community_id}", tags=["crisis"])

VOTE_THRESHOLD_PCT = 60  # percentage of members needed to trigger mode change

# Urgency levels mapped to integer weights for triage scoring
_URGENCY_RANK: dict[str, int] = {"low": 1, "medium": 2, "high": 3, "critical": 4}


def _triage_score(ticket: EmergencyTicket) -> int:
    """Compute a triage priority score for a ticket.

    Score = urgency_weight * 100 + age_hours (capped at 99).
    Higher score → show first in the triage view.
    When a due_at is set and overdue, add 200 to escalate above non-overdue tickets.
    """
    urgency_weight = _URGENCY_RANK.get(ticket.urgency, 1)
    now = datetime.datetime.utcnow()
    age_hours = min(int((now - ticket.created_at).total_seconds() / 3600), 99)
    score = urgency_weight * 100 + age_hours
    if ticket.due_at and ticket.due_at < now:
        score += 200  # escalate overdue tickets above everything else
    return score


def _ticket_to_out(ticket: EmergencyTicket) -> EmergencyTicketOut:
    """Build EmergencyTicketOut with the computed triage_score."""
    return EmergencyTicketOut(
        id=ticket.id,
        community_id=ticket.community_id,
        author=ticket.author,
        ticket_type=ticket.ticket_type,
        title=ticket.title,
        description=ticket.description,
        status=ticket.status,
        urgency=ticket.urgency,
        due_at=ticket.due_at,
        triage_score=_triage_score(ticket),
        assigned_to=ticket.assigned_to,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
    )


# ── Local helpers ─────────────────────────────────────────────────


def _get_community(db: Session, community_id: int) -> Community:
    community = db.query(Community).filter(Community.id == community_id).first()
    if not community or not community.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Community not found"
        )
    return community


# ── Crisis mode toggle (admin only) ──────────────────────────────


@router.post("/crisis/toggle", response_model=CrisisModeStatus)
def toggle_crisis_mode(
    community_id: int,
    body: CrisisModeToggle,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Admin-only: force-toggle the community between blue (normal) and red (crisis) mode."""
    community = _get_community(db, community_id)
    require_admin(db, community_id, current_user.id)

    community.mode = body.mode
    # Clear existing votes when admin overrides
    db.query(CrisisVote).filter(CrisisVote.community_id == community_id).delete()
    db.commit()
    db.refresh(community)

    label = "Red Sky (crisis)" if body.mode == "red" else "Blue Sky (normal)"
    record_activity(
        db,
        event_type="crisis_mode_changed",
        summary=f'switched "{community.name}" to {label}',
        actor_id=current_user.id,
        community_id=community_id,
    )

    if body.mode == "red":
        member_ids = [
            row[0]
            for row in db.query(CommunityMember.user_id)
            .filter(CommunityMember.community_id == community_id)
            .all()
        ]
        background_tasks.add_task(
            dispatch_event,
            db,
            "crisis.mode_changed",
            {"community_name": community.name, "new_mode": body.mode},
            member_ids,
            community_id,
        )

    total = (
        db.query(CommunityMember)
        .filter(CommunityMember.community_id == community_id)
        .count()
    )
    return CrisisModeStatus(
        community_id=community_id,
        mode=community.mode,
        total_members=total,
        threshold_pct=VOTE_THRESHOLD_PCT,
    )


@router.get("/crisis/status", response_model=CrisisModeStatus)
def get_crisis_status(
    community_id: int,
    db: Session = Depends(get_db),
):
    """Get crisis mode status including vote counts."""
    community = _get_community(db, community_id)

    total = (
        db.query(CommunityMember)
        .filter(CommunityMember.community_id == community_id)
        .count()
    )
    activate_votes = (
        db.query(CrisisVote)
        .filter(
            CrisisVote.community_id == community_id,
            CrisisVote.vote_type == "activate",
        )
        .count()
    )
    deactivate_votes = (
        db.query(CrisisVote)
        .filter(
            CrisisVote.community_id == community_id,
            CrisisVote.vote_type == "deactivate",
        )
        .count()
    )

    return CrisisModeStatus(
        community_id=community_id,
        mode=community.mode,
        votes_to_activate=activate_votes,
        votes_to_deactivate=deactivate_votes,
        total_members=total,
        threshold_pct=VOTE_THRESHOLD_PCT,
    )


# ── Community vote ────────────────────────────────────────────────


@router.post("/crisis/vote", response_model=CrisisVoteOut)
def cast_crisis_vote(
    community_id: int,
    body: CrisisVoteCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Cast a vote to activate or deactivate crisis mode. One vote per member."""
    community = _get_community(db, community_id)
    require_membership(db, community_id, current_user.id)

    # Check for existing vote (replace if different)
    existing = (
        db.query(CrisisVote)
        .filter(
            CrisisVote.community_id == community_id,
            CrisisVote.user_id == current_user.id,
        )
        .first()
    )
    if existing:
        if existing.vote_type == body.vote_type:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="You have already voted this way",
            )
        existing.vote_type = body.vote_type
        db.commit()
        db.refresh(existing)
        vote = existing
    else:
        vote = CrisisVote(
            community_id=community_id,
            user_id=current_user.id,
            vote_type=body.vote_type,
        )
        db.add(vote)
        db.commit()
        db.refresh(vote)

    # Eagerly load user before threshold check (which may delete the vote)
    _ = vote.user

    # Build response before potential deletion
    vote_response = CrisisVoteOut.model_validate(vote)

    # Check if threshold is met to auto-switch mode
    total_members = (
        db.query(CommunityMember)
        .filter(CommunityMember.community_id == community_id)
        .count()
    )
    target_type = body.vote_type  # activate or deactivate
    vote_count = (
        db.query(CrisisVote)
        .filter(
            CrisisVote.community_id == community_id,
            CrisisVote.vote_type == target_type,
        )
        .count()
    )

    threshold_needed = max(1, (total_members * VOTE_THRESHOLD_PCT + 99) // 100)
    if vote_count >= threshold_needed:
        new_mode = "red" if target_type == "activate" else "blue"
        if community.mode != new_mode:
            community.mode = new_mode
            # Clear all votes after mode switch
            db.query(CrisisVote).filter(
                CrisisVote.community_id == community_id
            ).delete()
            db.commit()

            label = "Red Sky (crisis)" if new_mode == "red" else "Blue Sky (normal)"
            record_activity(
                db,
                event_type="crisis_mode_changed",
                summary=f'community vote switched "{community.name}" to {label}',
                actor_id=current_user.id,
                community_id=community_id,
            )

    return vote_response


@router.delete("/crisis/vote", status_code=status.HTTP_204_NO_CONTENT)
def retract_crisis_vote(
    community_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retract your crisis mode vote."""
    _get_community(db, community_id)
    vote = (
        db.query(CrisisVote)
        .filter(
            CrisisVote.community_id == community_id,
            CrisisVote.user_id == current_user.id,
        )
        .first()
    )
    if not vote:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No vote to retract"
        )
    db.delete(vote)
    db.commit()


# ── Emergency tickets ─────────────────────────────────────────────


@router.post(
    "/tickets", response_model=EmergencyTicketOut, status_code=status.HTTP_201_CREATED
)
def create_ticket(
    community_id: int,
    body: EmergencyTicketCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create an emergency ticket (request, offer, or emergency ping)."""
    community = _get_community(db, community_id)
    require_membership(db, community_id, current_user.id)

    # Emergency pings require crisis mode to be active
    if body.ticket_type == "emergency_ping" and community.mode != "red":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Emergency pings are only available in Red Sky (crisis) mode",
        )

    ticket = EmergencyTicket(
        community_id=community_id,
        author_id=current_user.id,
        ticket_type=body.ticket_type,
        title=body.title,
        description=body.description,
        urgency=body.urgency,
        due_at=body.due_at,
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    _ = ticket.author
    _ = ticket.assigned_to

    record_activity(
        db,
        event_type="ticket_created",
        summary=f'created {body.ticket_type} ticket "{body.title}"',
        actor_id=current_user.id,
        community_id=community_id,
    )

    background_tasks.add_task(
        dispatch_event,
        db,
        "ticket.created",
        {
            "title": body.title,
            "ticket_type": body.ticket_type,
            "urgency": body.urgency,
            "community_name": community.name,
        },
        [],
        community_id,
    )

    return _ticket_to_out(ticket)


@router.get("/tickets", response_model=EmergencyTicketList)
def list_tickets(
    community_id: int,
    ticket_type: str | None = Query(None, description="Filter by type"),
    ticket_status: str | None = Query(None, alias="status", description="Filter by status"),
    urgency: str | None = Query(None, description="Filter by urgency level"),
    sort: str = Query("created_desc", description="Sort order: created_desc | priority_desc"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List emergency tickets for a community."""
    _get_community(db, community_id)
    require_membership(db, community_id, current_user.id)

    query = (
        db.query(EmergencyTicket)
        .options(
            joinedload(EmergencyTicket.author),
            joinedload(EmergencyTicket.assigned_to),
        )
        .filter(EmergencyTicket.community_id == community_id)
    )

    if ticket_type:
        query = query.filter(EmergencyTicket.ticket_type == ticket_type)
    if ticket_status:
        query = query.filter(EmergencyTicket.status == ticket_status)
    if urgency:
        query = query.filter(EmergencyTicket.urgency == urgency)

    total = query.count()

    if sort == "priority_desc":
        # Pull all matching tickets and sort in Python using the triage score
        # (avoids complex SQL expression for the composite score)
        all_items = query.all()
        all_items.sort(key=_triage_score, reverse=True)
        items = all_items[skip: skip + limit]
    else:
        items = query.order_by(EmergencyTicket.created_at.desc()).offset(skip).limit(limit).all()

    return EmergencyTicketList(items=[_ticket_to_out(t) for t in items], total=total)


@router.get("/tickets/triage", response_model=EmergencyTicketList)
def triage_tickets(
    community_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return all open/in-progress tickets sorted by triage score (highest first).

    Triage score = urgency_weight * 100 + age_hours (capped at 99).
    Overdue tickets (due_at < now) receive a +200 escalation bonus.
    Intended for neighbourhood leaders/admins to prioritise response work.
    """
    _get_community(db, community_id)
    membership = require_membership(db, community_id, current_user.id)

    if membership.role not in ("admin", "leader"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only leaders and admins can access the triage view",
        )

    tickets = (
        db.query(EmergencyTicket)
        .options(
            joinedload(EmergencyTicket.author),
            joinedload(EmergencyTicket.assigned_to),
        )
        .filter(
            EmergencyTicket.community_id == community_id,
            EmergencyTicket.status != "resolved",
        )
        .all()
    )
    tickets.sort(key=_triage_score, reverse=True)
    return EmergencyTicketList(items=[_ticket_to_out(t) for t in tickets], total=len(tickets))


@router.get("/tickets/{ticket_id}", response_model=EmergencyTicketOut)
def get_ticket(
    community_id: int,
    ticket_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a single emergency ticket."""
    _get_community(db, community_id)
    require_membership(db, community_id, current_user.id)

    ticket = (
        db.query(EmergencyTicket)
        .options(
            joinedload(EmergencyTicket.author),
            joinedload(EmergencyTicket.assigned_to),
        )
        .filter(
            EmergencyTicket.id == ticket_id,
            EmergencyTicket.community_id == community_id,
        )
        .first()
    )
    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found"
        )
    return _ticket_to_out(ticket)


@router.patch("/tickets/{ticket_id}", response_model=EmergencyTicketOut)
def update_ticket(
    community_id: int,
    ticket_id: int,
    body: EmergencyTicketUpdate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update a ticket. Author, leaders, or admins can update."""
    _get_community(db, community_id)
    membership = require_membership(db, community_id, current_user.id)

    ticket = (
        db.query(EmergencyTicket)
        .options(
            joinedload(EmergencyTicket.author),
            joinedload(EmergencyTicket.assigned_to),
        )
        .filter(
            EmergencyTicket.id == ticket_id,
            EmergencyTicket.community_id == community_id,
        )
        .first()
    )
    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found"
        )

    # Only author, leader, or admin can update
    if ticket.author_id != current_user.id and membership.role not in (
        "admin",
        "leader",
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the author, leaders, or admins can update this ticket",
        )

    if body.title is not None:
        ticket.title = body.title
    if body.description is not None:
        ticket.description = body.description
    if body.status is not None:
        ticket.status = body.status
    if body.urgency is not None:
        ticket.urgency = body.urgency
    if "due_at" in body.model_fields_set:
        ticket.due_at = body.due_at
    if body.assigned_to_id is not None:
        # Verify assignee is a member
        assignee_membership = (
            db.query(CommunityMember)
            .filter(
                CommunityMember.community_id == community_id,
                CommunityMember.user_id == body.assigned_to_id,
            )
            .first()
        )
        if not assignee_membership:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Assignee must be a community member",
            )
        prev_assigned = ticket.assigned_to_id
        ticket.assigned_to_id = body.assigned_to_id
        if body.assigned_to_id and body.assigned_to_id != prev_assigned:
            background_tasks.add_task(
                dispatch_event,
                db,
                "ticket.assigned",
                {"title": ticket.title, "urgency": ticket.urgency},
                [body.assigned_to_id],
            )

    db.commit()
    db.refresh(ticket)
    return _ticket_to_out(ticket)



# ── Ticket comments ──────────────────────────────────────────────


@router.get("/tickets/{ticket_id}/comments", response_model=list[TicketCommentOut])
def list_ticket_comments(
    community_id: int,
    ticket_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List comments on an emergency ticket. Any community member can view."""
    _get_community(db, community_id)
    require_membership(db, community_id, current_user.id)

    ticket = (
        db.query(EmergencyTicket)
        .filter(
            EmergencyTicket.id == ticket_id,
            EmergencyTicket.community_id == community_id,
        )
        .first()
    )
    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found"
        )

    comments = (
        db.query(TicketComment)
        .options(joinedload(TicketComment.author))
        .filter(TicketComment.ticket_id == ticket_id)
        .order_by(TicketComment.created_at.asc())
        .all()
    )
    return comments


@router.post(
    "/tickets/{ticket_id}/comments",
    response_model=TicketCommentOut,
    status_code=status.HTTP_201_CREATED,
)
def create_ticket_comment(
    community_id: int,
    ticket_id: int,
    body: TicketCommentCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Add a comment to an emergency ticket. Any community member can comment."""
    _get_community(db, community_id)
    require_membership(db, community_id, current_user.id)

    ticket = (
        db.query(EmergencyTicket)
        .filter(
            EmergencyTicket.id == ticket_id,
            EmergencyTicket.community_id == community_id,
        )
        .first()
    )
    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found"
        )

    comment = TicketComment(
        ticket_id=ticket_id,
        author_id=current_user.id,
        body=body.body,
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)
    _ = comment.author
    return comment


# ── Leader management ─────────────────────────────────────────────


@router.get("/leaders", response_model=list[LeaderOut])
def list_leaders(
    community_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List neighbourhood leaders for a community."""
    _get_community(db, community_id)
    require_membership(db, community_id, current_user.id)

    leaders = (
        db.query(CommunityMember)
        .options(joinedload(CommunityMember.user))
        .filter(
            CommunityMember.community_id == community_id,
            CommunityMember.role == "leader",
        )
        .order_by(CommunityMember.joined_at)
        .all()
    )
    return leaders


@router.post(
    "/leaders/{user_id}", response_model=CommunityMemberOut
)
def promote_to_leader(
    community_id: int,
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Promote a member to neighbourhood leader. Admin only."""
    community = _get_community(db, community_id)
    require_admin(db, community_id, current_user.id)

    membership = (
        db.query(CommunityMember)
        .options(joinedload(CommunityMember.user))
        .filter(
            CommunityMember.community_id == community_id,
            CommunityMember.user_id == user_id,
        )
        .first()
    )
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User is not a member of this community",
        )
    if membership.role == "admin":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Cannot change role of an admin",
        )
    if membership.role == "leader":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User is already a leader",
        )

    membership.role = "leader"
    db.commit()
    db.refresh(membership)

    record_activity(
        db,
        event_type="leader_promoted",
        summary=f'promoted {membership.user.display_name} to leader in "{community.name}"',
        actor_id=current_user.id,
        community_id=community_id,
    )
    return membership


@router.delete("/leaders/{user_id}", response_model=CommunityMemberOut)
def demote_leader(
    community_id: int,
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Demote a leader back to regular member. Admin only."""
    community = _get_community(db, community_id)
    require_admin(db, community_id, current_user.id)

    membership = (
        db.query(CommunityMember)
        .options(joinedload(CommunityMember.user))
        .filter(
            CommunityMember.community_id == community_id,
            CommunityMember.user_id == user_id,
        )
        .first()
    )
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User is not a member of this community",
        )
    if membership.role != "leader":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="User is not a leader",
        )

    membership.role = "member"
    db.commit()
    db.refresh(membership)

    record_activity(
        db,
        event_type="leader_demoted",
        summary=f'demoted {membership.user.display_name} from leader in "{community.name}"',
        actor_id=current_user.id,
        community_id=community_id,
    )
    return membership
