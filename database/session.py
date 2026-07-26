from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


# ==========================================================
# DATABASE LOCATION
# ==========================================================

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Use Render Persistent Disk if available
DB_PATH = os.getenv(
    "DB_PATH",
    str(BASE_DIR / "database" / "llamaqueue.db")
)

DATABASE_URL = f"sqlite:///{DB_PATH}"


# ==========================================================
# ENGINE
# ==========================================================

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    future=True,
    echo=False,
)


# ==========================================================
# SESSION FACTORY
# ==========================================================

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


# ==========================================================
# BASE MODEL
# ==========================================================

class Base(DeclarativeBase):
    pass


# ==========================================================
# DATABASE DEPENDENCY
# ==========================================================

def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()