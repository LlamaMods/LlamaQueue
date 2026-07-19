from collections import Counter

from sqlalchemy.orm import Session

from database.models import (
    LobbyHistory,
    LobbyHistoryPlayer,
    User,
)


class HistoryService:

    def __init__(self, db: Session, user: User):
        self.db = db
        self.user = user

    # ==========================================================
    # Internal Helpers
    # ==========================================================

    def _query(self):
        return (
            self.db.query(LobbyHistory)
            .filter(LobbyHistory.user_id == self.user.id)
            .order_by(LobbyHistory.completed_at.desc())
        )

    def _find(self, lobby_id: int):
        return (
            self._query()
            .filter(LobbyHistory.id == lobby_id)
            .first()
        )

    # ==========================================================
    # Public Methods
    # ==========================================================

    def add_lobby(self, players):

        lobby = LobbyHistory(
            user_id=self.user.id,
        )

        self.db.add(lobby)
        self.db.flush()

        for player in players:

            self.db.add(
                LobbyHistoryPlayer(
                    lobby_id=lobby.id,
                    youtube_name=player.get("youtube", ""),
                    player_name=player.get("player", ""),
                )
            )

        self.db.commit()

        return lobby

    def get_history(self):

        history = []

        for lobby in self._query().all():

            history.append({
                "id": lobby.id,
                "date": lobby.completed_at.strftime("%B %d, %Y"),
                "time": lobby.completed_at.strftime("%I:%M %p"),
                "player_count": len(lobby.players),
                "players": [
                    {
                        "youtube": player.youtube_name,
                        "player": player.player_name,
                    }
                    for player in lobby.players
                ]
            })

        return history

    def delete_lobby(self, lobby_id: int):

        lobby = self._find(lobby_id)

        if lobby is None:
            return False

        self.db.delete(lobby)
        self.db.commit()

        return True

    def clear_history(self):

        for lobby in self._query().all():
            self.db.delete(lobby)

        self.db.commit()

    # ==========================================================
    # Statistics
    # ==========================================================

    def total_lobbies(self):
        return self._query().count()

    def total_players(self):

        return sum(
            len(lobby.players)
            for lobby in self._query().all()
        )

    def average_players(self):

        lobbies = self._query().all()

        if not lobbies:
            return 0

        return round(
            sum(len(lobby.players) for lobby in lobbies) / len(lobbies),
            1,
        )

    def latest_lobby(self):

        history = self.get_history()

        return history[0] if history else None

    def unique_players(self):

        names = set()

        for lobby in self._query().all():
            for player in lobby.players:

                name = player.youtube_name.strip().lower()

                if name:
                    names.add(name)

        return len(names)

    def top_players(self, limit=10):

        counter = Counter()

        for lobby in self._query().all():
            for player in lobby.players:

                name = player.youtube_name.strip()

                if name:
                    counter[name] += 1

        return [
            {
                "youtube": name,
                "plays": plays,
            }
            for name, plays in counter.most_common(limit)
        ]

    def recent_players(self, limit=10):

        seen = set()
        recent = []

        for lobby in self._query().all():

            for player in lobby.players:

                name = player.youtube_name.strip()

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
            "recent_players": self.recent_players(),
        }