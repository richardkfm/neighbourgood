"""In-app messaging endpoints – direct messages between users.

Messages are restricted to users who share at least one community.
"""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import and_, case, func, or_
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.dependencies import get_current_user
from app.models.community import CommunityMember
from app.models.message import Message
from app.models.user import User
from app.utils.authorization import users_share_community as _share_community
from app.services.notifications import notify_new_message
from app.services.webhooks import dispatch_event
from app.schemas.message import (
    ConversationSummary,
    MarkReadAck,
    MessageCreate,
    MessageableUser,
    MessageList,
    MessageOut,
    UnreadCount,
)
from app.schemas.user import UserProfile

router = APIRouter(prefix="/messages", tags=["messages"])


@router.get("/contacts", response_model=list[MessageableUser])
def list_messageable_users(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all users who share a community with the current user (messageable contacts)."""
    my_communities = (
        db.query(CommunityMember.community_id)
        .filter(CommunityMember.user_id == current_user.id)
        .subquery()
    )
    fellow_member_ids = (
        db.query(CommunityMember.user_id)
        .filter(
            CommunityMember.community_id.in_(
                db.query(my_communities.c.community_id)
            ),
            CommunityMember.user_id != current_user.id,
        )
        .distinct()
        .subquery()
    )
    users = (
        db.query(User)
        .filter(
            User.id.in_(db.query(fellow_member_ids.c.user_id)),
            User.is_active == True,  # noqa: E712
        )
        .order_by(User.display_name)
        .all()
    )
    return users


@router.post("", response_model=MessageOut, status_code=status.HTTP_201_CREATED)
def send_message(
    body: MessageCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Send a message to another user. Both users must share at least one community."""
    if body.recipient_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Cannot send a message to yourself",
        )

    recipient = db.query(User).filter(User.id == body.recipient_id, User.is_active).first()
    if not recipient:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipient not found")

    if not _share_community(db, current_user.id, body.recipient_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only message users within your communities",
        )

    msg = Message(
        sender_id=current_user.id,
        recipient_id=body.recipient_id,
        booking_id=body.booking_id,
        skill_id=body.skill_id,
        body=body.body,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    _ = msg.sender
    _ = msg.recipient

    notify_new_message(recipient.email, current_user.display_name)

    background_tasks.add_task(
        dispatch_event,
        db,
        "message.new",
        {"sender_name": current_user.display_name},
        [body.recipient_id],
    )

    return msg


@router.get("", response_model=MessageList)
def list_messages(
    partner_id: int | None = Query(None, description="Filter conversation with a specific user"),
    booking_id: int | None = Query(None, description="Filter messages related to a booking"),
    skill_id: int | None = Query(None, description="Filter messages related to a skill"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List messages for the current user, optionally filtered by conversation partner or booking."""
    query = db.query(Message).options(
        joinedload(Message.sender),
        joinedload(Message.recipient),
    ).filter(
        or_(
            Message.sender_id == current_user.id,
            Message.recipient_id == current_user.id,
        )
    )

    if partner_id is not None:
        query = query.filter(
            or_(
                and_(Message.sender_id == current_user.id, Message.recipient_id == partner_id),
                and_(Message.sender_id == partner_id, Message.recipient_id == current_user.id),
            )
        )

    if booking_id is not None:
        query = query.filter(Message.booking_id == booking_id)

    if skill_id is not None:
        query = query.filter(Message.skill_id == skill_id)

    total = query.count()
    items = query.order_by(Message.created_at.desc()).offset(skip).limit(limit).all()
    return MessageList(items=items, total=total)


@router.get("/conversations", response_model=list[ConversationSummary])
def list_conversations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all conversation partners with the last message and unread count."""
    # Get the partner ID for each message (the other user)
    partner_id_col = case(
        (Message.sender_id == current_user.id, Message.recipient_id),
        else_=Message.sender_id,
    ).label("partner_id")

    # Subquery: get distinct partner IDs
    partner_subq = (
        db.query(partner_id_col)
        .filter(
            or_(
                Message.sender_id == current_user.id,
                Message.recipient_id == current_user.id,
            )
        )
        .distinct()
        .subquery()
    )

    partner_ids = [row[0] for row in db.query(partner_subq.c.partner_id).all()]
    if not partner_ids:
        return []

    # Bulk-fetch all partners in one query (fixes N+1)
    partners = db.query(User).filter(User.id.in_(partner_ids)).all()
    partner_map = {p.id: p for p in partners}

    conversations = []
    for pid in partner_ids:
        partner = partner_map.get(pid)
        if not partner:
            continue

        # Last message in this conversation
        last_msg = (
            db.query(Message)
            .filter(
                or_(
                    and_(Message.sender_id == current_user.id, Message.recipient_id == pid),
                    and_(Message.sender_id == pid, Message.recipient_id == current_user.id),
                )
            )
            .order_by(Message.created_at.desc())
            .first()
        )

        # Count unread from this partner
        unread = (
            db.query(func.count(Message.id))
            .filter(
                Message.sender_id == pid,
                Message.recipient_id == current_user.id,
                Message.is_read == False,  # noqa: E712
            )
            .scalar()
        )

        if last_msg:
            conversations.append(
                ConversationSummary(
                    partner=partner,
                    last_message_body=last_msg.body,
                    last_message_at=last_msg.created_at,
                    unread_count=unread or 0,
                )
            )

    conversations.sort(key=lambda c: c.last_message_at, reverse=True)
    return conversations


@router.get("/unread", response_model=UnreadCount)
def get_unread_count(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get the total number of unread messages for the current user."""
    count = (
        db.query(func.count(Message.id))
        .filter(
            Message.recipient_id == current_user.id,
            Message.is_read == False,  # noqa: E712
        )
        .scalar()
    )
    return UnreadCount(count=count or 0)


@router.patch("/{message_id}/read", response_model=MessageOut)
def mark_as_read(
    message_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mark a message as read (recipient only)."""
    msg = (
        db.query(Message)
        .options(joinedload(Message.sender), joinedload(Message.recipient))
        .filter(Message.id == message_id)
        .first()
    )
    if not msg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
    if msg.recipient_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your message")

    msg.is_read = True
    db.commit()
    db.refresh(msg)
    return msg


@router.post("/conversation/{partner_id}/read", response_model=MarkReadAck)
def mark_conversation_read(
    partner_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mark all messages from a partner as read."""
    marked = (
        db.query(Message)
        .filter(
            Message.sender_id == partner_id,
            Message.recipient_id == current_user.id,
            Message.is_read == False,  # noqa: E712
        )
        .update({"is_read": True})
    )
    db.commit()
    return MarkReadAck(ok=True, marked=int(marked or 0))
