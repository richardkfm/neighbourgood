"""Skill exchange CRUD endpoints with search and category metadata."""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.dependencies import get_current_user, get_current_user_optional
from app.models.community import CommunityMember
from app.models.skill import Skill
from app.models.user import User
from app.routers.users import compute_owner_trust
from app.services.activity import record_activity
from app.services.webhooks import dispatch_event
from app.schemas.skill import (
    SKILL_CATEGORY_META,
    VALID_SKILL_CATEGORIES,
    VALID_SKILL_TYPES,
    SkillCategoryInfo,
    SkillCreate,
    SkillList,
    SkillOut,
    SkillUpdate,
)

router = APIRouter(prefix="/skills", tags=["skills"])


def _skill_to_out(skill: Skill, owner_trust_map: dict | None = None) -> dict:
    """Convert a Skill ORM object to a dict for SkillOut."""
    trust = owner_trust_map.get(skill.owner_id) if owner_trust_map else None
    return {
        "id": skill.id,
        "title": skill.title,
        "description": skill.description,
        "category": skill.category,
        "skill_type": skill.skill_type,
        "owner_id": skill.owner_id,
        "community_id": skill.community_id,
        "owner": skill.owner,
        "owner_trust": trust,
        "created_at": skill.created_at,
        "updated_at": skill.updated_at,
    }


@router.get("/categories", response_model=list[SkillCategoryInfo])
def list_skill_categories():
    """Return all skill categories with labels and icon names."""
    return [
        SkillCategoryInfo(value=k, label=v["label"], icon=v["icon"])
        for k, v in SKILL_CATEGORY_META.items()
    ]


@router.get("", response_model=SkillList)
def list_skills(
    category: str | None = Query(None),
    skill_type: str | None = Query(None, description="Filter: offer or request"),
    community_id: int | None = Query(None, description="Filter by community"),
    q: str | None = Query(None, min_length=1, max_length=100),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
):
    """List skill listings with optional filters and text search.

    If authenticated and no community_id provided, shows skills from user's joined communities.
    If not authenticated or community_id provided, shows public community skills.
    """
    query = db.query(Skill).options(joinedload(Skill.owner))

    # Only show community-scoped skills
    query = query.filter(Skill.community_id.isnot(None))

    # Auto-filter by user's communities if logged in and no specific community requested
    if current_user is not None and community_id is None:
        user_community_ids = db.query(CommunityMember.community_id).filter(
            CommunityMember.user_id == current_user.id
        ).all()
        user_community_ids = [cid[0] for cid in user_community_ids]

        if user_community_ids:
            query = query.filter(Skill.community_id.in_(user_community_ids))
        else:
            # User not in any communities, return empty results
            query = query.filter(False)
    elif community_id is not None:
        query = query.filter(Skill.community_id == community_id)

    if category:
        query = query.filter(Skill.category == category)
    if skill_type:
        query = query.filter(Skill.skill_type == skill_type)
    if q:
        pattern = f"%{q}%"
        query = query.filter(
            or_(
                Skill.title.ilike(pattern),
                Skill.description.ilike(pattern),
            )
        )

    total = query.count()
    items = query.order_by(Skill.created_at.desc()).offset(skip).limit(limit).all()
    # Batch-compute trust for unique owners
    owner_ids = {s.owner_id for s in items}
    trust_map = {oid: compute_owner_trust(db, oid) for oid in owner_ids}
    return SkillList(
        items=[SkillOut(**_skill_to_out(s, trust_map)) for s in items],
        total=total,
    )


@router.post("", response_model=SkillOut, status_code=status.HTTP_201_CREATED)
def create_skill(
    body: SkillCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new skill listing (offer or request)."""
    if body.category not in VALID_SKILL_CATEGORIES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid category. Must be one of: {VALID_SKILL_CATEGORIES}",
        )
    if body.skill_type not in VALID_SKILL_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid skill_type. Must be one of: {VALID_SKILL_TYPES}",
        )

    skill = Skill(
        title=body.title,
        description=body.description,
        category=body.category,
        skill_type=body.skill_type,
        owner_id=current_user.id,
        community_id=body.community_id,
    )
    db.add(skill)
    db.commit()
    db.refresh(skill)
    _ = skill.owner
    event_type = "skill_offered" if skill.skill_type == "offer" else "skill_requested"
    verb = "offered" if skill.skill_type == "offer" else "is looking for"
    record_activity(
        db,
        event_type=event_type,
        summary=f"{verb} \"{skill.title}\"",
        actor_id=current_user.id,
        community_id=skill.community_id,
    )

    if skill.community_id:
        background_tasks.add_task(
            dispatch_event,
            db,
            "skill.created",
            {
                "actor_name": current_user.display_name,
                "title": skill.title,
                "category": skill.category,
                "skill_type": skill.skill_type,
            },
            [],
            skill.community_id,
        )

    trust_map = {skill.owner_id: compute_owner_trust(db, skill.owner_id)}
    return SkillOut(**_skill_to_out(skill, trust_map))


@router.get("/{skill_id}", response_model=SkillOut)
def get_skill(skill_id: int, db: Session = Depends(get_db)):
    """Get a single skill listing by ID."""
    skill = (
        db.query(Skill)
        .options(joinedload(Skill.owner))
        .filter(Skill.id == skill_id)
        .first()
    )
    if not skill:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill not found")
    trust_map = {skill.owner_id: compute_owner_trust(db, skill.owner_id)}
    return SkillOut(**_skill_to_out(skill, trust_map))


@router.patch("/{skill_id}", response_model=SkillOut)
def update_skill(
    skill_id: int,
    body: SkillUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update a skill listing (owner only)."""
    skill = db.query(Skill).filter(Skill.id == skill_id).first()
    if not skill:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill not found")
    if skill.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your skill listing")

    if body.title is not None:
        skill.title = body.title
    if body.description is not None:
        skill.description = body.description
    if body.category is not None:
        if body.category not in VALID_SKILL_CATEGORIES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid category. Must be one of: {VALID_SKILL_CATEGORIES}",
            )
        skill.category = body.category
    if body.skill_type is not None:
        if body.skill_type not in VALID_SKILL_TYPES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid skill_type. Must be one of: {VALID_SKILL_TYPES}",
            )
        skill.skill_type = body.skill_type

    db.commit()
    db.refresh(skill)
    _ = skill.owner
    trust_map = {skill.owner_id: compute_owner_trust(db, skill.owner_id)}
    return SkillOut(**_skill_to_out(skill, trust_map))


@router.delete("/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_skill(
    skill_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a skill listing (owner only)."""
    skill = db.query(Skill).filter(Skill.id == skill_id).first()
    if not skill:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill not found")
    if skill.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your skill listing")
    db.delete(skill)
    db.commit()
