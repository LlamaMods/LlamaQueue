from datetime import datetime
import time

from sqlalchemy.orm import Session

from database.models import QueueEntry, User
from chat.models import QueueEntryPriority


STATUS_WAITING = "waiting"
STATUS_INVITED = "invited"
STATUS_JOINED = "joined"
STATUS_COMPLETED = "completed"
STATUS_SKIPPED = "skipped"


class QueueService:

    def __init__(self, db: Session, user: User):
        self.db = db
        self.user = user

    # ==========================================================
    # Internal Helpers
    # ==========================================================

    def _query(self):
        return (
            self.db.query(QueueEntry)
            .filter(QueueEntry.user_id == self.user.id)
            .order_by(QueueEntry.position)
        )

    def _find(self, youtube_name: str):
        return (
            self.db.query(QueueEntry)
            .filter(
                QueueEntry.user_id == self.user.id,
                QueueEntry.youtube_name.ilike(youtube_name)
            )
            .first()
        )

    def _last_position(self):
        last = (
            self._query()
            .order_by(QueueEntry.position.desc())
            .first()
        )

        return 0 if last is None else last.position + 1

    def _renumber(self):
        players = self._query().all()

        for index, player in enumerate(players):
            player.position = index

        self.db.commit()

    # ==========================================================
    # Queue State
    # ==========================================================

    def is_open(self):
        if self.user.settings is None:
            return True

        return self.user.settings.queue_open

    def open_queue(self):
        if self.user.settings:
            self.user.settings.queue_open = True
            self.db.commit()

    def close_queue(self):
        if self.user.settings:
            self.user.settings.queue_open = False
            self.db.commit()

    @property
    def queue_open(self):
        return self.is_open()

    @property
    def lobby_size(self):
        if self.user.settings:
            return self.user.settings.party_size

        return 5

    def set_lobby_size(self, size: int):
        if self.user.settings:
            self.user.settings.party_size = size
            self.db.commit()

    def get_lobby_size(self):
        return self.lobby_size

    # ==========================================================
    # Queue Management
    # ==========================================================

    def join(self, youtube_name: str, player_name: str = "", priority: dict | None = None) -> bool:

        if not self.is_open():
            return False

        if self._find(youtube_name):
            return False

        entry = QueueEntry(
            user_id=self.user.id,
            youtube_name=youtube_name,
            player_name=player_name,
            position=self._last_position(),
            ready=False,
            status=STATUS_WAITING,
            joined_at=datetime.utcnow(),
        )
        self.db.add(entry)
        self.db.commit()
        self.db.refresh(entry)

        if priority and priority.get("key") and priority.get("rank"):
            self.db.add(QueueEntryPriority(
                queue_entry_id=entry.id,
                user_id=self.user.id,
                priority_key=priority["key"],
                priority_label=priority.get("label", priority["key"]),
                priority_rank=int(priority["rank"]),
                platform=priority.get("platform", ""),
                platform_user_id=priority.get("platform_user_id", ""),
            ))
            self.db.commit()
            self._insert_by_priority(entry)

        return True

    def _insert_by_priority(self, new_entry):
        entries = self._query().all()
        ids = [entry.id for entry in entries]
        metadata = {
            row.queue_entry_id: row
            for row in self.db.query(QueueEntryPriority).filter(
                QueueEntryPriority.queue_entry_id.in_(ids)
            ).all()
        } if ids else {}
        new_meta = metadata.get(new_entry.id)
        new_rank = new_meta.priority_rank if new_meta else 99
        ordered = [entry for entry in entries if entry.id != new_entry.id]
        insert_at = len(ordered)
        for index, existing in enumerate(ordered):
            existing_meta = metadata.get(existing.id)
            existing_rank = existing_meta.priority_rank if existing_meta else 99
            if existing_rank > new_rank:
                insert_at = index
                break
        ordered.insert(insert_at, new_entry)
        for index, entry in enumerate(ordered):
            entry.position = index
        self.db.commit()

    def remove(self, youtube_name: str) -> bool:

        player = self._find(youtube_name)

        if player is None:
            return False

        self.db.query(QueueEntryPriority).filter_by(queue_entry_id=player.id).delete(synchronize_session=False)
        self.db.delete(player)
        self.db.commit()

        self._renumber()

        return True

    def clear(self):

        self.db.query(QueueEntryPriority).filter_by(user_id=self.user.id).delete(synchronize_session=False)
        self._query().delete(
            synchronize_session=False
        )

        self.db.commit()

    def count(self):

        return self._query().count()

    def find(self, youtube_name: str):

        player = self._find(youtube_name)

        if player is None:
            return None

        return {
            "youtube": player.youtube_name,
            "player": player.player_name,
            "position": player.position,
            "ready": player.ready,
            "status": player.status,
            "joined": (
                player.joined_at.timestamp()
                if player.joined_at
                else None
            ),
        }

    def get_players(self):

        players = []

        entries = self._query().all()
        ids = [entry.id for entry in entries]
        priority_rows = self.db.query(QueueEntryPriority).filter(
            QueueEntryPriority.queue_entry_id.in_(ids)
        ).all() if ids else []
        priority_map = {row.queue_entry_id: row for row in priority_rows}

        for player in entries:
            priority = priority_map.get(player.id)
            players.append({
                "youtube": player.youtube_name,
                "player": player.player_name,
                "position": player.position,
                "ready": player.ready,
                "status": player.status,
                "priority_key": priority.priority_key if priority else None,
                "priority_label": priority.priority_label if priority else None,
                "priority_badge": {
                    "twitch_t3": "T3", "twitch_t2": "T2",
                    "youtube_member": "YT MEM", "twitch_t1": "T1 / PRIME"
                }.get(priority.priority_key) if priority else None,
                "joined": (
                    player.joined_at.timestamp()
                    if player.joined_at
                    else None
                ),
            })

        return players

    @property
    def players(self):
        return self.get_players()        

    # ==========================================================
    # Queue Position
    # ==========================================================

    def move_up(self, youtube_name: str):

        players = self._query().all()

        for index, player in enumerate(players):

            if (
                player.youtube_name.lower() == youtube_name.lower()
                and index > 0
            ):

                players[index - 1].position, player.position = (
                    player.position,
                    players[index - 1].position,
                )

                self.db.commit()
                self._renumber()
                return True

        return False

    def move_down(self, youtube_name: str):

        players = self._query().all()

        for index, player in enumerate(players):

            if (
                player.youtube_name.lower() == youtube_name.lower()
                and index < len(players) - 1
            ):

                players[index + 1].position, player.position = (
                    player.position,
                    players[index + 1].position,
                )

                self.db.commit()
                self._renumber()
                return True

        return False

    def move_to_front(self, youtube_name: str):

        player = self._find(youtube_name)

        if player is None:
            return False

        players = self._query().all()

        for p in players:
            if p.position < player.position:
                p.position += 1

        player.position = 0

        self.db.commit()
        self._renumber()

        return True

    def move_to_position(self, youtube_name: str, new_position: int):

        player = self._find(youtube_name)

        if player is None:
            return False

        players = self._query().all()

        new_position = max(
            0,
            min(new_position, len(players) - 1)
        )

        old_position = player.position

        if old_position == new_position:
            return True

        if new_position < old_position:

            for p in players:
                if new_position <= p.position < old_position:
                    p.position += 1

        else:

            for p in players:
                if old_position < p.position <= new_position:
                    p.position -= 1

        player.position = new_position

        self.db.commit()
        self._renumber()

        return True

    def reorder_by_priority(self, ranks: dict, enabled: bool = True):
        entries = self._query().all()
        if not enabled:
            ids = [entry.id for entry in entries]
            if ids:
                self.db.query(QueueEntryPriority).filter(
                    QueueEntryPriority.queue_entry_id.in_(ids)
                ).delete(synchronize_session=False)
            self.db.commit()
            return

        ids = [entry.id for entry in entries]
        metadata = {
            row.queue_entry_id: row
            for row in self.db.query(QueueEntryPriority).filter(
                QueueEntryPriority.queue_entry_id.in_(ids)
            ).all()
        } if ids else {}
        for row in metadata.values():
            row.priority_rank = int(ranks.get(row.priority_key, 99))
        entries.sort(key=lambda entry: (
            metadata[entry.id].priority_rank if entry.id in metadata else 99,
            entry.joined_at or datetime.min,
            entry.position,
        ))
        for index, entry in enumerate(entries):
            entry.position = index
        self.db.commit()

    # ==========================================================
    # Player State
    # ==========================================================

    def set_ready(self, youtube_name: str, ready: bool = True):

        player = self._find(youtube_name)

        if player is None:
            return False

        player.ready = ready

        self.db.commit()

        return True

    def set_status(self, youtube_name: str, status: str):

        player = self._find(youtube_name)

        if player is None:
            return False

        player.status = status

        self.db.commit()

        return True

    # ==========================================================
    # Lobby
    # ==========================================================

    def current_lobby(self):

        players = self.get_players()

        return players[:self.lobby_size]


    def waiting_players(self):

        players = self.get_players()

        return players[self.lobby_size:]

    def complete_lobby(self):

        players = self._query().limit(self.lobby_size).all()

        launched_players = list(players)

        for player in players:
            self.db.query(QueueEntryPriority).filter_by(queue_entry_id=player.id).delete(synchronize_session=False)
            self.db.delete(player)

        self.db.commit()
        self._renumber()

        return launched_players

    # ==========================================================
    # Utilities
    # ==========================================================

    def estimated_wait(self, index: int):

        if index < self.lobby_size:
            return "Now"

        lobbies_away = index // self.lobby_size

        minutes = (
            lobbies_away *
            (
                self.user.settings.estimated_match_length
                if self.user.settings
                else 4
            )
        )

        return f"~{minutes} min"

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

    def queue_summary(self):

        return {
            "queue_open": self.queue_open,
            "party_size": self.lobby_size,
            "total_players": self.count(),
            "current_lobby": len(self.current_lobby()),
            "waiting": len(self.waiting_players()),
        }        