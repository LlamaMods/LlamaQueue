import os

from authlib.integrations.starlette_client import OAuth

oauth = OAuth()

oauth.register(
    name="nightbot",
    client_id=os.getenv("NIGHTBOT_CLIENT_ID"),
    client_secret=os.getenv("NIGHTBOT_CLIENT_SECRET"),
    authorize_url="https://api.nightbot.tv/oauth2/authorize",
    access_token_url="https://api.nightbot.tv/oauth2/token",
    client_kwargs={
        "scope": "channel commands commands_default",
    },
)