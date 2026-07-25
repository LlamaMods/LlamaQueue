from sqlmodel import SQLModel, Field
from typing import Optional


class QueueAccess(SQLModel, table=True):
    __tablename__ = "queue_access"

    id: Optional[int] = Field(default=None, primary_key=True)

    queue_id: int = Field(index=True)

    user_id: int = Field(index=True)

    role: str = "Moderator"

    can_manage_queue: bool = False
    can_launch_lobby: bool = False
    can_remove_players: bool = False
    can_manage_moderators: bool = False
    can_manage_settings: bool = False