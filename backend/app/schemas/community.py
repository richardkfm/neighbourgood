"""Pydantic schemas for communities (neighbourhood groups)."""

from pydantic import BaseModel, Field, model_validator

from app.schemas.user import UserPublic
from app.schemas.common import UTCDateTime
from app.services.mode import is_global_red


class _EffectiveModeMixin(BaseModel):
    """Derives ``effective_mode`` from the stored ``mode`` and the instance mode."""

    @model_validator(mode="after")
    def _derive_effective_mode(self):
        self.effective_mode = "red" if is_global_red() or self.mode == "red" else "blue"
        return self


class CommunityCreate(BaseModel):
    model_config = {"str_strip_whitespace": True}

    name: str = Field(..., min_length=1, max_length=150)
    description: str | None = Field(None, max_length=5000)
    postal_code: str = Field(..., min_length=1, max_length=20)
    city: str = Field(..., min_length=1, max_length=150)
    country_code: str = Field("DE", max_length=5)
    primary_language: str | None = Field(None, max_length=10)
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)


class CommunityUpdate(BaseModel):
    model_config = {"str_strip_whitespace": True}

    name: str | None = Field(None, min_length=1, max_length=150)
    description: str | None = Field(None, max_length=5000)


class CommunityMemberOut(BaseModel):
    id: int
    user: UserPublic
    role: str
    joined_at: UTCDateTime

    model_config = {"from_attributes": True}


class CommunityOut(_EffectiveModeMixin):
    id: int
    name: str
    description: str | None
    postal_code: str
    city: str
    country_code: str
    primary_language: str | None = None
    is_active: bool
    # Stored per-community mode (toggles and votes change it)
    mode: str = "blue"
    # What the community behaves as: "red" also while the instance is in Red Sky
    effective_mode: str = "blue"
    latitude: float | None = None
    longitude: float | None = None
    member_count: int = 0
    created_by: UserPublic
    merged_into_id: int | None = None
    created_at: UTCDateTime

    model_config = {"from_attributes": True}


class CommunityMapItem(_EffectiveModeMixin):
    id: int
    name: str
    city: str
    postal_code: str
    country_code: str
    primary_language: str | None = None
    member_count: int = 0
    resource_count: int = 0
    skill_count: int = 0
    mode: str = "blue"
    effective_mode: str = "blue"
    latitude: float | None = None
    longitude: float | None = None


class CommunityList(BaseModel):
    items: list[CommunityOut]
    total: int


class MergeRequest(BaseModel):
    source_id: int
    target_id: int


class MergeSuggestion(BaseModel):
    source: CommunityOut
    target: CommunityOut
    reason: str
