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


def require_active_membership(
    db: Session, community_id: int, user_id: int
) -> CommunityMember:
    """404 if the community does not exist or is inactive/merged, 403 if the user is not a member."""
    community = require_community(db, community_id)
    if not community.is_active or community.merged_into_id is not None:
        raise HTTPException(status_code=404, detail="Community not found")
    return require_membership(db, community_id, user_id)


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


def get_active_community_membership(
    db: Session, user_id: int, *, exclude_community_id: int | None = None
) -> CommunityMember | None:
    """Return the user's membership in an active, non-merged community, if any.

    Excludes stale membership rows left behind in merged-away (inactive)
    communities, since a merge legitimately leaves the old row in place.
    """
    query = (
        db.query(CommunityMember)
        .join(Community, Community.id == CommunityMember.community_id)
        .filter(
            CommunityMember.user_id == user_id,
            Community.is_active == True,  # noqa: E712
            Community.merged_into_id == None,  # noqa: E711
        )
    )
    if exclude_community_id is not None:
        query = query.filter(CommunityMember.community_id != exclude_community_id)
    return query.first()
