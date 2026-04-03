"""Pydantic schemas for user profiles."""

import datetime
import re

from pydantic import BaseModel, EmailStr, Field, field_validator


class UserProfile(BaseModel):
    id: int
    email: str
    display_name: str
    neighbourhood: str | None
    role: str
    telegram_chat_id: str | None = None
    language_code: str = "en"
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


class UserProfileUpdate(BaseModel):
    display_name: str | None = Field(None, min_length=1, max_length=100)
    neighbourhood: str | None = Field(None, max_length=100)
    language_code: str | None = Field(None, max_length=10)


class ChangePassword(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        return v


class ChangeEmail(BaseModel):
    new_email: EmailStr
    password: str = Field(..., max_length=128)


class DashboardOverview(BaseModel):
    resources_count: int
    skills_count: int
    bookings_count: int
    messages_unread_count: int
    reputation_score: int
    reputation_level: str


class ReputationOut(BaseModel):
    user_id: int
    display_name: str
    score: int
    level: str
    breakdown: dict[str, int]


class TrustBadge(BaseModel):
    key: str
    label: str
    description: str


class OwnerTrust(BaseModel):
    reputation_level: str
    average_rating: float
    total_reviews: int
    badges: list[str]


class TrustSummary(BaseModel):
    user_id: int
    display_name: str
    neighbourhood: str | None
    member_since: datetime.datetime
    reputation_level: str
    reputation_score: int
    average_rating: float
    total_reviews: int
    badges: list[TrustBadge]
    lender_rating: float = 0.0
    lender_reviews: int = 0
    borrower_rating: float = 0.0
    borrower_reviews: int = 0
    skill_rating: float = 0.0
    skill_reviews: int = 0
    resources_count: int = 0
    skills_count: int = 0
