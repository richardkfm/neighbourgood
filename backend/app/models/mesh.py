"""SQLAlchemy models for BLE mesh: sync deduplication and message-signing keys."""

import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MeshSyncedMessage(Base):
    """Tracks mesh message IDs that have been synced to prevent duplicates.

    A message ID is unique per author: a verified (signed) message is keyed by
    its real author, so nobody can "squat" another author's message ID by
    syncing junk under it first. Unsigned messages are attributed to (and keyed
    by) the user who synced them.
    """

    __tablename__ = "mesh_synced_messages"
    __table_args__ = (
        UniqueConstraint("mesh_message_id", "author_id", name="uq_mesh_synced_message_author"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mesh_message_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    message_type: Mapped[str] = mapped_column(String(30), nullable=False)
    community_id: Mapped[int] = mapped_column(Integer, ForeignKey("communities.id"), nullable=False, index=True)
    synced_by_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    # Who the content is attributed to: the signing author, or the syncing user
    author_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    # True when the author's signature was verified
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    server_object_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    synced_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class MeshDeviceKey(Base):
    """A device's ECDSA P-256 public key for signing mesh messages (several per user)."""

    __tablename__ = "mesh_device_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    # base64url(SHA-256(SPKI DER)), also computed by the client and sent in messages
    key_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    # base64url SPKI DER (91 bytes for P-256)
    public_key: Mapped[str] = mapped_column(String(200), nullable=False)
    device_name: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    last_used_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    # Revoked keys stay on record so their signatures keep failing and the
    # key cannot be registered again
    revoked_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
