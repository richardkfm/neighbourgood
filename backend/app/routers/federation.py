"""Federation endpoints – instance directory, Red Sky alerts, data export/import."""

import datetime
import ipaddress
import json
import logging
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, HttpUrl
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.booking import Booking
from app.models.community import Community, CommunityMember
from app.models.federation import KnownInstance, RedSkyAlert
from app.models.message import Message
from app.models.resource import Resource
from app.models.review import Review
from app.models.skill import Skill
from app.models.user import User

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


class AlertOut(BaseModel):
    id: int
    source_instance_url: str
    source_instance_name: str
    title: str
    description: str
    severity: str
    is_active: bool
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


class AlertCreate(BaseModel):
    title: str
    description: str = ""
    severity: str = "warning"


class AlertReceive(BaseModel):
    """Schema for incoming alerts from remote instances."""
    source_instance_url: str
    source_instance_name: str
    title: str
    description: str = ""
    severity: str = "warning"


class DataExport(BaseModel):
    exported_at: str
    instance: str
    user: dict
    resources: list[dict]
    bookings: list[dict]
    skills: list[dict]
    messages: list[dict]
    reviews: list[dict]
    communities: list[dict]


class MigrationImport(BaseModel):
    display_name: str
    resources: list[dict] = []
    skills: list[dict] = []


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
    """Add a new instance to the directory by URL. Fetches its /instance/info to populate metadata."""
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
    """Re-crawl all known instances to update their metadata and reachability."""
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


def _is_safe_url(url: str) -> bool:
    """Reject URLs that resolve to private/internal IP ranges to prevent SSRF."""
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            return False
        import socket
        resolved = socket.getaddrinfo(hostname, None)
        for _, _, _, _, addr in resolved:
            ip = ipaddress.ip_address(addr[0])
            if ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local:
                return False
        return True
    except Exception:
        return False


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
    active_only: bool = Query(True, description="Only show active alerts"),
    db: Session = Depends(get_db),
):
    """List Red Sky alerts received from other instances."""
    query = db.query(RedSkyAlert).order_by(RedSkyAlert.created_at.desc())
    if active_only:
        query = query.filter(RedSkyAlert.is_active.is_(True))
    return query.all()


@router.post("/alerts/send", response_model=dict)
def broadcast_alert(
    body: AlertCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Broadcast a Red Sky alert to all known reachable instances (admin only)."""
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    payload = {
        "source_instance_url": settings.instance_url,
        "source_instance_name": settings.instance_name,
        "title": body.title,
        "description": body.description,
        "severity": body.severity,
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


@router.post("/alerts/receive", response_model=AlertOut, status_code=status.HTTP_201_CREATED)
def receive_alert(body: AlertReceive, db: Session = Depends(get_db)):
    """Receive a Red Sky alert from a remote instance. Only accepts alerts from known instances."""
    source_url = body.source_instance_url.rstrip("/")
    known = db.query(KnownInstance).filter(KnownInstance.url == source_url).first()
    if not known:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Alerts only accepted from known instances",
        )
    if body.severity not in ("info", "warning", "critical"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="severity must be one of: info, warning, critical",
        )
    alert = RedSkyAlert(
        source_instance_url=source_url,
        source_instance_name=body.source_instance_name[:200],
        title=body.title[:300],
        description=body.description[:5000] if body.description else "",
        severity=body.severity,
    )
    db.add(alert)
    db.commit()
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
    bookings = db.query(Booking).filter(Booking.borrower_id == uid).all()
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
                "resource_id": b.resource_id,
                "start_date": str(b.start_date),
                "end_date": str(b.end_date),
                "message": b.message,
                "status": b.status,
                "created_at": _dt(b.created_at),
            }
            for b in bookings
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
    re-create their listings on this instance.
    """
    created_resources = 0
    created_skills = 0

    for r in body.resources:
        resource = Resource(
            title=r.get("title", "Imported Resource"),
            description=r.get("description"),
            category=r.get("category", "other"),
            condition=r.get("condition"),
            is_available=r.get("is_available", True),
            owner_id=current_user.id,
        )
        db.add(resource)
        created_resources += 1

    for s in body.skills:
        skill = Skill(
            title=s.get("title", "Imported Skill"),
            description=s.get("description"),
            category=s.get("category", "other"),
            skill_type=s.get("skill_type", "offer"),
            owner_id=current_user.id,
        )
        db.add(skill)
        created_skills += 1

    db.commit()

    return {
        "message": "Import complete",
        "resources_created": created_resources,
        "skills_created": created_skills,
    }
