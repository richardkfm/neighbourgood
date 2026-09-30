"""SQLAlchemy models for Red Sky (crisis) mode – votes, emergency tickets."""

import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CrisisVote(Base):
    __tablename__ = "crisis_votes"
    __table_args__ = (
        UniqueConstraint("community_id", "user_id", name="uq_crisis_vote_community_user"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    community_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("communities.id"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    vote_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # activate, deactivate
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    community: Mapped["Community"] = relationship()  # noqa: F821
    user: Mapped["User"] = relationship()  # noqa: F821


class EmergencyTicket(Base):
    __tablename__ = "emergency_tickets"
    __table_args__ = (
        UniqueConstraint("author_id", "client_id", name="uq_emergency_ticket_author_client_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    community_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("communities.id"), nullable=False, index=True
    )
    author_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    ticket_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # request, offer, emergency_ping
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="open", nullable=False
    )  # open, in_progress, resolved
    urgency: Mapped[str] = mapped_column(
        String(20), default="medium", nullable=False
    )  # low, medium, high, critical
    assigned_to_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True, index=True
    )
    # Optional deadline for SLA tracking; drives triage score age bonus
    due_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    # Client-generated UUID shared by the REST create and the mesh broadcast of
    # the same ticket, so replays through either path never duplicate it
    client_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    community: Mapped["Community"] = relationship()  # noqa: F821
    author: Mapped["User"] = relationship(foreign_keys=[author_id])  # noqa: F821
    assigned_to: Mapped["User | None"] = relationship(foreign_keys=[assigned_to_id])  # noqa: F821


class TicketComment(Base):
    __tablename__ = "ticket_comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("emergency_tickets.id"), nullable=False, index=True
    )
    author_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    ticket: Mapped["EmergencyTicket"] = relationship()
    author: Mapped["User"] = relationship()  # noqa: F821
