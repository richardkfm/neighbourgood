"""Pydantic schemas for bookings (borrow requests)."""

import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.user import UserPublic
from app.schemas.common import UTCDateTime

VALID_BOOKING_STATUSES = ["pending", "approved", "rejected", "cancelled", "completed"]


class BookingCreate(BaseModel):
    resource_id: int
    start_date: datetime.date
    end_date: datetime.date
    message: str | None = Field(None, max_length=5000)


class BookingStatusUpdate(BaseModel):
    status: str = Field(..., max_length=20)

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in VALID_BOOKING_STATUSES:
            raise ValueError(f"Invalid status '{v}'. Must be one of: {VALID_BOOKING_STATUSES}")
        return v


class BookingOut(BaseModel):
    id: int
    resource_id: int
    resource_title: str | None = None
    borrower_id: int
    borrower: UserPublic
    start_date: datetime.date
    end_date: datetime.date
    message: str | None
    status: str
    created_at: UTCDateTime
    updated_at: UTCDateTime

    model_config = {"from_attributes": True}


class BookingList(BaseModel):
    items: list[BookingOut]
    total: int
