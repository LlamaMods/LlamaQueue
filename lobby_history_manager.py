import json
import os
from datetime import datetime


class LobbyHistoryManager:

    def __init__(self):

        self.file = "lobby_history.json"

        if not os.path.exists(self.file):
            self._save([])

    # -------------------------
    # Internal Helpers
    # -------------------------

    def _load(self):

        with open(self.file, "r") as f:
            return json.load(f)

    def _save(self, history):

        with open(self.file, "w") as f:
            json.dump(history, f, indent=4)

    # -------------------------
    # Public Methods
    # -------------------------

    def add_lobby(self, players):

        history = self.get_history()

        history.insert(0, {
            "date": datetime.now().strftime("%B %d, %Y"),
            "time": datetime.now().strftime("%I:%M %p"),
            "player_count": len(players),
            "players": players
        })

        # Keep newest 100 lobbies
        history = history[:100]

        self._save(history)

    def get_history(self):

        return self._load()

    def delete_lobby(self, index):

        history = self.get_history()

        if 0 <= index < len(history):
            history.pop(index)
            self._save(history)

    def clear_history(self):

        self._save([])

    # -------------------------
    # Statistics
    # -------------------------

    def total_lobbies(self):

        return len(self.get_history())

    def total_players(self):

        history = self.get_history()

        return sum(
            lobby.get(
                "player_count",
                len(lobby.get("players", []))
            )
            for lobby in history
        )

    def average_players(self):

        total = self.total_lobbies()

        if total == 0:
            return 0

        return round(
            self.total_players() / total,
            1
        )

    def latest_lobby(self):

        history = self.get_history()

        return history[0] if history else None