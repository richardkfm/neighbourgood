"""Community events CRUD and RSVP endpoints."""

import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.dependencies import get_current_user, get_current_user_optional
from app.models.community import CommunityMember
from app.models.event import Event, EventAttendee
from app.models.user import User
from app.schemas.event import (
    EVENT_CATEGORY_META,
    VALID_EVENT_CATEGORIES,
    EventCategoryInfo,
    EventCreate,
    EventList,
    EventOut,
    EventUpdate,
)
from app.services.activity import record_activity
from app.services.webhooks import dispatch_event

router = APIRouter(prefix="/events", tags=["events"])


def _event_to_out(event: Event, current_user_id: int | None) -> EventOut:
    attendee_ids = {a.user_id for a in event.attendees}
    return EventOut(
        id=event.id,
        title=event.title,
        description=event.description,
        category=event.category,
        start_at=event.start_at,
        end_at=event.end_at,
        location=event.location,
        max_attendees=event.max_attendees,
        organizer_id=event.organizer_id,
        community_id=event.community_id,
        organizer=event.organizer,
        attendee_count=len(attendee_ids),
        is_attending=current_user_id in attendee_ids if current_user_id else False,
        created_at=event.created_at,
    )


def _load_event(event_id: int, db: Session) -> Event:
    event = (
        db.query(Event)
        .options(joinedload(Event.organizer), joinedload(Event.attendees))
        .filter(Event.id == event_id)
        .first()
    )
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    return event


@router.get("/categories", response_model=list[EventCategoryInfo])
def list_event_categories():
    """Return all event categories with labels and icon names."""
    return [
        EventCategoryInfo(value=k, label=v["label"], icon=v["icon"])
        for k, v in EVENT_CATEGORY_META.items()
    ]


@router.get("", response_model=EventList)
def list_events(
    community_id: int | None = Query(None),
    category: str | None = Query(None),
    upcoming: bool | None = Query(None, description="If true, show only future events"),
    q: str | None = Query(None, min_length=1, max_length=100),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
):
    """List events with optional filters. Scoped to user's communities when logged in."""
    query = db.query(Event).options(joinedload(Event.organizer), joinedload(Event.attendees))

    if current_user is not None and community_id is None:
        user_community_ids = [
            cid[0]
            for cid in db.query(CommunityMember.community_id)
            .filter(CommunityMember.user_id == current_user.id)
            .all()
        ]
        if user_community_ids:
            query = query.filter(Event.community_id.in_(user_community_ids))
        else:
            query = query.filter(False)
    elif community_id is not None:
        query = query.filter(Event.community_id == community_id)

    if category:
        query = query.filter(Event.category == category)

    if upcoming:
        query = query.filter(Event.start_at >= datetime.datetime.utcnow())

    if q:
        pattern = f"%{q}%"
        query = query.filter(
            or_(Event.title.ilike(pattern), Event.description.ilike(pattern))
        )

    total = query.count()
    items = query.order_by(Event.start_at.asc()).offset(skip).limit(limit).all()
    current_user_id = current_user.id if current_user else None
    return EventList(
        items=[_event_to_out(e, current_user_id) for e in items],
        total=total,
    )


@router.post("", response_model=EventOut, status_code=status.HTTP_201_CREATED)
def create_event(
    body: EventCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new community event. Organizer must be a member of the community."""
    if body.category not in VALID_EVENT_CATEGORIES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid category. Must be one of: {VALID_EVENT_CATEGORIES}",
        )

    membership = (
        db.query(CommunityMember)
        .filter(
            CommunityMember.community_id == body.community_id,
            CommunityMember.user_id == current_user.id,
        )
        .first()
    )
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You must be a community member to create events",
        )

    event = Event(
        title=body.title,
        description=body.description,
        category=body.category,
        start_at=body.start_at,
        end_at=body.end_at,
        location=body.location,
        max_attendees=body.max_attendees,
        organizer_id=current_user.id,
        community_id=body.community_id,
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    # eager-load relationships
    _ = event.organizer
    _ = event.attendees

    record_activity(
        db,
        event_type="event_created",
        summary=f"created event \"{event.title}\"",
        actor_id=current_user.id,
        community_id=event.community_id,
    )

    background_tasks.add_task(
        dispatch_event,
        db,
        "event.created",
        {
            "actor_name": current_user.display_name,
            "title": event.title,
            "category": event.category,
            "start_at": event.start_at.isoformat(),
        },
        [],
        event.community_id,
    )

    return _event_to_out(event, current_user.id)


@router.get("/{event_id}", response_model=EventOut)
def get_event(
    event_id: int,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
):
    """Get a single event by ID."""
    event = _load_event(event_id, db)
    return _event_to_out(event, current_user.id if current_user else None)


@router.patch("/{event_id}", response_model=EventOut)
def update_event(
    event_id: int,
    body: EventUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update an event (organizer only)."""
    event = _load_event(event_id, db)
    if event.organizer_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your event")

    if body.category is not None and body.category not in VALID_EVENT_CATEGORIES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid category. Must be one of: {VALID_EVENT_CATEGORIES}",
        )

    for field in ("title", "description", "category", "start_at", "end_at", "location", "max_attendees"):
        val = getattr(body, field)
        if val is not None:
            setattr(event, field, val)

    db.commit()
    db.refresh(event)
    _ = event.organizer
    _ = event.attendees
    return _event_to_out(event, current_user.id)


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_event(
    event_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete an event (organizer only)."""
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    if event.organizer_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your event")
    db.delete(event)
    db.commit()


@router.post("/{event_id}/attend", response_model=EventOut, status_code=status.HTTP_201_CREATED)
def attend_event(
    event_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """RSVP to an event."""
    event = _load_event(event_id, db)

    already = (
        db.query(EventAttendee)
        .filter(EventAttendee.event_id == event_id, EventAttendee.user_id == current_user.id)
        .first()
    )
    if already:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Already attending this event"
        )

    if event.max_attendees is not None and len(event.attendees) >= event.max_attendees:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Event is full"
        )

    attendee = EventAttendee(event_id=event_id, user_id=current_user.id)
    db.add(attendee)
    db.commit()

    # reload to get fresh attendee list
    event = _load_event(event_id, db)
    return _event_to_out(event, current_user.id)


@router.delete("/{event_id}/attend", status_code=status.HTTP_204_NO_CONTENT)
def unattend_event(
    event_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Cancel RSVP for an event."""
    attendee = (
        db.query(EventAttendee)
        .filter(EventAttendee.event_id == event_id, EventAttendee.user_id == current_user.id)
        .first()
    )
    if not attendee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="You are not attending this event"
        )
    db.delete(attendee)
    db.commit()
