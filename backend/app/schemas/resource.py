"""Pydantic schemas for resources."""

import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.user import OwnerTrust, UserProfile

VALID_CATEGORIES = [
    "tool", "vehicle", "electronics", "furniture",
    "food", "clothing", "skill", "other",
]

VALID_CONDITIONS = ["new", "good", "fair", "worn"]

CATEGORY_META = {
    "tool":        {"label": "Tools",       "icon": "wrench"},
    "vehicle":     {"label": "Vehicles",    "icon": "car"},
    "electronics": {"label": "Electronics", "icon": "zap"},
    "furniture":   {"label": "Furniture",   "icon": "armchair"},
    "food":        {"label": "Food",        "icon": "utensils"},
    "clothing":    {"label": "Clothing",    "icon": "shirt"},
    "skill":       {"label": "Skills",      "icon": "lightbulb"},
    "other":       {"label": "Other",       "icon": "box"},
}


class ResourceCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(None, max_length=5000)
    category: str = Field(..., max_length=50)
    condition: str | None = Field(None, max_length=20)
    community_id: int | None = None
    quantity_total: int = Field(1, ge=1, description="Total units of this resource")
    reorder_threshold: int | None = Field(None, ge=0, description="Warn when available stock falls to or below this")

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        if v not in VALID_CATEGORIES:
            raise ValueError(f"Invalid category '{v}'. Must be one of: {VALID_CATEGORIES}")
        return v

    @field_validator("condition")
    @classmethod
    def validate_condition(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_CONDITIONS:
            raise ValueError(f"Invalid condition '{v}'. Must be one of: {VALID_CONDITIONS}")
        return v


class ResourceUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, max_length=5000)
    category: str | None = Field(None, max_length=50)
    condition: str | None = Field(None, max_length=20)
    is_available: bool | None = None
    reorder_threshold: int | None = Field(None, ge=0)

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_CATEGORIES:
            raise ValueError(f"Invalid category '{v}'. Must be one of: {VALID_CATEGORIES}")
        return v

    @field_validator("condition")
    @classmethod
    def validate_condition(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_CONDITIONS:
            raise ValueError(f"Invalid condition '{v}'. Must be one of: {VALID_CONDITIONS}")
        return v


class InventoryUpdate(BaseModel):
    """Manual stock-level adjustment by the resource owner."""
    quantity_available: int = Field(..., ge=0, description="Current available units (must not exceed quantity_total)")


class ResourceOut(BaseModel):
    id: int
    title: str
    description: str | None
    category: str
    condition: str | None
    image_url: str | None = None
    is_available: bool
    owner_id: int
    community_id: int | None = None
    owner: UserProfile
    owner_trust: OwnerTrust | None = None
    quantity_total: int
    quantity_available: int
    reorder_threshold: int | None = None
    low_stock: bool
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = {"from_attributes": True}


class ResourceList(BaseModel):
    items: list[ResourceOut]
    total: int


class CategoryInfo(BaseModel):
    value: str
    label: str
    icon: str
