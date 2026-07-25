from database.models import Moderator


class ModeratorService:

    def __init__(self, db, user):
        self.db = db
        self.user = user

    def get_all(self):
        return (
            self.db.query(Moderator)
            .filter_by(user_id=self.user.id)
            .order_by(Moderator.moderator_name)
            .all()
        )

    def get(self, youtube_name):
        return (
            self.db.query(Moderator)
            .filter_by(user_id=self.user.id)
            .filter(Moderator.moderator_name.ilike(youtube_name))
            .first()
        )

    def count(self):
        return (
            self.db.query(Moderator)
            .filter_by(user_id=self.user.id)
            .count()
        )

    def is_moderator(self, youtube_name):
        return self.get(youtube_name) is not None

    def has_permission(self, youtube_name, permission):
        moderator = self.get(youtube_name)

        if moderator is None:
            return False

        return getattr(moderator, permission, False)

    def add(
        self,
        youtube_name,
        can_open_queue=True,
        can_close_queue=True,
        can_launch_lobby=True,
        can_remove_players=True,
        can_manage_registrations=False,
        can_manage_members=False,
        can_manage_moderators=False,
        can_edit_settings=False,
    ):
        if self.is_moderator(youtube_name):
            return None

        moderator = Moderator(
            user_id=self.user.id,
            moderator_name=youtube_name,

            can_open_queue=can_open_queue,
            can_close_queue=can_close_queue,
            can_launch_lobby=can_launch_lobby,
            can_remove_players=can_remove_players,

            can_manage_registrations=can_manage_registrations,
            can_manage_members=can_manage_members,

            can_manage_moderators=can_manage_moderators,
            can_edit_settings=can_edit_settings,
        )

        self.db.add(moderator)
        self.db.commit()
        self.db.refresh(moderator)

        return moderator

    def update_permissions(self, youtube_name, **permissions):
        moderator = self.get(youtube_name)

        if moderator is None:
            return None

        for permission, value in permissions.items():
            if hasattr(moderator, permission):
                setattr(moderator, permission, bool(value))

        self.db.commit()
        self.db.refresh(moderator)

        return moderator

    def rename(self, old_name, new_name):
        moderator = self.get(old_name)

        if moderator is None:
            return None

        moderator.moderator_name = new_name

        self.db.commit()
        self.db.refresh(moderator)

        return moderator

    def remove(self, youtube_name):
        moderator = self.get(youtube_name)

        if moderator is None:
            return False

        self.db.delete(moderator)
        self.db.commit()

        return True