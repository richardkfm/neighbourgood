"""Public instance metadata endpoint for federation discovery."""

import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.activity import Activity
from app.models.community import Community
from app.models.event import Event
from app.models.resource import Resource
from app.models.skill import Skill
from app.models.user import User


router = APIRouter(prefix="/instance", tags=["instance"])


class InstanceInfo(BaseModel):
    name: str
    description: str
    region: str
    url: str
    version: str
    platform_mode: str
    admin_name: str
    admin_contact: str
    community_count: int
    user_count: int
    resource_count: int
    skill_count: int
    event_count: int
    active_user_count: int


@router.get("/info", response_model=InstanceInfo)
def get_instance_info(db: Session = Depends(get_db)):
    """Public metadata about this instance. Used for federation directory crawling."""
    community_count = db.query(Community).filter(Community.is_active == True).count()  # noqa: E712
    user_count = db.query(User).count()
    resource_count = db.query(Resource).filter(Resource.is_available == True).count()  # noqa: E712
    skill_count = db.query(Skill).count()
    event_count = db.query(Event).count()

    # Active users: users with activity in the last 30 days
    thirty_days_ago = datetime.datetime.utcnow() - datetime.timedelta(days=30)
    active_user_count = (
        db.query(Activity.actor_id)
        .filter(Activity.created_at >= thirty_days_ago)
        .distinct()
        .count()
    )

    return InstanceInfo(
        name=settings.instance_name,
        description=settings.instance_description,
        region=settings.instance_region,
        url=settings.instance_url,
        version=settings.app_version,
        platform_mode=settings.platform_mode,
        admin_name=settings.admin_name,
        admin_contact=settings.admin_contact,
        community_count=community_count,
        user_count=user_count,
        resource_count=resource_count,
        skill_count=skill_count,
        event_count=event_count,
        active_user_count=active_user_count,
    )
