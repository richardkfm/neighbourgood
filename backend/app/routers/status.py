"""Status endpoint – health check and platform mode indicator."""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.community import Community
from app.services.mode import effective_mode, is_global_red

router = APIRouter(tags=["status"])


class StatusOut(BaseModel):
    status: str
    version: str
    # Instance-wide mode (NG_PLATFORM_MODE)
    mode: str
    # Mode to behave as: the instance mode, or with ?community_id= that
    # community's effective mode (red while the instance or the community is red)
    effective_mode: str
    # True when the instance mode forces Red Sky on every community
    instance_red: bool
    community_id: int | None = None
    # Stored mode of the requested community (only with ?community_id=)
    community_mode: str | None = None


@router.get("/status", response_model=StatusOut)
def get_status(
    community_id: int | None = Query(None, description="Resolve the effective mode for this community"),
    db: Session = Depends(get_db),
):
    """Return platform health and current operating mode.

    The `mode` field reflects the dual-state architecture:
    - **blue** – normal "Blue Sky" operation (sharing, booking, gamification)
    - **red**  – "Red Sky" crisis mode (emergency coordination, low-bandwidth UI)
    """
    platform_mode = "red" if is_global_red() else "blue"
    out = StatusOut(
        status="ok",
        version=settings.app_version,
        mode=platform_mode,
        effective_mode=platform_mode,
        instance_red=is_global_red(),
    )
    if community_id is not None:
        community = db.query(Community).filter(Community.id == community_id).first()
        if community is not None and community.is_active:
            out.community_id = community.id
            out.community_mode = community.mode
            out.effective_mode = effective_mode(community)
    return out
