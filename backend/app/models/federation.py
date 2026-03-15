"""SQLAlchemy models for federation – instance directory and cross-instance alerts."""

import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class KnownInstance(Base):
    __tablename__ = "known_instances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    url: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    region: Mapped[str] = mapped_column(String(150), default="", nullable=False)
    version: Mapped[str] = mapped_column(String(50), default="", nullable=False)
    platform_mode: Mapped[str] = mapped_column(String(10), default="blue", nullable=False)
    admin_contact: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    community_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    user_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    resource_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    skill_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    event_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    active_user_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_reachable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_seen_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class RedSkyAlert(Base):
    __tablename__ = "red_sky_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_instance_url: Mapped[str] = mapped_column(String(500), nullable=False)
    source_instance_name: Mapped[str] = mapped_column(String(200), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    severity: Mapped[str] = mapped_column(String(20), default="warning", nullable=False)  # info, warning, critical
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
