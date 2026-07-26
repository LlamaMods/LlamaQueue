from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, Optional, Any
import announcement_queue

from database.session import SessionLocal
from database.models import User

from services.queue_service import QueueService
from services.registration_service import RegistrationService
from services.moderator_service import ModeratorService
from services.activity_service import ActivityService


# ==========================================================
# RESPONSE OBJECT
# ==========================================================

@dataclass(slots=True)
class BotResponse:

    success: bool

    message: str = ""

    announce: bool = False

    event: str = ""

    username: str = ""

    player: str = ""

    lobby: Optional[int] = None

    slot: Optional[int] = None

    position: Optional[int] = None

    queue_size: Optional[int] = None

    data: dict = field(default_factory=dict)


# ==========================================================
# BOT
# ==========================================================

class LlamaBot:

    def __init__(self, creator_id: int):

        self.creator_id = creator_id

        self.cooldowns: Dict[str, float] = {}

        self.command_map: Dict[str, Callable] = {

            "!join": self.join,

            "!leave": self.leave,

            "!position": self.position,

            "!queue": self.queue,

            "!reg": self.register,

            "!open": self.open_queue,

            "!close": self.close_queue,

            "!fc": self.player_id,

        }

    # ------------------------------------------------------

    def services(self):

        db = SessionLocal()

        user = db.get(User, self.creator_id)
        
        if user is None:

            db.close()

            raise RuntimeError("Creator account not found.")

        return {

            "db": db,

            "queue": QueueService(db, user),

            "registration": RegistrationService(db, user),

            "moderator": ModeratorService(db, user),

            "activity": ActivityService(db, user),

        }

    # ------------------------------------------------------

    def process(self, username: str, message: str) -> BotResponse:

        message = message.strip()

        if not message:

            return BotResponse(False)

        command = message.split()[0].lower()

        handler = self.command_map.get(command)

        if handler is None:

            return BotResponse(False)

        return handler(username, message)
    # ======================================================
    # !reg
    # ======================================================

    def register(self, username: str, message: str) -> BotResponse:

        s = self.services()

        db = s["db"]
        registration = s["registration"]
        activity = s["activity"]

        try:

            parts = message.split(maxsplit=1)

            if len(parts) == 1:

                player = registration.get_player(username)

                if player:

                    return BotResponse(
                        success=True,
                        message=f"{username} is registered as {player}.",
                        username=username,
                        player=player,
                    )

                return BotResponse(
                    success=False,
                    message="You are not registered. Use !reg PlayerName",
                    username=username,
                )

            player_name = parts[1].strip()

            if player_name == "":

                return BotResponse(
                    success=False,
                    message="Please provide a player name.",
                    username=username,
                )

            registration.register(
                username,
                player_name,
            )

            activity.add(
                f"{username} registered as {player_name}."
            )

            return BotResponse(
                success=True,
                message=f"Registration complete! ({player_name})",
                username=username,
                player=player_name,
                event="register",
                announce=False,
            )

        finally:

            db.close()


    # ======================================================
    # !join
    # ======================================================

    def join(self, username: str, message: str) -> BotResponse:

        s = self.services()

        db = s["db"]
        queue = s["queue"]
        registration = s["registration"]
        activity = s["activity"]

        try:

            if not queue.is_open():

                return BotResponse(
                    success=False,
                    message="The queue is currently closed.",
                    username=username,
                )

            player = registration.get_player(username)

            if player is None:

                return BotResponse(
                    success=False,
                    message="Please register first using !reg PlayerName",
                    username=username,
                )

            success = queue.join(
                username,
                player,
            )

            if not success:

                if not queue.is_open():

                    return BotResponse(
                        success=False,
                        message="The queue is currently closed.",
                        username=username,
                    )

                return BotResponse(
                    success=False,
                    message="You're already in the queue.",
                    username=username,
                    player=player,
                )

            players = queue.get_players()

            position = len(players)

            lobby_size = queue.get_lobby_size()

            lobby = ((position - 1) // lobby_size) + 1

            slot = ((position - 1) % lobby_size) + 1

            lobby_players = players[
                ((lobby - 1) * lobby_size):(lobby * lobby_size)
            ]

            if len(lobby_players) == lobby_size:

                names = "\n".join(
                    player["player"] for player in lobby_players
                )

                announcement_queue.add(
                    BotResponse(
                        success=True,
                        announce=True,
                        event="lobby_ready",
                        lobby=lobby,
                        message=(
                            f"🎮 Lobby {lobby} is Ready!\n\n"
                            f"{names}\n\n"
                            "Please send your invites!"
                        ),
                    )
                )

            activity.add(
                f"{username} joined the queue."
            )

            response = BotResponse(

                success=True,

                username=username,

                player=player,

                lobby=lobby,

                slot=slot,

                position=position,

                queue_size=len(players),

                announce=False,

                event="join",

                message=(
                    f"{username} joined "
                    f"Lobby {lobby} "
                    f"({slot}/{lobby_size})."
                ),

            )

            return response

        finally:

            db.close()

    # ======================================================
    # !leave
    # ======================================================

    def leave(self, username: str, message: str) -> BotResponse:

        s = self.services()

        db = s["db"]
        queue = s["queue"]
        activity = s["activity"]

        try:

            if not queue.remove(username):

                return BotResponse(
                    success=False,
                    username=username,
                    message="You are not currently in the queue.",
                )

            activity.add(
                f"{username} left the queue."
            )

            return BotResponse(
                success=True,
                username=username,
                message="You have left the queue.",
                announce=False,
                event="leave",
            )

        finally:

            db.close()


    # ======================================================
    # !position
    # ======================================================

    def position(self, username: str, message: str) -> BotResponse:

        s = self.services()

        db = s["db"]
        queue = s["queue"]

        try:

            waiting = queue.get_players()

            lobby_size = queue.get_lobby_size()

            for index, player in enumerate(waiting):

                if player["youtube"].lower() != username.lower():
                    continue

                lobby = (index // lobby_size) + 1

                slot = (index % lobby_size) + 1

                return BotResponse(

                    success=True,

                    username=username,

                    position=index + 1,

                    lobby=lobby,

                    slot=slot,

                    queue_size=len(waiting),

                    message=(
                        f"Position #{index + 1} | "
                        f"Lobby {lobby} | "
                        f"Slot {slot}/{lobby_size}"
                    )

                )

            return BotResponse(

                success=False,

                username=username,

                message="You are not currently in the queue."

            )

        finally:

            db.close()


    # ======================================================
    # !queue
    # ======================================================

    def queue(self, username: str, message: str) -> BotResponse:

        s = self.services()

        db = s["db"]
        queue = s["queue"]

        try:

            waiting = queue.get_players()

            return BotResponse(

                success=True,

                username=username,

                queue_size=len(waiting),

                message=f"There are currently {len(waiting)} players waiting."

            )

        finally:

            db.close()


    # ======================================================
    # !open
    # ======================================================

    def open_queue(self, username: str, message: str) -> BotResponse:

        s = self.services()

        db = s["db"]
        queue = s["queue"]
        moderator = s["moderator"]
        activity = s["activity"]

        try:

            if not moderator.is_moderator(username):

                return BotResponse(
                    success=False,
                    username=username,
                    message="You don't have permission.",
                )

            queue.open_queue()

            activity.add(
                f"{username} opened the queue."
            )

            return BotResponse(

                success=True,

                username=username,

                announce=True,

                event="queue_open",

                message="🟢 Queue is now OPEN."

            )

        finally:

            db.close()


    # ======================================================
    # !close
    # ======================================================

    def close_queue(self, username: str, message: str) -> BotResponse:

        s = self.services()

        db = s["db"]
        queue = s["queue"]
        moderator = s["moderator"]
        activity = s["activity"]

        try:

            if not moderator.is_moderator(username):

                return BotResponse(
                    success=False,
                    username=username,
                    message="You don't have permission.",
                )

            queue.close_queue()

            activity.add(
                f"{username} closed the queue."
            )

            return BotResponse(

                success=True,

                username=username,

                announce=True,

                event="queue_closed",

                message="🔴 Queue is now CLOSED."

            )

        finally:

            db.close()
    # ======================================================
    # Utility
    # ======================================================

    def queue_size(self) -> int:

        s = self.services()

        db = s["db"]
        queue = s["queue"]

        try:

            return len(queue.get_players())

        finally:

            db.close()


    def is_registered(self, username: str) -> bool:

        s = self.services()

        db = s["db"]
        registration = s["registration"]

        try:

            return registration.get_player(username) is not None

        finally:

            db.close()


    def is_moderator(self, username: str) -> bool:

        s = self.services()

        db = s["db"]
        moderator = s["moderator"]

        try:

            return moderator.is_moderator(username)

        finally:

            db.close()


    def get_lobby(self, position: int):

        s = self.services()

        db = s["db"]
        queue = s["queue"]

        try:

            size = queue.get_lobby_size()

            lobby = ((position - 1) // size) + 1

            slot = ((position - 1) % size) + 1

            return lobby, slot

        finally:

            db.close()


    # ======================================================
    # Announcement Queue
    # ======================================================

    def queue_announcement(self, response: BotResponse):

        announcement_queue.add(response)


    def queue_lobby_announcement(self, players, launching=False):

        if not players:
            return

        status = "Launching" if launching else "Ready"

        names = "\n".join(player.player for player in players)

        announcement_queue.add(
            BotResponse(
                success=True,
                announce=True,
                event="lobby_ready",
                lobby=players[0].lobby,
                message=(
                    f"🎮 Lobby {players[0].lobby} is {status}!\n\n"
                    f"{names}\n\n"
                    "Please send your invites!"
                ),
            )
        )

    def get_pending_announcements(self):

        return announcement_queue.get_all()


    # ======================================================
    # Dispatcher
    # ======================================================

    def has_command(self, command: str) -> bool:

        return command.lower() in self.command_map


    def commands(self):

        return sorted(self.command_map.keys())

    # ======================================================
    # !fc
    # ======================================================

    def player_id(self, username: str, message: str) -> BotResponse:

        s = self.services()

        db = s["db"]

        try:

            settings = s["queue"].user.settings

            label = settings.player_id_label or "Player ID"

            value = settings.player_id_value

            if not value:

                return BotResponse(
                    success=False,
                    message="The creator hasn't configured a Player ID yet.",
                    username=username,
                )

            return BotResponse(
                success=True,
                message=f"{label}: {value}",
                username=username,
            )

        finally:

            db.close()
