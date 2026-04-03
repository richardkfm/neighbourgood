"""SQLAlchemy model for transaction reviews/ratings and skill endorsements."""

import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (
        UniqueConstraint("booking_id", "reviewer_id", name="uq_review_booking_reviewer"),
        UniqueConstraint("skill_id", "reviewer_id", name="uq_review_skill_reviewer"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    booking_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("bookings.id"), nullable=True, index=True
    )
    skill_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("skills.id"), nullable=True, index=True
    )
    review_type: Mapped[str] = mapped_column(
        String(10), nullable=False, default="booking", index=True
    )  # "booking" or "skill"
    reviewer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    reviewee_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    rating: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-5
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    booking: Mapped["Booking | None"] = relationship()  # noqa: F821
    skill: Mapped["Skill | None"] = relationship()  # noqa: F821
    reviewer: Mapped["User"] = relationship(foreign_keys=[reviewer_id])  # noqa: F821
    reviewee: Mapped["User"] = relationship(foreign_keys=[reviewee_id])  # noqa: F821
