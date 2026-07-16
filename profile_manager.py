import json
import os


class ProfileManager:

    def __init__(self):

        self.folder = "profiles"
        self.active_file = "pokemon_go.json"

    def load(self):

        path = os.path.join(
            self.folder,
            self.active_file
        )

        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def game(self):
        return self.load()["game"]

    def player_label(self):
        return self.load()["player_label"]

    def copy_button(self):
        return self.load()["copy_button"]

    def launch_button(self):
        return self.load()["launch_button"]

    def default_lobby_size(self):
        return self.load()["default_lobby_size"]