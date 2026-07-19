from fastapi import Request
from sqlalchemy.orm import Session

from database.models import User
from database.session import SessionLocal


def get_current_user(request: Request):
    user_id = request.session.get("user_id")

    if user_id is None:
        return None

    db: Session = SessionLocal()

    try:
        user = (
            db.query(User)
            .filter(User.id == user_id)
            .first()
        )

        return user

    finally:
        db.close()