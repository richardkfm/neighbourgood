"""Pydantic schemas for community activity feed."""

from pydantic import BaseModel

from app.schemas.user import UserPublic
from app.schemas.common import UTCDateTime


class ActivityOut(BaseModel):
    id: int
    event_type: str
    summary: str
    actor_id: int
    community_id: int | None
    actor: UserPublic
    created_at: UTCDateTime

    model_config = {"from_attributes": True}


class ActivityList(BaseModel):
    items: list[ActivityOut]
    total: int
