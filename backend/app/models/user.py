"""SQLAlchemy models for users."""

import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    neighbourhood: Mapped[str | None] = mapped_column(String(100), nullable=True)
    role: Mapped[str] = mapped_column(String(20), default="member", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    telegram_chat_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    language_code: Mapped[str] = mapped_column(String(10), default="en", nullable=False)
    mesh_public_key: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    resources: Mapped[list["Resource"]] = relationship(back_populates="owner")  # noqa: F821
