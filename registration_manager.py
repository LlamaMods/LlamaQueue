import json
import os


class RegistrationManager:
    def __init__(self):

        self.file = "database/registrations.json"

        os.makedirs("database", exist_ok=True)

        if not os.path.exists(self.file):
            with open(self.file, "w") as f:
                json.dump({}, f, indent=4)

    def load(self):

        with open(self.file, "r") as f:
            return json.load(f)

    def save(self, data):

        with open(self.file, "w") as f:
            json.dump(data, f, indent=4)

    def register(self, youtube_name, player_name):

        data = self.load()

        data[youtube_name] = {
            "player": player_name
        }

        self.save(data)

    def get_player(self, youtube_name):

        data = self.load()

        if youtube_name in data:
            return data[youtube_name]["player"]

        return None

    def is_registered(self, youtube_name):

        data = self.load()

        return youtube_name in data