class Player:
    def __init__(self, youtube_name, trainer_name):
        self.youtube_name = youtube_name
        self.trainer_name = trainer_name
        self.ready = False

    def __repr__(self):
        return f"{self.youtube_name} ({self.trainer_name})"