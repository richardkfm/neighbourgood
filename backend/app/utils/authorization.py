"""Shared authorization helpers for route handlers."""

from fastapi import HTTPException

from app.models.community import Community, CommunityMember
from app.models.user import User
from sqlalchemy.orm import Session


def require_community(db: Session, community_id: int) -> Community:
    """Return the community or raise 404."""
    community = db.query(Community).filter(Community.id == community_id).first()
    if not community:
        raise HTTPException(status_code=404, detail="Community not found")
    return community


def require_membership(
    db: Session, community_id: int, user_id: int
) -> CommunityMember:
    """Return the membership record or raise 403."""
    member = (
        db.query(CommunityMember)
        .filter(
            CommunityMember.community_id == community_id,
            CommunityMember.user_id == user_id,
        )
        .first()
    )
    if not member:
        raise HTTPException(status_code=403, detail="Not a member of this community")
    return member


def require_admin(
    db: Session, community_id: int, user_id: int
) -> CommunityMember:
    """Return the membership record if user is admin, else raise 403."""
    member = require_membership(db, community_id, user_id)
    if member.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return member


def require_admin_or_leader(
    db: Session, community_id: int, user_id: int
) -> CommunityMember:
    """Return the membership record if user is admin or leader, else raise 403."""
    member = require_membership(db, community_id, user_id)
    if member.role not in ("admin", "leader"):
        raise HTTPException(
            status_code=403, detail="Admin or leader access required"
        )
    return member
