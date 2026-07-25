from database.models import ActivityLog


class ActivityService:
    def __init__(self, db, user):
        self.db = db
        self.user = user

    def add(self, message, details=""):
        activity = ActivityLog(
            user_id=self.user.id,
            action=message,
            details=details,
        )

        self.db.add(activity)
        self.db.commit()

    def get_all(self, limit=250):
        return (
            self.db.query(ActivityLog)
            .filter_by(user_id=self.user.id)
            .order_by(ActivityLog.created_at.desc())
            .limit(limit)
            .all()
        )

    def clear(self):
        (
            self.db.query(ActivityLog)
            .filter_by(user_id=self.user.id)
            .delete()
        )

        self.db.commit()