from datetime import datetime

from sqlalchemy import String, Text, Integer, DateTime, ForeignKey, Boolean, func, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


class GoogleToken(Base):
    __tablename__ = "google_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    token_json: Mapped[str] = mapped_column(Text)


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    daily_checkin_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    preferred_checkin_hour: Mapped[int] = mapped_column(Integer, default=9)
    timezone: Mapped[str] = mapped_column(String(50), default="America/Phoenix")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    tasks: Mapped[list["TaskRecord"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    calls: Mapped[list["CallLog"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class TaskRecord(Base):
    """Persisted task from a scheduled goal — tracks progress for check-in calls."""
    __tablename__ = "task_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user_profiles.id"), index=True)
    goal: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(String(500))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    estimate_minutes: Mapped[int] = mapped_column(Integer)
    scheduled_start: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    scheduled_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    calendar_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    resources_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    task_hash: Mapped[str | None] = mapped_column(String(16), unique=True, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    progress_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    user: Mapped["UserProfile"] = relationship(back_populates="tasks")


class CallLog(Base):
    """Record of a daily AI check-in call."""
    __tablename__ = "call_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user_profiles.id"), index=True)
    twilio_call_sid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="initiated")
    ai_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    tasks_discussed: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["UserProfile"] = relationship(back_populates="calls")
