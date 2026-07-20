from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


# ==========================================================
# DATABASE LOCATION
# ==========================================================

BASE_DIR = Path(__file__).resolve().parent.parent

DATABASE_URL = (
    f"sqlite:///{BASE_DIR / 'database' / 'llamaqueue.db'}"
)


# ==========================================================
# ENGINE
# ==========================================================

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    future=True,
    echo=True,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

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