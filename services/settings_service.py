from sqlalchemy.orm import Session

from database.models import CreatorSettings, User


class SettingsService:

    DEFAULTS = {
        "creator_name": "Creator Queue",
        "queue_name": "Community Queue",
        "player_label": "Player",
        "party_size": 5,
        "min_party_size": 1,
        "max_party_size": 10,
        "estimated_match_length": 4,
        "theme": "dark",
        "queue_open": True,
    }

    def __init__(self, db: Session, user: User):
        self.db = db
        self.user = user

        settings = (
            self.db.query(CreatorSettings)
            .filter(CreatorSettings.user_id == user.id)
            .first()
        )

        if settings is None:
            settings = CreatorSettings(
                user_id=user.id,
                **self.DEFAULTS,
            )
            self.db.add(settings)
            self.db.commit()

        self._settings = settings

    @property
    def settings(self):
        self.db.refresh(self._settings)
        return self._settings

    def get(self, key):
        return getattr(self.settings, key)

    def set(self, key, value):

        setattr(self.settings, key, value)
        self.db.commit()

    def update(self, **kwargs):

        for key, value in kwargs.items():
            if hasattr(self.settings, key):
                setattr(self.settings, key, value)

        self.db.commit()

    def get_all(self):

        s = self.settings

        return {
            "creator_name": s.creator_name,
            "queue_name": s.queue_name,
            "player_label": s.player_label,
            "party_size": s.party_size,
            "min_party_size": s.min_party_size,
            "max_party_size": s.max_party_size,
            "estimated_match_length": s.estimated_match_length,
            "theme": s.theme,
            "queue_open": s.queue_open,
        }

    def reset(self):

        for key, value in self.DEFAULTS.items():
            setattr(self.settings, key, value)

        self.db.commit()

    def is_open(self):
        return self.settings.queue_open

    def open_queue(self):
        self.settings.queue_open = True
        self.db.commit()

    def close_queue(self):
        self.settings.queue_open = False
        self.db.commit()