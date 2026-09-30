"""Booking endpoints – calendar-based borrow requests with approve/reject flow."""

import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.dependencies import get_current_user
from app.models.booking import BOOKING_STATUSES, Booking
from app.models.resource import Resource
from app.models.user import User
from app.utils.authorization import is_community_member, users_share_community
from app.services.activity import record_activity
from app.services.notifications import notify_booking_request, notify_booking_status
from app.services.webhooks import dispatch_event
from app.schemas.booking import (
    BookingCreate,
    BookingList,
    BookingOut,
    BookingStatusUpdate,
)

router = APIRouter(prefix="/bookings", tags=["bookings"])


def _booking_to_out(b: Booking) -> BookingOut:
    return BookingOut(
        id=b.id,
        resource_id=b.resource_id,
        resource_title=b.resource.title if b.resource else None,
        borrower_id=b.borrower_id,
        borrower=b.borrower,
        start_date=b.start_date,
        end_date=b.end_date,
        message=b.message,
        status=b.status,
        created_at=b.created_at,
        updated_at=b.updated_at,
    )


def _units_exhausted(
    db: Session,
    resource: Resource,
    start: datetime.date,
    end: datetime.date,
    exclude_id: int | None = None,
) -> bool:
    """Return True if every unit of the resource is already reserved at some point in [start, end].

    Each pending/approved booking reserves one unit. The number of units a
    resource can lend at once is ``quantity_available`` (the owner's current
    stock count, see ``PATCH /resources/{id}/inventory``); bookings do not
    decrement it, they are counted here per date instead.
    """
    capacity = max(resource.quantity_available, 1)
    q = db.query(Booking.start_date, Booking.end_date).filter(
        Booking.resource_id == resource.id,
        Booking.status.in_(["pending", "approved"]),
        Booking.start_date <= end,
        Booking.end_date >= start,
    )
    if exclude_id:
        q = q.filter(Booking.id != exclude_id)
    overlapping = q.all()
    if len(overlapping) < capacity:
        return False
    # Peak concurrency inside the requested window is reached on the new
    # booking's first day or on the start day of one of the overlapping bookings.
    check_days = {start} | {b_start for b_start, _ in overlapping if b_start > start}
    return any(
        sum(1 for b_start, b_end in overlapping if b_start <= day <= b_end) >= capacity
        for day in check_days
    )


@router.post("", response_model=BookingOut, status_code=status.HTTP_201_CREATED)
def create_booking(
    body: BookingCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Request to borrow a resource for a date range."""
    resource = db.query(Resource).filter(Resource.id == body.resource_id).first()
    if not resource:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
    if not resource.is_available:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Resource is not available")
    if resource.owner_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot borrow your own resource")

    # Only members of the resource's community may book it. Personal items
    # (no community) can be booked by users who share a community with the owner.
    if resource.community_id is not None:
        if not is_community_member(db, resource.community_id, current_user.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You must be a member of this resource's community to book it",
            )
    elif not users_share_community(db, current_user.id, resource.owner_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You must share a community with the owner to book this resource",
        )

    if body.end_date < body.start_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="end_date must be >= start_date",
        )
    if body.start_date < datetime.date.today():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="start_date must not be in the past",
        )

    if _units_exhausted(db, resource, body.start_date, body.end_date):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Dates overlap with an existing booking",
        )

    booking = Booking(
        resource_id=body.resource_id,
        borrower_id=current_user.id,
        start_date=body.start_date,
        end_date=body.end_date,
        message=body.message,
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)
    _ = booking.borrower
    _ = booking.resource

    # Notify resource owner
    owner = db.query(User).filter(User.id == resource.owner_id).first()
    if owner:
        notify_booking_request(owner.email, current_user.display_name, resource.title)

    record_activity(
        db,
        event_type="resource_borrowed",
        summary=f"requested to borrow \"{resource.title}\"",
        actor_id=current_user.id,
        community_id=resource.community_id,
    )

    background_tasks.add_task(
        dispatch_event,
        db,
        "booking.created",
        {
            "borrower_name": current_user.display_name,
            "resource_title": resource.title,
            "start_date": str(body.start_date),
            "end_date": str(body.end_date),
        },
        [resource.owner_id],
    )

    return _booking_to_out(booking)


@router.get("", response_model=BookingList)
def list_bookings(
    resource_id: int | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    role: str | None = Query(None, description="'borrower' or 'owner' – filter by your role"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List bookings relevant to the current user (as borrower or resource owner)."""
    query = db.query(Booking).options(
        joinedload(Booking.borrower),
        joinedload(Booking.resource),
    )

    if role == "owner":
        # Bookings for resources I own
        owned_ids = [r.id for r in db.query(Resource.id).filter(Resource.owner_id == current_user.id).all()]
        query = query.filter(Booking.resource_id.in_(owned_ids))
    elif role == "borrower":
        query = query.filter(Booking.borrower_id == current_user.id)
    else:
        # Default: show both
        owned_ids = [r.id for r in db.query(Resource.id).filter(Resource.owner_id == current_user.id).all()]
        query = query.filter(
            or_(
                Booking.borrower_id == current_user.id,
                Booking.resource_id.in_(owned_ids),
            )
        )

    if resource_id is not None:
        query = query.filter(Booking.resource_id == resource_id)
    if status_filter:
        query = query.filter(Booking.status == status_filter)

    total = query.count()
    items = query.order_by(Booking.created_at.desc()).offset(skip).limit(limit).all()
    return BookingList(items=[_booking_to_out(b) for b in items], total=total)


@router.get("/{booking_id}", response_model=BookingOut)
def get_booking(
    booking_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a single booking (must be borrower or resource owner)."""
    booking = (
        db.query(Booking)
        .options(joinedload(Booking.borrower), joinedload(Booking.resource))
        .filter(Booking.id == booking_id)
        .first()
    )
    if not booking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")

    resource = db.query(Resource).filter(Resource.id == booking.resource_id).first()
    if booking.borrower_id != current_user.id and (not resource or resource.owner_id != current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your booking")

    return _booking_to_out(booking)


@router.patch("/{booking_id}", response_model=BookingOut)
def update_booking_status(
    booking_id: int,
    body: BookingStatusUpdate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update booking status. Owners (lenders) can approve/reject/complete; borrowers can cancel."""
    booking = (
        db.query(Booking)
        .options(joinedload(Booking.borrower), joinedload(Booking.resource))
        .filter(Booking.id == booking_id)
        .first()
    )
    if not booking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")

    if body.status not in BOOKING_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid status. Must be one of: {BOOKING_STATUSES}",
        )

    resource = db.query(Resource).filter(Resource.id == booking.resource_id).first()
    is_owner = resource and resource.owner_id == current_user.id
    is_borrower = booking.borrower_id == current_user.id

    if not is_owner and not is_borrower:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your booking")

    # Enforce valid transitions
    allowed = _allowed_transitions(booking.status, is_owner, is_borrower)
    if body.status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot transition from '{booking.status}' to '{body.status}'. Allowed: {allowed}",
        )

    booking.status = body.status
    db.commit()
    db.refresh(booking)

    # Notify borrower about status change
    borrower = db.query(User).filter(User.id == booking.borrower_id).first()
    resource_title = resource.title if resource else "Resource"
    if borrower and borrower.id != current_user.id:
        notify_booking_status(borrower.email, resource_title, body.status)
        background_tasks.add_task(
            dispatch_event,
            db,
            "booking.status_changed",
            {"resource_title": resource_title, "status": body.status},
            [borrower.id],
        )

    if body.status == "completed":
        record_activity(
            db,
            event_type="booking_completed",
            summary=f"completed a booking for \"{resource_title}\"",
            actor_id=current_user.id,
            community_id=resource.community_id if resource else None,
        )

    return _booking_to_out(booking)


@router.get("/resource/{resource_id}/calendar", response_model=list[BookingOut])
def get_resource_calendar(
    resource_id: int,
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2020, le=2100),
    db: Session = Depends(get_db),
):
    """Get all active bookings for a resource in a given month (for calendar display)."""
    resource = db.query(Resource).filter(Resource.id == resource_id).first()
    if not resource:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")

    first_day = datetime.date(year, month, 1)
    if month == 12:
        last_day = datetime.date(year + 1, 1, 1) - datetime.timedelta(days=1)
    else:
        last_day = datetime.date(year, month + 1, 1) - datetime.timedelta(days=1)

    bookings = (
        db.query(Booking)
        .options(joinedload(Booking.borrower), joinedload(Booking.resource))
        .filter(
            Booking.resource_id == resource_id,
            Booking.status.in_(["pending", "approved"]),
            Booking.start_date <= last_day,
            Booking.end_date >= first_day,
        )
        .order_by(Booking.start_date)
        .all()
    )
    return [_booking_to_out(b) for b in bookings]


def _allowed_transitions(current: str, is_owner: bool, is_borrower: bool) -> list[str]:
    """Return the statuses a user can transition to from the current status."""
    transitions: list[str] = []
    if current == "pending":
        if is_owner:
            transitions.extend(["approved", "rejected"])
        if is_borrower:
            transitions.append("cancelled")
    elif current == "approved":
        # Only the lender confirms the item came back, so a borrower cannot
        # mark their own booking complete to farm reputation points.
        if is_owner:
            transitions.append("completed")
        if is_borrower:
            transitions.append("cancelled")
    return transitions
