"""Pydantic schemas for in-app messaging."""

from pydantic import BaseModel, Field

from app.schemas.user import UserPublic
from app.schemas.common import UTCDateTime


class MessageCreate(BaseModel):
    model_config = {"str_strip_whitespace": True}

    recipient_id: int
    booking_id: int | None = None
    skill_id: int | None = None
    body: str = Field(..., min_length=1, max_length=2000)


class MessageOut(BaseModel):
    id: int
    sender_id: int
    sender: UserPublic
    recipient_id: int
    recipient: UserPublic
    booking_id: int | None
    skill_id: int | None
    body: str
    is_read: bool
    created_at: UTCDateTime

    model_config = {"from_attributes": True}


class MessageList(BaseModel):
    items: list[MessageOut]
    total: int


class MessageableUser(BaseModel):
    """A user the current user can message (shares a community). No email: members only see names."""
    id: int
    display_name: str
    neighbourhood: str | None = None

    model_config = {"from_attributes": True}


class ConversationSummary(BaseModel):
    """Summary of a conversation with another user."""
    partner: UserPublic
    last_message_body: str
    last_message_at: UTCDateTime
    unread_count: int


class UnreadCount(BaseModel):
    count: int


class MarkReadAck(BaseModel):
    ok: bool
    marked: int
