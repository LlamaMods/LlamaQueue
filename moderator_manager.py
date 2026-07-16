import json
import os


class ModeratorManager:

    def __init__(self):

        self.file = "moderators.json"

        if not os.path.exists(self.file):

            with open(self.file, "w") as f:
                json.dump([], f)

    def get_all(self):

        with open(self.file, "r") as f:
            return json.load(f)

    def is_moderator(self, youtube_name):

        moderators = self.get_all()

        return youtube_name.lower() in [
            mod.lower()
            for mod in moderators
        ]

    def add(self, youtube_name):

        moderators = self.get_all()

        if youtube_name not in moderators:

            moderators.append(youtube_name)

            with open(self.file, "w") as f:
                json.dump(
                    moderators,
                    f,
                    indent=4
                )

    def remove(self, youtube_name):

        moderators = self.get_all()

        moderators = [
            mod
            for mod in moderators
            if mod.lower() != youtube_name.lower()
        ]

        with open(self.file, "w") as f:
            json.dump(
                moderators,
                f,
                indent=4
            )