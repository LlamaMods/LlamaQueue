import json
import os


class SettingsManager:

    def __init__(self):

        os.makedirs("database", exist_ok=True)

        self.file = "database/settings.json"

        self.defaults = {
            "creator_name": "Creator Queue",
            "queue_name": "Community Queue",
            "player_label": "Player",
            "party_size": 5,
            "min_party_size": 1,
            "max_party_size": 10,
            "estimated_match_length": 4,
            "theme": "dark"
        }

        if not os.path.exists(self.file):
            self.settings = self.defaults.copy()
            self.save()

        self.load()

    def load(self):

        with open(self.file, "r") as f:
            self.settings = json.load(f)

        # Add any missing settings automatically
        updated = False

        for key, value in self.defaults.items():
            if key not in self.settings:
                self.settings[key] = value
                updated = True

        if updated:
            self.save()

    def save(self):

        with open(self.file, "w") as f:
            json.dump(self.settings, f, indent=4)

    def get(self, key):

        self.load()
        return self.settings.get(key)

    def set(self, key, value):

        self.load()
        self.settings[key] = value
        self.save()

    def get_all(self):

        self.load()
        return self.settings.copy()

    def reset(self):

        self.settings = self.defaults.copy()
        self.save()