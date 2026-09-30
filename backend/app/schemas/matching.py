"""Pydantic schemas for the smart matching service."""

from pydantic import BaseModel, Field
from app.schemas.common import UTCDateTime


class MatchSuggestion(BaseModel):
    match_type: str  # "skill_match" | "resource_suggestion"
    item_id: int
    item_title: str = Field(max_length=200)
    item_type: str  # "skill" | "resource"
    category: str
    score: float  # 0.0–1.0 relevance score
    reason: str = Field(max_length=500)
    ai_enhanced: bool = False

    model_config = {"from_attributes": True}


class UnmetNeed(BaseModel):
    ticket_id: int
    title: str = Field(max_length=200)
    ticket_type: str
    urgency: str
    created_at: UTCDateTime
    offer_count: int  # how many matching offers exist

    model_config = {"from_attributes": True}


class MatchingStatus(BaseModel):
    ai_available: bool
    ai_provider: str | None = None
    ai_model: str | None = None
