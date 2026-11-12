import os
import ipaddress

from fastapi import Request
from sqlalchemy.orm import Session

from database.models import User, Community
from database.session import SessionLocal


def get_current_user(request: Request):
    user_id = request.session.get("user_id")

    host = (request.url.hostname or "").lower().strip("[]")
    local_host = host in {"localhost", "127.0.0.1", "::1"}
    client_host = request.client.host if request.client else ""
    try:
        local_client = ipaddress.ip_address(client_host).is_loopback
    except ValueError:
        local_client = False

    if (
        os.getenv("LLAMAQUEUE_LOCAL_TEST_MODE", "").lower() in {"1", "true", "yes"}
        and local_host and local_client
    ):
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.email == "local-test@llamaqueue.invalid").first()
            if user is None:
                user = User(email="local-test@llamaqueue.invalid", display_name="Local Test User")
                db.add(user)
                db.commit()
                db.refresh(user)
            community = db.query(Community).filter(Community.owner_user_id == user.id).first()
            if community is None:
                community = Community(owner_user_id=user.id, name="LlamaQueue Local Test")
                db.add(community)
                db.commit()
                db.refresh(community)
            request.session["user_id"] = user.id
            request.session["community_id"] = community.id
            return user
        finally:
            db.close()

    if user_id is None:
        return None

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        return user
    finally:
        db.close()
