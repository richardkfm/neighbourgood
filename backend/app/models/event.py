"""SQLAlchemy models for community events."""

import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    start_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    end_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    location: Mapped[str | None] = mapped_column(String(300), nullable=True)
    max_attendees: Mapped[int | None] = mapped_column(Integer, nullable=True)
    organizer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    community_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("communities.id"), nullable=False, index=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    organizer: Mapped["User"] = relationship()  # noqa: F821
    community: Mapped["Community"] = relationship()  # noqa: F821
    attendees: Mapped[list["EventAttendee"]] = relationship(back_populates="event", cascade="all, delete-orphan")  # noqa: F821


class EventAttendee(Base):
    __tablename__ = "event_attendees"
    __table_args__ = (UniqueConstraint("event_id", "user_id", name="uq_event_attendee"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("events.id"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    joined_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    event: Mapped["Event"] = relationship(back_populates="attendees")
    user: Mapped["User"] = relationship()  # noqa: F821
