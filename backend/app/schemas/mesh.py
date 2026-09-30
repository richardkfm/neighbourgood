"""Pydantic schemas for BLE mesh sync endpoint."""

from typing import Annotated

from pydantic import BaseModel, Field

from app.schemas.common import UTCDateTime


class MeshMessageIn(BaseModel):
    """A single NG mesh message received via BLE, submitted for server sync."""

    ng: int = Field(1, ge=1, le=1, description="Protocol version, must be 1")
    type: str = Field(
        ...,
        pattern="^(emergency_ticket|ticket_comment|crisis_vote|crisis_status|direct_message|heartbeat|resource_request|resource_offer|location_checkin|ack)$",
        max_length=30,
    )
    community_id: int
    sender_name: str = Field(..., max_length=100)
    ts: int = Field(..., description="Unix timestamp in milliseconds")
    id: str = Field(..., min_length=1, max_length=100, description="Unique message UUID")
    data: dict = Field(default_factory=dict)
    # Signature fields (see app/services/mesh_signing.py). Messages without a
    # valid signature are attributed to the syncing user and labelled unverified.
    author_user_id: int | None = Field(None, ge=1)
    key_id: str | None = Field(None, max_length=64)
    sig: str | None = Field(None, max_length=200)


class MeshSyncRequest(BaseModel):
    """Batch of mesh messages to sync to the server."""

    messages: list[MeshMessageIn] = Field(..., max_length=100)


class MeshSyncResponse(BaseModel):
    """Result counts from a mesh sync operation."""

    synced: int = 0
    # Of the synced messages, how many carried a valid author signature
    verified: int = 0
    duplicates: int = 0
    errors: int = 0
    # Refused by policy (too old, relayed personal action, crisis mode change);
    # not in failed_ids, so clients drop them instead of retrying
    rejected: int = 0
    # Mesh IDs of the messages counted in ``errors`` so clients can keep only those
    failed_ids: list[str] = Field(default_factory=list)


class MeshMetricsIn(BaseModel):
    """Client-side mesh session metrics for aggregate reporting."""

    messages_sent: int = Field(0, ge=0)
    messages_received: int = Field(0, ge=0)
    messages_relayed: int = Field(0, ge=0)
    reconnect_attempts: int = Field(0, ge=0)
    reconnect_successes: int = Field(0, ge=0)
    peak_peer_count: int = Field(0, ge=0)
    acks_sent: int = Field(0, ge=0)
    acks_received: int = Field(0, ge=0)
    errors: int = Field(0, ge=0)
    session_duration_ms: int = Field(0, ge=0)


class MeshKeyRegister(BaseModel):
    """Register this device's ECDSA P-256 mesh signing key."""

    # base64/base64url SubjectPublicKeyInfo DER, or a public JWK (object or JSON string)
    public_key: Annotated[str, Field(min_length=1, max_length=2000)] | dict
    device_name: str = Field("", max_length=100)
    # base64url P1363 signature over "NG-MESH-KEY-V1\n{user_id}\n{key_id}" made
    # with the private key: proves the device holds it, so nobody can register
    # someone else's public key and have that person's messages attributed to them
    proof: str = Field(..., min_length=1, max_length=200)


class MeshKeyOut(BaseModel):
    key_id: str
    device_name: str
    public_key: str
    created_at: UTCDateTime
    last_used_at: UTCDateTime | None = None
    revoked_at: UTCDateTime | None = None

    model_config = {"from_attributes": True}


class MeshPublicKeyOut(BaseModel):
    user_id: int
    key_id: str
    public_key: str

    model_config = {"from_attributes": True}


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
