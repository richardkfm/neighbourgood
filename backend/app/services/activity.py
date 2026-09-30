"""Service for recording activity feed events."""

from sqlalchemy.orm import Session

from app.models.activity import Activity


def record_activity(
    db: Session,
    *,
    event_type: str,
    summary: str,
    actor_id: int,
    community_id: int | None = None,
    commit: bool = True,
) -> Activity:
    """Create an activity feed event.

    Pass ``commit=False`` to only flush, so the caller can commit the event
    together with the rest of its unit of work (e.g. mesh sync).
    """
    event = Activity(
        event_type=event_type,
        summary=summary,
        actor_id=actor_id,
        community_id=community_id,
    )
    db.add(event)
    if commit:
        db.commit()
        db.refresh(event)
    else:
        db.flush()
    return event
