"""Pydantic schemas for communities (neighbourhood groups)."""

import datetime

from pydantic import BaseModel, Field

from app.schemas.user import UserPublic


class CommunityCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    description: str | None = Field(None, max_length=5000)
    postal_code: str = Field(..., min_length=1, max_length=20)
    city: str = Field(..., min_length=1, max_length=150)
    country_code: str = Field("DE", max_length=5)
    primary_language: str | None = Field(None, max_length=10)
    latitude: float | None = None
    longitude: float | None = None


class CommunityUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=150)
    description: str | None = Field(None, max_length=5000)


class CommunityMemberOut(BaseModel):
    id: int
    user: UserPublic
    role: str
    joined_at: datetime.datetime

    model_config = {"from_attributes": True}


class CommunityOut(BaseModel):
    id: int
    name: str
    description: str | None
    postal_code: str
    city: str
    country_code: str
    primary_language: str | None = None
    is_active: bool
    mode: str = "blue"
    latitude: float | None = None
    longitude: float | None = None
    member_count: int = 0
    created_by: UserPublic
    merged_into_id: int | None = None
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


class CommunityMapItem(BaseModel):
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
