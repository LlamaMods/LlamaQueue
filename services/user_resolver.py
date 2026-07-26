from sqlalchemy.orm import Session
from database.models import User

def get_creator_from_nightbot(
    db: Session,
    channel: dict,
    creator_name: str | None,
):
    provider = channel.get("provider")
    provider_id = channel.get("providerId")

    if provider == "youtube":
        user = (
            db.query(User)
            .filter(User.youtube_channel_id == provider_id)
            .first()
        )
        if user:
            return user

    elif provider == "twitch":
        user = (
            db.query(User)
            .filter(User.twitch_user_id == provider_id)
            .first()
        )
        if user:
            return user

    if creator_name:
        return (
            db.query(User)
            .filter(User.youtube_channel_name == creator_name)
            .first()
        )

    return None