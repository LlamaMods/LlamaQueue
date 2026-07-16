import json
import os
from datetime import datetime


class ActivityManager:

    def __init__(self):

        self.file = "activity_log.json"

        if not os.path.exists(self.file):

            with open(self.file, "w") as f:
                json.dump([], f)

    def add(self, message):

        with open(self.file, "r") as f:
            activities = json.load(f)

        activities.insert(0, {
            "time": datetime.now().strftime("%I:%M %p"),
            "message": message
        })

        # Keep only the newest 250 entries
        activities = activities[:250]

        with open(self.file, "w") as f:
            json.dump(
                activities,
                f,
                indent=4
            )

    def get_all(self):

        with open(self.file, "r") as f:
            return json.load(f)

    def clear(self):

        with open(self.file, "w") as f:
            json.dump([], f)