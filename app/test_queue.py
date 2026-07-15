from app.services.queue_service import QueueManager

queue = QueueManager()

queue.join_player("RyanStone", "LlamaRyan")
queue.join_player("PocketPlays42", "PocketJon")
queue.join_player("RockStarYT", "LoisRockstar")

print(queue.show_queue())
print("Pocket is position:", queue.get_position("PocketPlays42"))
print("Next up:", queue.next_player())
print(queue.show_queue())