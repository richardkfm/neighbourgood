"""Pydantic schemas for webhooks and Telegram integration."""

from pydantic import BaseModel, Field, field_validator
from app.schemas.common import UTCDateTime


WEBHOOK_EVENTS = [
    "message.new",
    "booking.created",
    "booking.status_changed",
    "crisis.mode_changed",
    "ticket.created",
    "ticket.assigned",
    "resource.shared",
    "skill.created",
    "member.joined",
]


class WebhookCreate(BaseModel):
    url: str = Field(..., max_length=500)
    secret: str = Field(..., min_length=8, max_length=64)
    event_types: list[str]

    @field_validator("event_types")
    @classmethod
    def validate_events(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("event_types must not be empty")
        invalid = [e for e in v if e not in WEBHOOK_EVENTS]
        if invalid:
            raise ValueError(f"Unknown event types: {invalid}. Valid: {WEBHOOK_EVENTS}")
        return v

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("Webhook URL must start with http:// or https://")
        return v


class WebhookOut(BaseModel):
    id: int
    owner_type: str
    owner_id: int
    url: str
    event_types: list[str]
    is_active: bool
    created_at: UTCDateTime

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_model(cls, obj) -> "WebhookOut":
        import json
        return cls(
            id=obj.id,
            owner_type=obj.owner_type,
            owner_id=obj.owner_id,
            url=obj.url,
            event_types=json.loads(obj.event_types),
            is_active=obj.is_active,
            created_at=obj.created_at,
        )


class TelegramLinkStart(BaseModel):
    bot_url: str


class TelegramGroupLinkStart(BaseModel):
    token: str


class TelegramWebhookRegistered(BaseModel):
    url: str
