"""Federation endpoints – instance directory, Red Sky alerts, data export/import."""

import datetime
import json
import logging
import secrets
from typing import Annotated
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from pydantic import AfterValidator, BaseModel, Field, HttpUrl, model_validator
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.booking import Booking
from app.models.community import Community, CommunityMember
from app.models.federation import KnownInstance, RedSkyAlert, SentAlert
from app.models.message import Message
from app.models.resource import Resource
from app.models.review import Review
from app.models.skill import Skill
from app.models.user import User
from app.schemas.common import UTCDateTime
from app.schemas.resource import VALID_CATEGORIES, VALID_CONDITIONS
from app.schemas.skill import VALID_SKILL_CATEGORIES, VALID_SKILL_TYPES
from app.utils.net import is_safe_url as _is_safe_url

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/federation", tags=["federation"])


# ── Schemas ─────────────────────────────────────────────────────────


class InstanceDirectoryEntry(BaseModel):
    id: int
    url: str
    name: str
    description: str
    region: str
    version: str
    platform_mode: str
    admin_contact: str
    community_count: int
    user_count: int
    resource_count: int
    skill_count: int
    event_count: int
    active_user_count: int
    is_reachable: bool
    last_seen_at: datetime.datetime
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


class InstanceAdd(BaseModel):
    url: HttpUrl


ALERT_DEFAULT_DURATION_HOURS = 48
ALERT_MAX_DURATION_HOURS = 336  # two weeks


def _utcnow() -> datetime.datetime:
    return datetime.datetime.utcnow()


def _naive_utc(value: datetime.datetime) -> datetime.datetime:
    if value.tzinfo is not None:
        value = value.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    return value


# Accepts aware or naive (UTC) input, stores naive UTC, serialises with "Z"
AlertDateTime = Annotated[UTCDateTime, AfterValidator(_naive_utc)]


class AlertOut(BaseModel):
    id: int
    source_instance_url: str
    source_instance_name: str
    title: str
    description: str
    severity: str
    # False once dismissed by an admin or past expires_at
    is_active: bool
    expires_at: UTCDateTime | None = None
    created_at: UTCDateTime

    model_config = {"from_attributes": True}

    @model_validator(mode="after")
    def _expire(self):
        if self.expires_at is not None and self.expires_at <= _utcnow():
            self.is_active = False
        return self


class AlertCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    description: str = Field("", max_length=5000)
    severity: str = Field("warning", pattern="^(info|warning|critical)$")
    # How long receivers show the alert as active
    duration_hours: int = Field(ALERT_DEFAULT_DURATION_HOURS, ge=1, le=ALERT_MAX_DURATION_HOURS)


_ALERT_UID_PATTERN = "^[A-Za-z0-9_-]{16,64}$"


class AlertReceive(BaseModel):
    """Notification that a remote instance published an alert.

    Only the source URL and alert UID are used: the alert itself is fetched back
    from the (known) source instance, so a forged notification cannot inject
    content. Title/description/severity are still sent for older receivers.
    """
    source_instance_url: str = Field(..., max_length=500)
    alert_uid: str = Field(..., pattern=_ALERT_UID_PATTERN)
    source_instance_name: str = Field("", max_length=200)
    title: str = Field("", max_length=300)
    description: str = Field("", max_length=5000)
    severity: str = Field("warning", max_length=20)


class PublishedAlert(BaseModel):
    """An alert as published by its source instance, fetched back for verification."""
    alert_uid: str = Field(..., pattern=_ALERT_UID_PATTERN)
    title: str = Field(..., min_length=1, max_length=300)
    description: str = Field("", max_length=5000)
    severity: str = Field(..., pattern="^(info|warning|critical)$")
    # Optional so alerts from senders predating expiry still verify
    expires_at: AlertDateTime | None = None


class DataExport(BaseModel):
    exported_at: str
    instance: str
    user: dict
    resources: list[dict]
    # Bookings I made as a borrower (unchanged shape for existing consumers).
    bookings: list[dict]
    # Bookings other members made on resources I own; kept apart from my own borrowings.
    lending_bookings: list[dict] = []
    skills: list[dict]
    messages: list[dict]
    reviews: list[dict]
    communities: list[dict]


MAX_IMPORT_ITEMS = 200


class MigrationImport(BaseModel):
    display_name: str = Field(..., max_length=100)
    resources: list[dict] = []
    skills: list[dict] = []

    @model_validator(mode="after")
    def _cap_items(self):
        if len(self.resources) + len(self.skills) > MAX_IMPORT_ITEMS:
            raise ValueError(f"At most {MAX_IMPORT_ITEMS} items (resources + skills) can be imported per request")
        return self


# ── Instance Directory ──────────────────────────────────────────────


@router.get("/directory", response_model=list[InstanceDirectoryEntry])
def list_known_instances(
    reachable_only: bool = Query(False, description="Only show reachable instances"),
    db: Session = Depends(get_db),
):
    """List all known NeighbourGood instances in the directory."""
    query = db.query(KnownInstance).order_by(KnownInstance.last_seen_at.desc())
    if reachable_only:
        query = query.filter(KnownInstance.is_reachable.is_(True))
    return query.all()


@router.post("/directory", response_model=InstanceDirectoryEntry, status_code=status.HTTP_201_CREATED)
def add_instance(
    body: InstanceAdd,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Add a new instance to the directory by URL (admin only). Fetches its /instance/info to populate metadata.

    Known instances are trusted as alert sources, so only admins may add them.
    """
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    url = str(body.url).rstrip("/")

    existing = db.query(KnownInstance).filter(KnownInstance.url == url).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Instance already in directory")

    # Fetch remote instance info
    info = _fetch_instance_info(url)
    if info is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Could not reach instance or invalid /instance/info response",
        )

    instance = KnownInstance(
        url=url,
        name=info.get("name", url),
        description=info.get("description", ""),
        region=info.get("region", ""),
        version=info.get("version", ""),
        platform_mode=info.get("platform_mode", "blue"),
        admin_contact=info.get("admin_contact", ""),
        community_count=info.get("community_count", 0),
        user_count=info.get("user_count", 0),
        resource_count=info.get("resource_count", 0),
        skill_count=info.get("skill_count", 0),
        event_count=info.get("event_count", 0),
        active_user_count=info.get("active_user_count", 0),
        is_reachable=True,
        last_seen_at=datetime.datetime.utcnow(),
    )
    db.add(instance)
    db.commit()
    db.refresh(instance)
    return instance


@router.delete("/directory/{instance_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_instance(
    instance_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Remove an instance from the directory (admin only)."""
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    inst = db.query(KnownInstance).filter(KnownInstance.id == instance_id).first()
    if not inst:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instance not found")
    db.delete(inst)
    db.commit()


@router.post("/directory/refresh", response_model=list[InstanceDirectoryEntry])
def refresh_directory(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Re-crawl all known instances to update their metadata and reachability (admin only)."""
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    instances = db.query(KnownInstance).all()
    for inst in instances:
        info = _fetch_instance_info(inst.url)
        if info:
            inst.name = info.get("name", inst.name)
            inst.description = info.get("description", inst.description)
            inst.region = info.get("region", inst.region)
            inst.version = info.get("version", inst.version)
            inst.platform_mode = info.get("platform_mode", inst.platform_mode)
            inst.admin_contact = info.get("admin_contact", inst.admin_contact)
            inst.community_count = info.get("community_count", inst.community_count)
            inst.user_count = info.get("user_count", inst.user_count)
            inst.resource_count = info.get("resource_count", inst.resource_count)
            inst.skill_count = info.get("skill_count", inst.skill_count)
            inst.event_count = info.get("event_count", inst.event_count)
            inst.active_user_count = info.get("active_user_count", inst.active_user_count)
            inst.is_reachable = True
            inst.last_seen_at = datetime.datetime.utcnow()
        else:
            inst.is_reachable = False

    db.commit()
    return instances


def _fetch_instance_info(base_url: str) -> dict | None:
    """Fetch /instance/info from a remote NeighbourGood instance."""
    if not _is_safe_url(base_url):
        logger.warning("Blocked SSRF attempt to internal URL: %s", base_url)
        return None
    try:
        resp = httpx.get(f"{base_url}/instance/info", timeout=10)
        if resp.status_code == 200:
            return resp.json()
    except Exception as exc:
        logger.warning("Failed to reach %s: %s", base_url, exc)
    return None


# ── Cross-Instance Red Sky Alerts ───────────────────────────────────


@router.get("/alerts", response_model=list[AlertOut])
def list_alerts(
    active_only: bool = Query(True, description="Only show active (not dismissed, not expired) alerts"),
    db: Session = Depends(get_db),
):
    """List Red Sky alerts received from other instances."""
    query = db.query(RedSkyAlert).order_by(RedSkyAlert.created_at.desc())
    if active_only:
        query = query.filter(
            RedSkyAlert.is_active.is_(True),
            or_(RedSkyAlert.expires_at.is_(None), RedSkyAlert.expires_at > _utcnow()),
        )
    return query.all()


@router.get("/alerts/{alert_id}", response_model=AlertOut)
def get_alert(
    alert_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """A single received alert (any logged-in user), including dismissed or expired ones."""
    alert = db.query(RedSkyAlert).filter(RedSkyAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    return alert


@router.post("/alerts/send", response_model=dict)
def broadcast_alert(
    body: AlertCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Broadcast a Red Sky alert to all known reachable instances (admin only)."""
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    if not settings.instance_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Set NG_INSTANCE_URL so other instances can verify alerts from this instance",
        )

    sent_alert = SentAlert(
        alert_uid=secrets.token_urlsafe(24),
        title=body.title,
        description=body.description,
        severity=body.severity,
        sent_by_id=current_user.id,
        expires_at=_utcnow() + datetime.timedelta(hours=body.duration_hours),
    )
    db.add(sent_alert)
    db.commit()

    payload = {
        "source_instance_url": settings.instance_url.rstrip("/"),
        "source_instance_name": settings.instance_name,
        "alert_uid": sent_alert.alert_uid,
        "title": body.title,
        "description": body.description,
        "severity": body.severity,
        "expires_at": sent_alert.expires_at.isoformat() + "Z",
    }

    instances = db.query(KnownInstance).filter(KnownInstance.is_reachable.is_(True)).all()
    sent = 0
    failed = 0
    for inst in instances:
        try:
            resp = httpx.post(f"{inst.url}/federation/alerts/receive", json=payload, timeout=10)
            if resp.status_code in (200, 201):
                sent += 1
            else:
                failed += 1
        except Exception:
            failed += 1

    return {"sent": sent, "failed": failed, "total": len(instances)}


@router.get("/alerts/outgoing/{alert_uid}", response_model=PublishedAlert)
def get_published_alert(alert_uid: str, db: Session = Depends(get_db)):
    """Return an alert this instance broadcast, so receivers can verify it came from here."""
    alert = db.query(SentAlert).filter(SentAlert.alert_uid == alert_uid).first()
    if not alert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    return alert


def _fetch_published_alert(base_url: str, alert_uid: str) -> PublishedAlert | None:
    """Fetch an alert back from its source instance. Returns None if it cannot be verified."""
    if not _is_safe_url(base_url):
        logger.warning("Blocked SSRF attempt to internal URL: %s", base_url)
        return None
    try:
        resp = httpx.get(
            f"{base_url}/federation/alerts/outgoing/{quote(alert_uid, safe='')}",
            timeout=10,
            follow_redirects=False,
        )
        if resp.status_code != 200:
            return None
        published = PublishedAlert.model_validate(resp.json())
    except Exception as exc:
        logger.warning("Could not verify alert %s from %s: %s", alert_uid, base_url, exc)
        return None
    return published if published.alert_uid == alert_uid else None


@router.post("/alerts/receive", response_model=AlertOut, status_code=status.HTTP_201_CREATED)
def receive_alert(body: AlertReceive, db: Session = Depends(get_db)):
    """Receive a Red Sky alert from a known remote instance.

    The request body is only a notification: the alert is fetched back from the
    source instance's URL in our directory and stored from that response, so
    anyone who can reach this endpoint still cannot forge an alert.
    """
    source_url = body.source_instance_url.rstrip("/")
    known = db.query(KnownInstance).filter(KnownInstance.url == source_url).first()
    if not known:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Alerts only accepted from known instances",
        )

    existing = (
        db.query(RedSkyAlert)
        .filter(RedSkyAlert.source_instance_url == known.url, RedSkyAlert.source_alert_uid == body.alert_uid)
        .first()
    )
    if existing:
        return existing

    published = _fetch_published_alert(known.url, body.alert_uid)
    if published is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Alert could not be verified with its source instance",
        )

    # The sender picks the duration; never keep an alert active longer than
    # the maximum a sender may choose, and give legacy alerts the default
    now = _utcnow()
    latest = now + datetime.timedelta(hours=ALERT_MAX_DURATION_HOURS)
    expires_at = published.expires_at or now + datetime.timedelta(hours=ALERT_DEFAULT_DURATION_HOURS)
    alert = RedSkyAlert(
        source_instance_url=known.url,
        source_alert_uid=published.alert_uid,
        source_instance_name=known.name[:200],
        title=published.title,
        description=published.description,
        severity=published.severity,
        expires_at=min(expires_at, latest),
    )
    db.add(alert)
    try:
        db.commit()
    except IntegrityError:
        # A concurrent delivery of the same alert won the race
        db.rollback()
        return (
            db.query(RedSkyAlert)
            .filter(RedSkyAlert.source_instance_url == known.url, RedSkyAlert.source_alert_uid == body.alert_uid)
            .first()
        )
    db.refresh(alert)
    return alert


@router.patch("/alerts/{alert_id}/dismiss", response_model=AlertOut)
def dismiss_alert(
    alert_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Dismiss a Red Sky alert (admin only)."""
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    alert = db.query(RedSkyAlert).filter(RedSkyAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    alert.is_active = False
    db.commit()
    db.refresh(alert)
    return alert


# ── User Data Export ────────────────────────────────────────────────


@router.get("/export/my-data", response_model=DataExport)
def export_my_data(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Export all of the authenticated user's data as a portable JSON backup."""
    uid = current_user.id

    resources = db.query(Resource).filter(Resource.owner_id == uid).all()
    bookings = (
        db.query(Booking)
        .options(joinedload(Booking.resource))
        .filter(Booking.borrower_id == uid)
        .all()
    )
    lending_bookings = (
        db.query(Booking)
        .options(joinedload(Booking.resource), joinedload(Booking.borrower))
        .join(Resource, Resource.id == Booking.resource_id)
        .filter(Resource.owner_id == uid)
        .all()
    )
    skills = db.query(Skill).filter(Skill.owner_id == uid).all()
    sent_messages = db.query(Message).filter(Message.sender_id == uid).all()
    received_messages = db.query(Message).filter(Message.recipient_id == uid).all()
    reviews_given = db.query(Review).filter(Review.reviewer_id == uid).all()
    reviews_received = db.query(Review).filter(Review.reviewee_id == uid).all()

    memberships = (
        db.query(CommunityMember)
        .filter(CommunityMember.user_id == uid)
        .all()
    )
    community_ids = [m.community_id for m in memberships]
    communities = (
        db.query(Community)
        .filter(Community.id.in_(community_ids))
        .all()
        if community_ids else []
    )

    def _dt(v):
        return v.isoformat() if v else None

    return DataExport(
        exported_at=datetime.datetime.utcnow().isoformat(),
        instance=settings.instance_url or settings.instance_name,
        user={
            "email": current_user.email,
            "display_name": current_user.display_name,
            "neighbourhood": current_user.neighbourhood,
            "role": current_user.role,
            "created_at": _dt(current_user.created_at),
        },
        resources=[
            {
                "title": r.title,
                "description": r.description,
                "category": r.category,
                "condition": r.condition,
                "is_available": r.is_available,
                "created_at": _dt(r.created_at),
            }
            for r in resources
        ],
        bookings=[
            {
                "role": "borrower",
                "resource_id": b.resource_id,
                "resource_title": b.resource.title if b.resource else None,
                "start_date": str(b.start_date),
                "end_date": str(b.end_date),
                "message": b.message,
                "status": b.status,
                "created_at": _dt(b.created_at),
            }
            for b in bookings
        ],
        # Other members are identified by display name only, never by email.
        lending_bookings=[
            {
                "role": "lender",
                "resource_id": b.resource_id,
                "resource_title": b.resource.title if b.resource else None,
                "borrower_display_name": b.borrower.display_name if b.borrower else None,
                "start_date": str(b.start_date),
                "end_date": str(b.end_date),
                "message": b.message,
                "status": b.status,
                "created_at": _dt(b.created_at),
            }
            for b in lending_bookings
        ],
        skills=[
            {
                "title": s.title,
                "description": s.description,
                "category": s.category,
                "skill_type": s.skill_type,
                "created_at": _dt(s.created_at),
            }
            for s in skills
        ],
        messages=[
            {
                "direction": "sent" if m.sender_id == uid else "received",
                "body": m.body,
                "created_at": _dt(m.created_at),
            }
            for m in sent_messages + received_messages
        ],
        reviews=[
            {
                "role": "reviewer" if r.reviewer_id == uid else "reviewee",
                "rating": r.rating,
                "comment": r.comment,
                "created_at": _dt(r.created_at),
            }
            for r in reviews_given + reviews_received
        ],
        communities=[
            {
                "name": c.name,
                "postal_code": c.postal_code,
                "city": c.city,
                "role": next(
                    (m.role for m in memberships if m.community_id == c.id), "member"
                ),
            }
            for c in communities
        ],
    )


# ── Instance Migration ──────────────────────────────────────────────


@router.post("/migrate/import", status_code=status.HTTP_201_CREATED)
def import_user_data(
    body: MigrationImport,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Import resources and skills from a data export into the current user's account.

    This allows a user who exported their data from another instance to
    re-create their listings on this instance. Imported listings are flagged
    ``imported`` and earn no reputation points.
    """
    created_resources = 0
    created_skills = 0

    def _text(value, default: str | None, limit: int) -> str | None:
        if not isinstance(value, str) or not value.strip():
            return default
        return value.strip()[:limit]

    for r in body.resources:
        category = r.get("category")
        condition = r.get("condition")
        resource = Resource(
            title=_text(r.get("title"), "Imported Resource", 200),
            description=_text(r.get("description"), None, 5000),
            category=category if category in VALID_CATEGORIES else "other",
            condition=condition if condition in VALID_CONDITIONS else None,
            is_available=bool(r.get("is_available", True)),
            owner_id=current_user.id,
            imported=True,
        )
        db.add(resource)
        created_resources += 1

    for s in body.skills:
        category = s.get("category")
        skill_type = s.get("skill_type")
        skill = Skill(
            title=_text(s.get("title"), "Imported Skill", 200),
            description=_text(s.get("description"), None, 5000),
            category=category if category in VALID_SKILL_CATEGORIES else "other",
            skill_type=skill_type if skill_type in VALID_SKILL_TYPES else "offer",
            owner_id=current_user.id,
            imported=True,
        )
        db.add(skill)
        created_skills += 1

    db.commit()

    return {
        "message": "Import complete",
        "resources_created": created_resources,
        "skills_created": created_skills,
    }
