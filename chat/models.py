from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from database.session import Base


class ChatConnection(Base):
    """Chat-only OAuth credentials; existing login credentials are untouched."""
    __tablename__ = "chat_connections"
    __table_args__ = (UniqueConstraint("user_id", "platform", name="uq_chat_user_platform"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    platform_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    platform_login: Mapped[str | None] = mapped_column(String(255), nullable=True)
    platform_display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ChatOverlayToken(Base):
    __tablename__ = "chat_overlay_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)
    token: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ChatAppearance(Base):
    """Per-user unified chat and OBS appearance preferences."""
    __tablename__ = "chat_appearance"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)
    settings_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ChatIdentity(Base):
    """Verified platform identity and current membership data observed from live chat."""
    __tablename__ = "chat_identities"
    __table_args__ = (
        UniqueConstraint("user_id", "platform", "platform_user_id", name="uq_chat_identity_platform_user"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    platform_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_member: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    subscription_key: Mapped[str | None] = mapped_column(String(40), nullable=True)
    tenure_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tier_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class QueuePrioritySettings(Base):
    """Per-creator priority order. Rank 1 is the highest priority."""
    __tablename__ = "queue_priority_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)
    settings_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class QueueEntryPriority(Base):
    """Priority metadata kept separately so the original queue-entry schema remains intact."""
    __tablename__ = "queue_entry_priorities"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    queue_entry_id: Mapped[int] = mapped_column(ForeignKey("queue_entries.id", ondelete="CASCADE"), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    priority_key: Mapped[str] = mapped_column(String(40), nullable=False)
    priority_label: Mapped[str] = mapped_column(String(80), nullable=False)
    priority_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    platform_user_id: Mapped[str] = mapped_column(String(255), nullable=False)


class AppearancePreset(Base):
    """Three saved website appearance presets per creator."""
    __tablename__ = "appearance_presets"
    __table_args__ = (UniqueConstraint("user_id", "slot", name="uq_appearance_preset_user_slot"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    slot: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    settings_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ChatResumeCursor(Base):
    """Durable YouTube Live Chat stream cursor for interruption recovery."""
    __tablename__ = "chat_resume_cursors"
    __table_args__ = (
        UniqueConstraint("user_id", "live_chat_id", name="uq_chat_resume_user_live_chat"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    live_chat_id: Mapped[str] = mapped_column(String(255), nullable=False)
    page_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
