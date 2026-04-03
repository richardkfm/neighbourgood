"""Pydantic schemas for skill exchange listings."""

import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.user import OwnerTrust, UserProfile

VALID_SKILL_CATEGORIES = [
    "tutoring",
    "repairs",
    "cooking",
    "languages",
    "music",
    "gardening",
    "tech",
    "crafts",
    "fitness",
    "other",
]

SKILL_CATEGORY_META = {
    "tutoring":  {"label": "Tutoring",    "icon": "book"},
    "repairs":   {"label": "Repairs",     "icon": "wrench"},
    "cooking":   {"label": "Cooking",     "icon": "utensils"},
    "languages": {"label": "Languages",   "icon": "globe"},
    "music":     {"label": "Music",       "icon": "music"},
    "gardening": {"label": "Gardening",   "icon": "leaf"},
    "tech":      {"label": "Tech",        "icon": "laptop"},
    "crafts":    {"label": "Crafts",      "icon": "scissors"},
    "fitness":   {"label": "Fitness",     "icon": "dumbbell"},
    "other":     {"label": "Other",       "icon": "star"},
}

VALID_SKILL_TYPES = ["offer", "request"]


class SkillCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(None, max_length=5000)
    category: str = Field(..., max_length=50)
    skill_type: str = Field(..., max_length=10)
    community_id: int

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        if v not in VALID_SKILL_CATEGORIES:
            raise ValueError(f"Invalid category '{v}'. Must be one of: {VALID_SKILL_CATEGORIES}")
        return v

    @field_validator("skill_type")
    @classmethod
    def validate_skill_type(cls, v: str) -> str:
        if v not in VALID_SKILL_TYPES:
            raise ValueError(f"Invalid skill_type '{v}'. Must be one of: {VALID_SKILL_TYPES}")
        return v


class SkillUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, max_length=5000)
    category: str | None = Field(None, max_length=50)
    skill_type: str | None = Field(None, max_length=10)

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_SKILL_CATEGORIES:
            raise ValueError(f"Invalid category '{v}'. Must be one of: {VALID_SKILL_CATEGORIES}")
        return v

    @field_validator("skill_type")
    @classmethod
    def validate_skill_type(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_SKILL_TYPES:
            raise ValueError(f"Invalid skill_type '{v}'. Must be one of: {VALID_SKILL_TYPES}")
        return v


class SkillOut(BaseModel):
    id: int
    title: str
    description: str | None
    category: str
    skill_type: str
    owner_id: int
    community_id: int | None
    owner: UserProfile
    owner_trust: OwnerTrust | None = None
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = {"from_attributes": True}


class SkillList(BaseModel):
    items: list[SkillOut]
    total: int


class SkillCategoryInfo(BaseModel):
    value: str
    label: str
    icon: str
