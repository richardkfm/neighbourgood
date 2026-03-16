"""Pydantic schemas for BLE mesh sync endpoint."""

from pydantic import BaseModel, Field


class MeshMessageIn(BaseModel):
    """A single NG mesh message received via BLE, submitted for server sync."""

    ng: int = Field(1, description="Protocol version, must be 1")
    type: str = Field(
        ...,
        pattern="^(emergency_ticket|ticket_comment|crisis_vote|crisis_status|direct_message|heartbeat|resource_request|resource_offer)$",
        max_length=30,
    )
    community_id: int
    sender_name: str = Field(..., max_length=100)
    ts: int = Field(..., description="Unix timestamp in milliseconds")
    id: str = Field(..., max_length=100, description="Unique message UUID")
    data: dict = Field(default_factory=dict)


class MeshSyncRequest(BaseModel):
    """Batch of mesh messages to sync to the server."""

    messages: list[MeshMessageIn] = Field(..., max_length=100)


class MeshSyncResponse(BaseModel):
    """Result counts from a mesh sync operation."""

    synced: int = 0
    duplicates: int = 0
    errors: int = 0
