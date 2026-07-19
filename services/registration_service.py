from sqlalchemy.orm import Session

from database.models import Registration, User


class RegistrationService:

    def __init__(self, db: Session, user: User):
        self.db = db
        self.user = user

    # ==========================================================
    # Internal Helpers
    # ==========================================================

    def _query(self):
        return (
            self.db.query(Registration)
            .filter(Registration.user_id == self.user.id)
        )

    def _find(self, youtube_name: str):
        return (
            self._query()
            .filter(
                Registration.youtube_name.ilike(youtube_name)
            )
            .first()
        )

    # ==========================================================
    # Registration Management
    # ==========================================================

    def register(self, youtube_name: str, player_name: str = ""):

        registration = self._find(youtube_name)

        if registration:

            registration.player_name = player_name

        else:

            registration = Registration(
                user_id=self.user.id,
                youtube_name=youtube_name,
                player_name=player_name,
            )

            self.db.add(registration)

        self.db.commit()

        return registration

    def unregister(self, youtube_name: str):

        registration = self._find(youtube_name)

        if registration is None:
            return False

        self.db.delete(registration)
        self.db.commit()

        return True

    def clear(self):

        self._query().delete(
            synchronize_session=False
        )

        self.db.commit()

    # ==========================================================
    # Lookups
    # ==========================================================

    def find(self, youtube_name: str):

        registration = self._find(youtube_name)

        if registration is None:
            return None

        return {
            "youtube": registration.youtube_name,
            "player": registration.player_name,
        }

    def get_player(self, youtube_name: str):

        registration = self._find(youtube_name)

        if registration:
            return registration.player_name

        return None

    def is_registered(self, youtube_name: str):

        return self._find(youtube_name) is not None

    def count(self):

        return self._query().count()

    def all(self):

        registrations = (
            self._query()
            .order_by(Registration.youtube_name)
            .all()
        )

        return [
            {
                "youtube": r.youtube_name,
                "player": r.player_name,
            }
            for r in registrations
        ]

        