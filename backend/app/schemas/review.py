"""Pydantic schemas for transaction reviews/ratings and skill endorsements."""

from pydantic import BaseModel, Field

from app.schemas.user import UserPublic
from app.schemas.common import UTCDateTime


class ReviewCreate(BaseModel):
    booking_id: int
    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(None, max_length=5000)


class SkillReviewCreate(BaseModel):
    skill_id: int
    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(None, max_length=5000)


class ReviewOut(BaseModel):
    id: int
    booking_id: int | None = None
    skill_id: int | None = None
    review_type: str = "booking"
    reviewee_role: str | None = None  # "lender" / "borrower" for booking reviews, None for skill reviews
    reviewer_id: int
    reviewee_id: int
    rating: int
    comment: str | None
    reviewer: UserPublic
    reviewee: UserPublic
    created_at: UTCDateTime

    model_config = {"from_attributes": True}


class ReviewSummary(BaseModel):
    user_id: int
    average_rating: float
    total_reviews: int
    lender_avg: float = 0.0
    lender_count: int = 0
    borrower_avg: float = 0.0
    borrower_count: int = 0
    skill_avg: float = 0.0
    skill_count: int = 0
