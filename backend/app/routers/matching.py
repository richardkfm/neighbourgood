"""Smart matching API: skill matches, resource suggestions, unmet needs."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.community import Community, CommunityMember
from app.models.user import User
from app.schemas.matching import MatchingStatus, MatchSuggestion, UnmetNeed
from app.services.ai_client import get_ai_client
from app.services.matching import (
    enhance_with_ai,
    get_resource_suggestions,
    get_skill_matches,
    get_unmet_needs,
)
from app.services.mode import effective_mode

router = APIRouter(prefix="/matching", tags=["matching"])


@router.get("/status", response_model=MatchingStatus)
def matching_status(current_user: User = Depends(get_current_user)):
    """Check whether AI-enhanced matching is available."""
    ai = get_ai_client()
    return MatchingStatus(
        ai_available=ai is not None,
        ai_provider=settings.ai_provider if ai else None,
        ai_model=settings.ai_model if ai else None,
    )


@router.get("/suggestions", response_model=list[MatchSuggestion])
def get_suggestions(
    community_id: int | None = Query(None, description="Scope to a specific community"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return personalised skill match and resource suggestions."""
    # Validate community membership if a specific community is requested
    if community_id is not None:
        membership = db.query(CommunityMember).filter(
            CommunityMember.community_id == community_id,
            CommunityMember.user_id == current_user.id,
        ).first()
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not a member of this community",
            )

    skill_matches = get_skill_matches(db, current_user, community_id)
    resource_suggestions = get_resource_suggestions(db, current_user, community_id)

    combined = skill_matches + resource_suggestions
    combined.sort(key=lambda x: x["score"], reverse=True)

    # Optional AI re-ranking
    ai_client = get_ai_client()
    if ai_client and combined:
        context = f"User: {current_user.display_name}"
        combined = enhance_with_ai(ai_client, combined, context)

    return [MatchSuggestion(**s) for s in combined[:20]]


@router.get("/unmet-needs", response_model=list[UnmetNeed])
def unmet_needs(
    community_id: int = Query(..., description="Community in Red Sky mode"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List emergency requests with few or no matching offers (Red Sky only)."""
    community = db.query(Community).filter(Community.id == community_id).first()
    if not community:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Community not found",
        )

    if effective_mode(community) != "red":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unmet needs are only available in Red Sky mode",
        )

    # Require leader or admin role
    membership = db.query(CommunityMember).filter(
        CommunityMember.community_id == community_id,
        CommunityMember.user_id == current_user.id,
    ).first()
    if not membership or membership.role not in ("leader", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only leaders and admins can view unmet needs",
        )

    results = get_unmet_needs(db, community_id)
    return [UnmetNeed(**r) for r in results]
