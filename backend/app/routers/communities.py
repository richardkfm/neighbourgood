"""Community endpoints – neighbourhood groups with PLZ-based discovery and merge."""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.dependencies import get_current_user
from app.models.activity import Activity
from app.models.community import Community, CommunityMember
from app.models.event import Event
from app.models.resource import Resource
from app.models.skill import Skill
from app.models.user import User
from app.services.activity import record_activity
from app.services.webhooks import dispatch_event
from app.utils.authorization import get_active_community_membership
from app.schemas.community import (
    CommunityCreate,
    CommunityList,
    CommunityMapItem,
    CommunityMemberOut,
    CommunityOut,
    CommunityUpdate,
    MergeRequest,
    MergeSuggestion,
)

router = APIRouter(prefix="/communities", tags=["communities"])


def _community_to_out(c: Community, member_count: int | None = None) -> CommunityOut:
    return CommunityOut(
        id=c.id,
        name=c.name,
        description=c.description,
        postal_code=c.postal_code,
        city=c.city,
        country_code=c.country_code,
        is_active=c.is_active,
        mode=c.mode,
        latitude=c.latitude,
        longitude=c.longitude,
        member_count=member_count if member_count is not None else len(c.members),
        created_by=c.created_by,
        merged_into_id=c.merged_into_id,
        created_at=c.created_at,
    )


# ── Public map data ────────────────────────────────────────────────


@router.get("/map", response_model=list[CommunityMapItem])
def get_communities_for_map(db: Session = Depends(get_db)):
    """Return lightweight community data for the public explore map. No auth required."""
    communities = (
        db.query(Community)
        .options(joinedload(Community.members))
        .filter(
            Community.is_active == True,  # noqa: E712
            Community.merged_into_id == None,  # noqa: E711
        )
        .all()
    )

    # Batch-count resources and skills per community
    community_ids = [c.id for c in communities]
    resource_counts: dict[int, int] = {}
    skill_counts: dict[int, int] = {}
    if community_ids:
        for cid, cnt in (
            db.query(Resource.community_id, func.count(Resource.id))
            .filter(Resource.community_id.in_(community_ids))
            .group_by(Resource.community_id)
            .all()
        ):
            resource_counts[cid] = cnt
        for cid, cnt in (
            db.query(Skill.community_id, func.count(Skill.id))
            .filter(Skill.community_id.in_(community_ids))
            .group_by(Skill.community_id)
            .all()
        ):
            skill_counts[cid] = cnt

    return [
        CommunityMapItem(
            id=c.id,
            name=c.name,
            city=c.city,
            postal_code=c.postal_code,
            country_code=c.country_code,
            member_count=len(c.members),
            resource_count=resource_counts.get(c.id, 0),
            skill_count=skill_counts.get(c.id, 0),
            mode=c.mode,
            latitude=c.latitude,
            longitude=c.longitude,
        )
        for c in communities
    ]


# ── Search / Discovery ──────────────────────────────────────────────


@router.get("/search", response_model=CommunityList)
def search_communities(
    q: str | None = Query(None, min_length=1, max_length=100, description="Search by name, city, or PLZ"),
    postal_code: str | None = Query(None, description="Filter by exact postal code"),
    city: str | None = Query(None, description="Filter by city name"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Search communities by name, city, or postal code. Used during onboarding."""
    query = db.query(Community).options(
        joinedload(Community.created_by),
        joinedload(Community.members),
    ).filter(
        Community.is_active == True,  # noqa: E712
        Community.merged_into_id == None,  # noqa: E711
    )

    if postal_code:
        query = query.filter(Community.postal_code == postal_code)
    if city:
        query = query.filter(Community.city.ilike(f"%{city}%"))
    if q:
        pattern = f"%{q}%"
        query = query.filter(
            or_(
                Community.name.ilike(pattern),
                Community.city.ilike(pattern),
                Community.postal_code.ilike(pattern),
            )
        )

    total = query.count()
    items = query.order_by(Community.created_at.desc()).offset(skip).limit(limit).all()
    return CommunityList(
        items=[_community_to_out(c) for c in items],
        total=total,
    )


# ── CRUD ─────────────────────────────────────────────────────────────


@router.post("", response_model=CommunityOut, status_code=status.HTTP_201_CREATED)
def create_community(
    body: CommunityCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new community group."""
    community = Community(
        name=body.name,
        description=body.description,
        postal_code=body.postal_code,
        city=body.city,
        country_code=body.country_code,
        latitude=body.latitude,
        longitude=body.longitude,
        created_by_id=current_user.id,
    )
    db.add(community)
    db.flush()

    # Creator becomes admin
    membership = CommunityMember(
        community_id=community.id,
        user_id=current_user.id,
        role="admin",
    )
    db.add(membership)
    db.commit()

    # Re-fetch with eager-loaded relationships to ensure proper serialization
    community = (
        db.query(Community)
        .options(joinedload(Community.created_by), joinedload(Community.members))
        .filter(Community.id == community.id)
        .first()
    )
    return _community_to_out(community)


@router.get("/{community_id}", response_model=CommunityOut)
def get_community(community_id: int, db: Session = Depends(get_db)):
    """Get a community by ID."""
    community = (
        db.query(Community)
        .options(joinedload(Community.created_by), joinedload(Community.members))
        .filter(Community.id == community_id)
        .first()
    )
    if not community:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Community not found")
    return _community_to_out(community)


@router.patch("/{community_id}", response_model=CommunityOut)
def update_community(
    community_id: int,
    body: CommunityUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update community info (admin only)."""
    community = (
        db.query(Community)
        .options(joinedload(Community.created_by), joinedload(Community.members))
        .filter(Community.id == community_id)
        .first()
    )
    if not community:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Community not found")

    membership = (
        db.query(CommunityMember)
        .filter(CommunityMember.community_id == community_id, CommunityMember.user_id == current_user.id)
        .first()
    )
    if not membership or membership.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    if body.name is not None:
        community.name = body.name
    if body.description is not None:
        community.description = body.description

    db.commit()
    db.refresh(community)
    return _community_to_out(community)


# ── My memberships (must be before /{community_id} to avoid path conflict) ──


@router.get("/my/memberships", response_model=list[CommunityOut])
def my_communities(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List communities the current user belongs to, oldest membership first."""
    memberships = (
        db.query(CommunityMember)
        .join(Community, Community.id == CommunityMember.community_id)
        .filter(
            CommunityMember.user_id == current_user.id,
            Community.is_active == True,  # noqa: E712
            Community.merged_into_id == None,  # noqa: E711
        )
        .order_by(CommunityMember.joined_at.asc(), CommunityMember.id.asc())
        .all()
    )
    community_ids = [m.community_id for m in memberships]
    if not community_ids:
        return []

    communities = (
        db.query(Community)
        .options(joinedload(Community.created_by), joinedload(Community.members))
        .filter(Community.id.in_(community_ids))
        .all()
    )
    by_id = {c.id: c for c in communities}
    ordered = [by_id[cid] for cid in community_ids if cid in by_id]
    return [_community_to_out(c) for c in ordered]


# ── Merge suggestions (must be before /{community_id} to avoid path conflict) ──


@router.get("/merge/suggestions", response_model=list[MergeSuggestion])
def get_merge_suggestions(
    community_id: int = Query(..., description="Community to find merge candidates for"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get automatic merge suggestions based on proximity (same postal code or city)."""
    community = (
        db.query(Community)
        .options(joinedload(Community.created_by), joinedload(Community.members))
        .filter(Community.id == community_id)
        .first()
    )
    if not community:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Community not found")

    # Find communities with same postal code or city, excluding self and merged ones
    candidates = (
        db.query(Community)
        .options(joinedload(Community.created_by), joinedload(Community.members))
        .filter(
            Community.id != community_id,
            Community.is_active == True,  # noqa: E712
            Community.merged_into_id == None,  # noqa: E711
            or_(
                Community.postal_code == community.postal_code,
                Community.city == community.city,
            ),
        )
        .all()
    )

    suggestions = []
    for candidate in candidates:
        if candidate.postal_code == community.postal_code:
            reason = f"Same postal code ({community.postal_code})"
        else:
            reason = f"Same city ({community.city})"

        suggestions.append(
            MergeSuggestion(
                source=_community_to_out(community),
                target=_community_to_out(candidate),
                reason=reason,
            )
        )

    return suggestions


# ── Membership ───────────────────────────────────────────────────────


@router.post("/{community_id}/join", response_model=CommunityMemberOut)
def join_community(
    community_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Join a community."""
    community = db.query(Community).filter(Community.id == community_id).first()
    if not community:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Community not found")
    if community.merged_into_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"This community has been merged. Join community #{community.merged_into_id} instead.",
        )
    if not community.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Community not found")

    existing = (
        db.query(CommunityMember)
        .filter(CommunityMember.community_id == community_id, CommunityMember.user_id == current_user.id)
        .first()
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already a member")

    other_membership = get_active_community_membership(
        db, current_user.id, exclude_community_id=community_id
    )
    if other_membership:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You're already a member of a community. Leave your current community before joining another.",
        )

    membership = CommunityMember(
        community_id=community_id,
        user_id=current_user.id,
        role="member",
    )
    db.add(membership)
    db.commit()
    db.refresh(membership)
    _ = membership.user
    record_activity(
        db,
        event_type="member_joined",
        summary=f"joined \"{community.name}\"",
        actor_id=current_user.id,
        community_id=community_id,
    )

    background_tasks.add_task(
        dispatch_event,
        db,
        "member.joined",
        {"actor_name": current_user.display_name, "community_name": community.name},
        [],
        community_id,
    )

    return membership


@router.delete("/{community_id}/leave", status_code=status.HTTP_204_NO_CONTENT)
def leave_community(
    community_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Leave a community."""
    membership = (
        db.query(CommunityMember)
        .filter(CommunityMember.community_id == community_id, CommunityMember.user_id == current_user.id)
        .first()
    )
    if not membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not a member")
    db.delete(membership)
    db.commit()


@router.get("/{community_id}/members", response_model=list[CommunityMemberOut])
def list_members(community_id: int, db: Session = Depends(get_db)):
    """List members of a community."""
    community = db.query(Community).filter(Community.id == community_id).first()
    if not community:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Community not found")

    members = (
        db.query(CommunityMember)
        .options(joinedload(CommunityMember.user))
        .filter(CommunityMember.community_id == community_id)
        .order_by(CommunityMember.joined_at)
        .all()
    )
    return members


# ── Merge ────────────────────────────────────────────────────────────


@router.post("/merge", response_model=CommunityOut)
def merge_communities(
    body: MergeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Merge source community into target. Both community admins or the source admin can initiate."""
    source = (
        db.query(Community)
        .options(joinedload(Community.members), joinedload(Community.created_by))
        .filter(Community.id == body.source_id)
        .first()
    )
    target = (
        db.query(Community)
        .options(joinedload(Community.members), joinedload(Community.created_by))
        .filter(Community.id == body.target_id)
        .first()
    )

    if not source or not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Community not found")
    if source.id == target.id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Cannot merge a community into itself")
    if source.merged_into_id is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Source community is already merged")
    if target.merged_into_id is not None or not target.is_active:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Target community is no longer active")

    # Check that the user is admin of the source community
    source_membership = (
        db.query(CommunityMember)
        .filter(CommunityMember.community_id == source.id, CommunityMember.user_id == current_user.id)
        .first()
    )
    if not source_membership or source_membership.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Must be admin of source community")

    # Move members from source to target (skip duplicates)
    target_user_ids = {m.user_id for m in target.members}
    for member in source.members:
        if member.user_id not in target_user_ids:
            new_member = CommunityMember(
                community_id=target.id,
                user_id=member.user_id,
                role="member",
            )
            db.add(new_member)

    # Move the source community's content so it stays visible to the merged group
    for model in (Resource, Skill, Event, Activity):
        db.query(model).filter(model.community_id == source.id).update(
            {model.community_id: target.id}, synchronize_session=False
        )

    # Mark source as merged
    source.merged_into_id = target.id
    source.is_active = False

    db.commit()
    db.refresh(target)
    return _community_to_out(target)
