"""Pydantic schemas for community events."""

import datetime

from pydantic import BaseModel, Field

from app.schemas.user import UserProfile

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
    title: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(None, max_length=5000)
    category: str
    start_at: datetime.datetime
    end_at: datetime.datetime | None = None
    location: str | None = Field(None, max_length=300)
    max_attendees: int | None = Field(None, ge=1, le=10000)
    community_id: int


class EventUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, max_length=5000)
    category: str | None = None
    start_at: datetime.datetime | None = None
    end_at: datetime.datetime | None = None
    location: str | None = Field(None, max_length=300)
    max_attendees: int | None = Field(None, ge=1, le=10000)


class EventOut(BaseModel):
    id: int
    title: str
    description: str | None
    category: str
    start_at: datetime.datetime
    end_at: datetime.datetime | None
    location: str | None
    max_attendees: int | None
    organizer_id: int
    community_id: int
    organizer: UserProfile
    attendee_count: int
    is_attending: bool
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


class EventList(BaseModel):
    items: list[EventOut]
    total: int


class EventCategoryInfo(BaseModel):
    value: str
    label: str
    icon: str
