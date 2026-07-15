from registration_manager import RegistrationManager
from queue_manager import QueueManager

registrations = RegistrationManager()
queue = QueueManager()

print("🦙 Llama Queue Bot")
print("Type messages like:")
print("RyanStone: !reg LlamaRyan")
print("RyanStone: !join")
print("RyanStone: !leave")
print("RyanStone: !position")
print()

while True:

    message = input("> ").strip()

    if ":" not in message:
        continue

    youtube_name, command = message.split(":", 1)

    youtube_name = youtube_name.strip()
    command = command.strip()

    # --------------------------
    # !reg
    # --------------------------

    if command.startswith("!reg"):

        parts = command.split(maxsplit=1)

        if len(parts) == 1:

            trainer = registrations.get_trainer(youtube_name)

            if trainer:
                print(f"🦙 Registered Trainer: {trainer}")
            else:
                print("❌ You are not registered.")
                print("Usage: !reg YourTrainerName")

        else:

            trainer_name = parts[1].strip()

            registrations.register(
                youtube_name,
                trainer_name
            )

            print(f"✅ Registered!")
            print(f"YouTube: {youtube_name}")
            print(f"Trainer: {trainer_name}")

        continue

    # --------------------------
    # !join
    # --------------------------

    if command == "!join":

        trainer = registrations.get_trainer(youtube_name)

        if trainer is None:

            print("❌ You're not registered.")
            print("Use: !reg YourTrainerName")
            continue

        success = queue.join(
            youtube_name,
            trainer
        )

        if success:

            players = queue.get_players()

            position = len(players)

            lobby = ((position - 1) // queue.get_lobby_size()) + 1

            wait = queue.estimated_wait(position - 1)

            print()
            print("🦙 Joined Queue!")
            print(f"Position: #{position}")
            print(f"Lobby: {lobby}")
            print(f"Estimated Start: {wait}")
            print()

        else:

            if not queue.is_open():
                print("🔴 Queue is currently CLOSED.")
            else:
                print("⚠️ You're already in the queue.")

        continue

    # --------------------------
    # !leave
    # --------------------------

    if command == "!leave":

        queue.remove(youtube_name)

        print("👋 You left the queue.")

        continue

    # --------------------------
    # !position
    # --------------------------

    if command == "!position":

        players = queue.get_players()

        found = False

        for index, player in enumerate(players):

            if player["youtube"].lower() == youtube_name.lower():

                lobby = (
                    index // queue.get_lobby_size()
                ) + 1

                wait = queue.estimated_wait(index)

                print()
                print(f"🦙 {youtube_name}")
                print(f"Position: #{index + 1}")
                print(f"Lobby: {lobby}")
                print(f"Estimated Start: {wait}")
                print()

                found = True
                break

        if not found:
            print("❌ You're not currently in the queue.")

        continue

    print("❓ Unknown command.")