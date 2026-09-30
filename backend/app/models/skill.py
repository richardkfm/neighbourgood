"""SQLAlchemy models for skill exchange listings."""

import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    skill_type: Mapped[str] = mapped_column(String(10), nullable=False, index=True)  # "offer" or "request"
    # Created via /federation/migrate/import; earns no reputation points
    imported: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    owner_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    community_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("communities.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    owner: Mapped["User"] = relationship()  # noqa: F821
    community: Mapped["Community | None"] = relationship()  # noqa: F821
