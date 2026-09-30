"""SQLAlchemy models for shared resources."""

import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Resource(Base):
    __tablename__ = "resources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    condition: Mapped[str | None] = mapped_column(String(20), nullable=True)
    image_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Inventory tracking: how many units exist and how many are currently available
    quantity_total: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    quantity_available: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # Optional alert threshold – surface a low-stock warning when quantity_available drops to or below this
    reorder_threshold: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Created via /federation/migrate/import; earns no reputation points
    imported: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    community_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("communities.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    owner: Mapped["User"] = relationship(back_populates="resources")  # noqa: F821
    community: Mapped["Community | None"] = relationship()  # noqa: F821
