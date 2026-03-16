"""Pydantic schemas for BLE mesh sync endpoint."""

from pydantic import BaseModel, Field


class MeshMessageIn(BaseModel):
    """A single NG mesh message received via BLE, submitted for server sync."""

    ng: int = Field(1, description="Protocol version, must be 1")
    type: str = Field(
        ...,
        pattern="^(emergency_ticket|ticket_comment|crisis_vote|crisis_status|direct_message|heartbeat|resource_request|resource_offer|location_checkin|ack)$",
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


class MeshMetricsIn(BaseModel):
    """Client-side mesh session metrics for aggregate reporting."""

    messages_sent: int = 0
    messages_received: int = 0
    messages_relayed: int = 0
    reconnect_attempts: int = 0
    reconnect_successes: int = 0
    peak_peer_count: int = 0
    acks_sent: int = 0
    acks_received: int = 0
    errors: int = 0
    session_duration_ms: int = 0


class MeshCheckinOut(BaseModel):
    """A location check-in for API responses."""

    id: int
    community_id: int
    user_id: int
    display_name: str
    lat: float
    lng: float
    status: str
    note: str | None = None
    checked_in_at: str
