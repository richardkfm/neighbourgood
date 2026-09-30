"""Pydantic schemas for community events."""

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.common import InputDateTime, UTCDateTime
from app.schemas.user import UserPublic

VALID_EVENT_CATEGORIES = [
    "meetup",
    "workshop",
    "repair_cafe",
    "swap",
    "gardening",
    "food",
    "sport",
    "cultural",
    "other",
]

EVENT_CATEGORY_META = {
    "meetup":      {"label": "Meetup",        "icon": "users"},
    "workshop":    {"label": "Workshop",       "icon": "book-open"},
    "repair_cafe": {"label": "Repair Café",    "icon": "wrench"},
    "swap":        {"label": "Swap",           "icon": "refresh-cw"},
    "gardening":   {"label": "Gardening",      "icon": "leaf"},
    "food":        {"label": "Food",           "icon": "utensils"},
    "sport":       {"label": "Sport",          "icon": "activity"},
    "cultural":    {"label": "Cultural",       "icon": "music"},
    "other":       {"label": "Other",          "icon": "star"},
}


class EventCreate(BaseModel):
    model_config = {"str_strip_whitespace": True}

    title: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(None, max_length=5000)
    category: str = Field(..., max_length=50)
    start_at: InputDateTime
    end_at: InputDateTime | None = None
    location: str | None = Field(None, max_length=300)
    max_attendees: int | None = Field(None, ge=1, le=10000)
    community_id: int

    @model_validator(mode="after")
    def end_not_before_start(self):
        if self.end_at is not None and self.end_at < self.start_at:
            raise ValueError("end_at must not be before start_at")
        return self

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        if v not in VALID_EVENT_CATEGORIES:
            raise ValueError(f"Invalid category '{v}'. Must be one of: {VALID_EVENT_CATEGORIES}")
        return v


class EventUpdate(BaseModel):
    model_config = {"str_strip_whitespace": True}

    title: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, max_length=5000)
    category: str | None = Field(None, max_length=50)
    start_at: InputDateTime | None = None
    end_at: InputDateTime | None = None
    location: str | None = Field(None, max_length=300)
    max_attendees: int | None = Field(None, ge=1, le=10000)

    @model_validator(mode="after")
    def end_not_before_start(self):
        if self.start_at is not None and self.end_at is not None and self.end_at < self.start_at:
            raise ValueError("end_at must not be before start_at")
        return self

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_EVENT_CATEGORIES:
            raise ValueError(f"Invalid category '{v}'. Must be one of: {VALID_EVENT_CATEGORIES}")
        return v


class EventAttendeeProfile(BaseModel):
    id: int
    display_name: str
    neighbourhood: str | None

    model_config = {"from_attributes": True}


class EventOut(BaseModel):
    id: int
    title: str
    description: str | None
    category: str
    start_at: UTCDateTime
    end_at: UTCDateTime | None
    location: str | None
    max_attendees: int | None
    organizer_id: int
    community_id: int
    organizer: UserPublic
    attendee_count: int
    is_attending: bool
    attendees: list[EventAttendeeProfile] | None = None
    created_at: UTCDateTime

    model_config = {"from_attributes": True}


class EventList(BaseModel):
    items: list[EventOut]
    total: int


class EventCategoryInfo(BaseModel):
    value: str
    label: str
    icon: str
