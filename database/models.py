from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)

from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
)

from database.session import Base


# ==========================================================
# USER
# ==========================================================

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    # ------------------------------------------------------
    # Account
    # ------------------------------------------------------

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )

    display_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    avatar_url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    # ------------------------------------------------------
    # Connected Accounts
    # ------------------------------------------------------

    google_user_id: Mapped[str | None] = mapped_column(
        String(255),
        unique=True,
        nullable=True,
    )

    youtube_channel_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    youtube_channel_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    youtube_channel_handle: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    youtube_thumbnail: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    twitch_user_id: Mapped[str | None] = mapped_column(
        String(255),
        unique=True,
        nullable=True,
    )

    twitch_login: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    twitch_display_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    twitch_avatar: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    nightbot_user_id: Mapped[str | None] = mapped_column(
        String(255),
        unique=True,
        nullable=True,
    )

    nightbot_provider: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    nightbot_provider_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    nightbot_bot_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    nightbot_channel_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    nightbot_display_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    nightbot_avatar: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    nightbot_access_token: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    nightbot_refresh_token: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # ------------------------------------------------------
    # Permissions
    # ------------------------------------------------------

    is_admin: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    # ------------------------------------------------------
    # Relationships
    # ------------------------------------------------------

    settings: Mapped["CreatorSettings"] = relationship(
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )

    communities: Mapped[list["Community"]] = relationship(
       back_populates="owner",
       cascade="all, delete-orphan",
    )

    registrations: Mapped[list["Registration"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    queue_entries: Mapped[list["QueueEntry"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    moderators: Mapped[list["Moderator"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    lobby_history: Mapped[list["LobbyHistory"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    activity_logs: Mapped[list["ActivityLog"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

# ==========================================================
# CREATOR SETTINGS
# ==========================================================

class CreatorSettings(Base):
    __tablename__ = "creator_settings"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )

    creator_name: Mapped[str] = mapped_column(
        String(255),
        default="Creator",
    )

    queue_name: Mapped[str] = mapped_column(
        String(255),
        default="Queue",
    )

    player_label: Mapped[str] = mapped_column(
        String(100),
        default="Player",
    )

    party_size: Mapped[int] = mapped_column(
        Integer,
        default=5,
    )

    min_party_size: Mapped[int] = mapped_column(
        Integer,
        default=1,
    )

    max_party_size: Mapped[int] = mapped_column(
        Integer,
        default=10,
    )

    estimated_match_length: Mapped[int] = mapped_column(
        Integer,
        default=4,
    )

    theme: Mapped[str] = mapped_column(
        String(100),
        default="default",
    )

    queue_open: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
    )

    auto_remove_after_invite: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )

    user: Mapped["User"] = relationship(
        back_populates="settings",
    )

# ==========================================================
# COMMUNITIES
# ==========================================================

class Community(Base):
    __tablename__ = "communities"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    owner_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    description: Mapped[str] = mapped_column(
        Text,
        default="",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )

    owner: Mapped["User"] = relationship(
        back_populates="communities",
    )

# ==========================================================
# REGISTRATIONS
# ==========================================================

class Registration(Base):
    __tablename__ = "registrations"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )

    youtube_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    player_name: Mapped[str] = mapped_column(
        String(255),
        default="",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )

    user: Mapped["User"] = relationship(
        back_populates="registrations",
    )


# ==========================================================
# QUEUE
# ==========================================================

class QueueEntry(Base):
    __tablename__ = "queue_entries"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )

    youtube_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    player_name: Mapped[str] = mapped_column(
        String(255),
        default="",
    )

    position: Mapped[int] = mapped_column(
        Integer,
        default=0,
        index=True,
    )

    ready: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        default="waiting",
    )

    joined_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )

    user: Mapped["User"] = relationship(
        back_populates="queue_entries",
    )


# ==========================================================
# MODERATORS
# ==========================================================

class Moderator(Base):
    __tablename__ = "moderators"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )

    moderator_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    # Queue
    can_open_queue: Mapped[bool] = mapped_column(Boolean, default=True)
    can_close_queue: Mapped[bool] = mapped_column(Boolean, default=True)
    can_launch_lobby: Mapped[bool] = mapped_column(Boolean, default=True)
    can_remove_players: Mapped[bool] = mapped_column(Boolean, default=True)

    # Community
    can_manage_registrations: Mapped[bool] = mapped_column(Boolean, default=False)
    can_manage_members: Mapped[bool] = mapped_column(Boolean, default=False)

    # Administration
    can_manage_moderators: Mapped[bool] = mapped_column(Boolean, default=False)
    can_edit_settings: Mapped[bool] = mapped_column(Boolean, default=False)

    added_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )

    user: Mapped["User"] = relationship(
        back_populates="moderators",
    )

# ==========================================================
# LOBBY HISTORY
# ==========================================================

class LobbyHistory(Base):
    __tablename__ = "lobby_history"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )

    completed_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )

    user: Mapped["User"] = relationship(
        back_populates="lobby_history",
    )

    players: Mapped[list["LobbyHistoryPlayer"]] = relationship(
        back_populates="lobby",
        cascade="all, delete-orphan",
    )


# ==========================================================
# LOBBY HISTORY PLAYERS
# ==========================================================

class LobbyHistoryPlayer(Base):
    __tablename__ = "lobby_history_players"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    lobby_id: Mapped[int] = mapped_column(
        ForeignKey("lobby_history.id", ondelete="CASCADE"),
        index=True,
    )

    youtube_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    player_name: Mapped[str] = mapped_column(
        String(255),
        default="",
    )

    joined: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
    )

    lobby: Mapped["LobbyHistory"] = relationship(
        back_populates="players",
    )


# ==========================================================
# ACTIVITY LOG
# ==========================================================

class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )

    action: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    details: Mapped[str] = mapped_column(
        Text,
        default="",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )

    user: Mapped["User"] = relationship(
        back_populates="activity_logs",
    )        

# ==========================================================
# COMMAND MAPPINGS
# ==========================================================

class CommandMapping(Base):
    __tablename__ = "command_mappings"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )

    # Internal identifier
    action: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    # Nightbot command
    command: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    # Creator editable response
    message: Mapped[str] = mapped_column(
        Text,
        default="",
        nullable=False,
    )

    permission: Mapped[str] = mapped_column(
        String(50),
        default="everyone",
    )

    cooldown: Mapped[int] = mapped_column(
        Integer,
        default=30,
        nullable=False,
    )

    enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    builtin: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    description: Mapped[str] = mapped_column(
        String(255),
        default="",
        nullable=False,
    )