from sqlmodel import SQLModel, Field
from typing import Optional


class Queue(SQLModel, table=True):
    __tablename__ = "queues"

    id: Optional[int] = Field(default=None, primary_key=True)

    owner_id: int = Field(index=True)

    name: str

    slug: str = Field(index=True, unique=True)