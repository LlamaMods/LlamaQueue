import os

from authlib.integrations.starlette_client import OAuth

oauth = OAuth()

oauth.register(
    name="twitch",
    client_id=os.getenv("TWITCH_CLIENT_ID"),
    client_secret=os.getenv("TWITCH_CLIENT_SECRET"),
    access_token_url="https://id.twitch.tv/oauth2/token",
    authorize_url="https://id.twitch.tv/oauth2/authorize",
    api_base_url="https://api.twitch.tv/helix/",
    client_kwargs={
        "scope": "user:read:email",
        "token_endpoint_auth_method": "client_secret_post",
    },
)