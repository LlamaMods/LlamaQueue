import json
import os
import time


class QueueManager:

    def __init__(self):

        self.file = "database/queue.json"

        os.makedirs("database", exist_ok=True)

        self.players = []
        self.lobby_size = 5
        self.queue_open = True

        if not os.path.exists(self.file):
            self.save()

        self.load()

    def load(self):

        try:

            with open(self.file, "r", encoding="utf-8") as f:
                data = json.load(f)

        except (FileNotFoundError, json.JSONDecodeError):

            data = {
                "players": [],
                "lobby_size": 5,
                "queue_open": True
            }

            with open(self.file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)

        self.players = data.get("players", [])
        self.lobby_size = data.get("lobby_size", 5)
        self.queue_open = data.get("queue_open", True)

    def save(self):

        data = {
            "players": self.players,
            "lobby_size": self.lobby_size,
            "queue_open": self.queue_open
        }

        with open(self.file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

    def is_open(self):

        self.load()

        return self.queue_open

    def open_queue(self):

        self.load()

        self.queue_open = True

        self.save()

    def close_queue(self):

        self.load()

        self.queue_open = False

        self.save()

    def join(self, youtube_name, trainer_name=""):

        self.load()

        if not self.queue_open:
            return False

        for player in self.players:

            if player["youtube"].lower() == youtube_name.lower():
                return False

        self.players.append({

            "youtube": youtube_name,

            "trainer": trainer_name,

            "ready": False,

            "joined": time.time()

        })

        self.save()

        return True

    def remove(self, youtube_name):

        self.load()

        self.players = [

            p for p in self.players

            if p["youtube"] != youtube_name

        ]

        self.save()

    def set_lobby_size(self, size):

        self.load()

        self.lobby_size = size

        self.save()

    def get_lobby_size(self):

        self.load()

        return self.lobby_size

    def current_lobby(self):

        self.load()

        return self.players[:self.lobby_size]

    def waiting_players(self):

        self.load()

        return self.players[self.lobby_size:]

    def complete_lobby(self):

        self.load()

        self.players = self.players[self.lobby_size:]

        self.save()

    def estimated_wait(self, index):

        self.load()

        if index < self.lobby_size:

            return "Now"

        lobby_number = index // self.lobby_size

        minutes = lobby_number * 4

        return f"~{minutes} min"

    def get_players(self):

        self.load()

        return self.players.copy()

    def waiting_time(self, player):

        joined = player.get("joined")

        if joined is None:

            return "--"

        minutes = int((time.time() - joined) / 60)

        if minutes < 1:

            return "<1m"

        if minutes < 60:

            return f"{minutes}m"

        hours = minutes // 60
        mins = minutes % 60

        return f"{hours}h {mins}m"

    # =====================================
    # Moderator Tools
    # =====================================

    def move_up(self, youtube_name):

        self.load()

        for i, player in enumerate(self.players):

            if player["youtube"] == youtube_name and i > 0:

                self.players[i], self.players[i - 1] = (

                    self.players[i - 1],

                    self.players[i]

                )

                break

        self.save()

    def move_down(self, youtube_name):

        self.load()

        for i, player in enumerate(self.players):

            if (

                player["youtube"] == youtube_name

                and i < len(self.players) - 1

            ):

                self.players[i], self.players[i + 1] = (

                    self.players[i + 1],

                    self.players[i]

                )

                break

        self.save()

    def move_to_front(self, youtube_name):

        self.load()

        for i, player in enumerate(self.players):

            if player["youtube"] == youtube_name:

                self.players.insert(

                    0,

                    self.players.pop(i)

                )

                break

        self.save()