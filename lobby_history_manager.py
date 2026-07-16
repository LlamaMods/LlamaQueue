import json
import os
from datetime import datetime


class LobbyHistoryManager:

    def __init__(self):

        self.file = "lobby_history.json"

        if not os.path.exists(self.file):
            with open(self.file, "w") as f:
                json.dump([], f)

    def add_lobby(self, players):

        with open(self.file, "r") as f:
            history = json.load(f)

        history.insert(0, {
            "time": datetime.now().strftime("%I:%M %p"),
            "players": players
        })

        # Keep the newest 100 lobbies
        history = history[:100]

        with open(self.file, "w") as f:
            json.dump(history, f, indent=4)

    def get_history(self):

        with open(self.file, "r") as f:
            return json.load(f)