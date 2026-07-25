from sqlalchemy.orm import Session
from database.models import User

def get_creator_from_nightbot(db: Session, channel: dict):
    provider = channel.get("provider")
    provider_id = channel.get("providerId")

    if provider == "youtube":
        return (
            db.query(User)
            .filter(User.youtube_channel_id == provider_id)
            .first()
        )

    if provider == "twitch":
        return (
            db.query(User)
            .filter(User.twitch_user_id == provider_id)
            .first()
        )

    return None