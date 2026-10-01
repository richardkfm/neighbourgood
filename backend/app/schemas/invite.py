"""Pydantic schemas for community invite codes."""

from pydantic import BaseModel, Field
from app.schemas.common import UTCDateTime


class InviteCreate(BaseModel):
    community_id: int
    max_uses: int | None = Field(None, ge=1, le=10000)
    expires_in_hours: int | None = Field(None, ge=1, le=24 * 365)  # None = never expires


class InviteOut(BaseModel):
    id: int
    code: str
    community_id: int
    created_by_id: int
    max_uses: int | None
    use_count: int
    is_active: bool
    expires_at: UTCDateTime | None
    created_at: UTCDateTime

    model_config = {"from_attributes": True}


class InviteRedeemResult(BaseModel):
    community_id: int
    community_name: str
    message: str
