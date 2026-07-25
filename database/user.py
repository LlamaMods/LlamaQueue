from sqlmodel import SQLModel, Field
from typing import Optional


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True)

    google_id: str = Field(index=True, unique=True)

    email: str

    display_name: str

    avatar_url: Optional[str] = None