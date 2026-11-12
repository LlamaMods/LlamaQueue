import json

from chat.models import ChatIdentity, QueuePrioritySettings


class PriorityService:
    DEFAULT_RANKS = {
        "twitch_t3": 1,
        "twitch_t2": 2,
        "youtube_member": 3,
        "twitch_t1": 4,
    }
    LABELS = {
        "twitch_t3": "Twitch Tier 3",
        "twitch_t2": "Twitch Tier 2",
        "youtube_member": "YouTube Member",
        "twitch_t1": "Twitch Tier 1 / Prime",
    }
    BADGES = {
        "twitch_t3": "T3",
        "twitch_t2": "T2",
        "youtube_member": "YT MEM",
        "twitch_t1": "T1 / PRIME",
    }

    @classmethod
    def get_settings(cls, db, user_id):
        row = db.query(QueuePrioritySettings).filter_by(user_id=user_id).first()
        settings = {"enabled": True, "ranks": dict(cls.DEFAULT_RANKS)}
        if row:
            try:
                saved = json.loads(row.settings_json or "{}")
                if isinstance(saved, dict):
                    settings["enabled"] = bool(saved.get("enabled", True))
                    ranks = saved.get("ranks", {})
                    if isinstance(ranks, dict):
                        for key in cls.DEFAULT_RANKS:
                            try:
                                value = int(ranks.get(key, cls.DEFAULT_RANKS[key]))
                                if 1 <= value <= 4:
                                    settings["ranks"][key] = value
                            except (TypeError, ValueError):
                                pass
            except (TypeError, ValueError):
                pass
        return settings

    @classmethod
    def save_settings(cls, db, user_id, enabled, ranks):
        clean = {}
        for key in cls.DEFAULT_RANKS:
            value = int(ranks[key])
            if not 1 <= value <= 4:
                raise ValueError("Priority ranks must be between 1 and 4.")
            clean[key] = value
        if len(set(clean.values())) != 4:
            raise ValueError("Each subscription category must have its own priority rank.")
        row = db.query(QueuePrioritySettings).filter_by(user_id=user_id).first()
        if row is None:
            row = QueuePrioritySettings(user_id=user_id, settings_json="{}")
            db.add(row)
        row.settings_json = json.dumps({"enabled": bool(enabled), "ranks": clean})
        db.commit()
        return {"enabled": bool(enabled), "ranks": clean}

    @classmethod
    def resolve(cls, db, user_id, platform, platform_user_id):
        if not platform or not platform_user_id:
            return None
        platform = str(platform).lower()
        if platform not in {"twitch", "youtube"}:
            return None
        settings = cls.get_settings(db, user_id)
        if not settings["enabled"]:
            return None
        identity = (
            db.query(ChatIdentity)
            .filter_by(
                user_id=user_id,
                platform=platform,
                platform_user_id=str(platform_user_id),
            )
            .first()
        )
        if identity is None or not identity.is_member or not identity.subscription_key:
            return None
        key = identity.subscription_key
        if key not in cls.DEFAULT_RANKS:
            return None
        return {
            "key": key,
            "rank": settings["ranks"][key],
            "label": cls.LABELS[key],
            "badge": cls.BADGES[key],
            "platform": platform,
            "platform_user_id": str(platform_user_id),
        }
