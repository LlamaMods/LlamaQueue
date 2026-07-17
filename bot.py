from registration_manager import RegistrationManager
from queue_manager import QueueManager
from youtube_manager import YouTubeManager
from moderator_manager import ModeratorManager
from activity_manager import ActivityManager

registrations = RegistrationManager()
queue = QueueManager()
youtube = YouTubeManager()
moderators = ModeratorManager()
activity = ActivityManager()

print("🦙 Llama Queue Bot")
print("Connecting to YouTube...")
print()

youtube.connect()

if youtube.is_live():

    print("🟢 Active livestream detected.")
    print()

else:

    print("🟡 No active livestream detected.")
    print()
    exit()

def handle_message(author, message):

    message = message.strip()

    print(f"{author}: {message}")

    # ------------------------------------
    # !open
    # ------------------------------------

    if message == "!open":

        if not moderators.is_moderator(author):

            youtube.send_message(
                f"{author} You don't have permission to use this command."
            )

            return

        queue.open_queue()

        activity.add(f"{author} closed the queue.")

        youtube.send_message(
            "🟢 Queue is now OPEN!"
        )

        return

    # ------------------------------------
    # !close
    # ------------------------------------

    if message == "!close":

        if not moderators.is_moderator(author):

            youtube.send_message(
                f"{author} You don't have permission to use this command."
            )

            return

        queue.close_queue()

        youtube.send_message(
            "🔴 Queue is now CLOSED!"
        )

        return

    # ------------------------------------
    # !reg
    # ------------------------------------

    if message.startswith("!reg"):

        parts = message.split(maxsplit=1)

        if len(parts) == 1:

            player = registrations.get_player(author)

            if player:

                youtube.send_message(
                    f"{author} Your registered player is {player}"
                )

            else:

                youtube.send_message(
                    f"{author} You are not registered. Use !reg PlayerName"
                )

            return

        Player_name = parts[1].strip()

        registrations.register(
            author,
            Player_name
        )

        youtube.send_message(
            f"{author} Registration complete! Player: {player_name}"
        )

        return

    # ------------------------------------
    # !join
    # ------------------------------------

    if message == "!join":

        player = registrations.get_player(author)

        if player is None:

            youtube.send_message(
                f"{author} Please register first using !reg PlayerName"
            )

            return

        success = queue.join(
            author,
            player
        )
        if success:
            activity.add(f"{author} joined the queue.")
          

        if success:

            players = queue.get_players()

            position = len(players)

            lobby = (
                (position - 1)
                // queue.get_lobby_size()
            ) + 1

            wait = queue.estimated_wait(
                position - 1
            )

            youtube.send_message(
                f"{author} Joined! Position #{position} | Lobby {lobby} | Est. {wait}"
            )

        else:

            if not queue.is_open():

                youtube.send_message(
                    f"{author} Queue is currently CLOSED."
                )

            else:

                youtube.send_message(
                    f"{author} You're already in the queue."
                )

        return
           
    # ------------------------------------
    # !leave
    # ------------------------------------

    if message == "!leave":

        queue.remove(author)
        
        activity.add(f"{author} left the queue.")

        youtube.send_message(
            f"{author} You have left the queue."
        )

        return

    # ------------------------------------
    # !position
    # ------------------------------------

    if message == "!position":

        players = queue.get_players()

        for index, player in enumerate(players):

            if player["youtube"].lower() == author.lower():

                lobby = (
                    index // queue.get_lobby_size()
                ) + 1

                wait = queue.estimated_wait(index)

                youtube.send_message(
                    f"{author} Position #{index + 1} | Lobby {lobby} | Est. {wait}"
                )

                return

        youtube.send_message(
            f"{author} You are not currently in the queue."
        )

        return

    # Ignore everything else for now.
    return


youtube.listen(handle_message)