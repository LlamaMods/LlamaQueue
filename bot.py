from registration_manager import RegistrationManager
from queue_manager import QueueManager
from youtube_manager import YouTubeManager


registrations = RegistrationManager()
queue = QueueManager()
youtube = YouTubeManager()


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
    # !reg
    # ------------------------------------

    if message.startswith("!reg"):

        parts = message.split(maxsplit=1)

        if len(parts) == 1:

            trainer = registrations.get_trainer(author)

            if trainer:

                youtube.send_message(
                    f"@{author} Your registered trainer is {trainer}"
                )

            else:

                youtube.send_message(
                    f"@{author} You are not registered. Use !reg TrainerName"
                )

            return

        trainer_name = parts[1].strip()

        registrations.register(
            author,
            trainer_name
        )

        youtube.send_message(
            f"@{author} Registration complete! Trainer: {trainer_name}"
        )

        return

    # ------------------------------------
    # !join
    # ------------------------------------

    if message == "!join":

        trainer = registrations.get_trainer(author)

        if trainer is None:

            youtube.send_message(
                f"@{author} Please register first using !reg TrainerName"
            )

            return

        success = queue.join(
            author,
            trainer
        )

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
                f"@{author} Joined! Position #{position} | Lobby {lobby} | Est. {wait}"
            )

        else:

            if not queue.is_open():

                youtube.send_message(
                    f"@{author} Queue is currently CLOSED."
                )

            else:

                youtube.send_message(
                    f"@{author} You're already in the queue."
                )

        return
            # ------------------------------------
    # !leave
    # ------------------------------------

    if message == "!leave":

        queue.remove(author)

        youtube.send_message(
            f"@{author} You have left the queue."
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
                    f"@{author} Position #{index + 1} | Lobby {lobby} | Est. {wait}"
                )

                return

        youtube.send_message(
            f"@{author} You are not currently in the queue."
        )

        return

    # Ignore everything else for now.
    return


print()
print("🦙 Listening for YouTube chat...")
print()

youtube.listen(handle_message)