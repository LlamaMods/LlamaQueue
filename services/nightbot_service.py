import requests

from database.models import User


class NightbotService:
    BASE_URL = "https://api.nightbot.tv/1"

    def __init__(self, user: User):
        self.user = user

    @property
    def headers(self):
        return {
            "Authorization": f"Bearer {self.user.nightbot_access_token}"
        }

    def get(self, endpoint: str):
        print("Nightbot Access Token:", self.user.nightbot_access_token)
        response = requests.get(
            f"{self.BASE_URL}/{endpoint.lstrip('/')}",
            headers=self.headers,    
        )
        print(response.status_code)
        print(response.text)


        response.raise_for_status()

        return response.json()

    def list_commands(self):
        response = self.get("commands")

        return response.get("commands", [])

    def post(self, endpoint: str, payload: dict):
        response = requests.post(
            f"{self.BASE_URL}/{endpoint.lstrip('/')}",
            headers=self.headers,
            json=payload,
        )

        response.raise_for_status()

        return response.json()

    def send_message(self, message: str):
        """
        Send a chat message through Nightbot.
        Requires the 'channel_send' OAuth scope.
        """

        return self.post(
            "channel/send",
            {
                "message": message,
            },
        )    

    def put(self, endpoint: str, payload: dict):
        response = requests.put(
            f"{self.BASE_URL}/{endpoint.lstrip('/')}",
            headers=self.headers,
            json=payload,
        )

        response.raise_for_status()

        return response.json()

    def create_command(
        self,
        name: str,
        message: str,
        permission: str,
        cooldown: int,
    ):

        return self.post(
            "commands",
            {
                "name": name,
                "message": message,
                "userLevel": permission,
                "coolDown": cooldown,
            },
        )

    def update_command(
        self,
        command_id: str,
        name: str,
        message: str,
        permission: str,
        cooldown: int,
    ):

        return self.put(
            f"commands/{command_id}",
            {
                "name": name,
                "message": message,
                "userLevel": permission,
                "coolDown": cooldown,
            },
        )