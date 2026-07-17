import json
import os
from collections import Counter
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

        try:
            with open(self.file, "r", encoding="utf-8") as f:
                history = json.load(f)

            if not isinstance(history, list):
                raise ValueError

            return history

        except (FileNotFoundError, json.JSONDecodeError, ValueError):

            history = []
            self._save(history)
            return history

    def _save(self, history):

        with open(self.file, "w", encoding="utf-8") as f:
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

        return round(self.total_players() / total, 1)

    def latest_lobby(self):

        history = self.get_history()

        return history[0] if history else None

    def unique_players(self):

        names = set()

        for lobby in self.get_history():
            for player in lobby.get("players", []):
                names.add(player.get("youtube", "").strip().lower())

        names.discard("")

        return len(names)

    def top_players(self, limit=10):

        counter = Counter()

        for lobby in self.get_history():
            for player in lobby.get("players", []):

                name = player.get("youtube", "").strip()

                if name:
                    counter[name] += 1

        return [
            {
                "youtube": name,
                "plays": plays
            }
            for name, plays in counter.most_common(limit)
        ]

    def recent_players(self, limit=10):

        seen = set()
        recent = []

        for lobby in self.get_history():

            for player in lobby.get("players", []):

                name = player.get("youtube", "").strip()

                if not name:
                    continue

                key = name.lower()

                if key in seen:
                    continue

                seen.add(key)
                recent.append(name)

                if len(recent) >= limit:
                    return recent

        return recent

    def statistics(self):

        return {
            "total_lobbies": self.total_lobbies(),
            "total_players": self.total_players(),
            "unique_players": self.unique_players(),
            "average_players": self.average_players(),
            "latest_lobby": self.latest_lobby(),
            "top_players": self.top_players(),
            "recent_players": self.recent_players()
        }