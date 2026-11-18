import os
import logging
import requests

logger = logging.getLogger(__name__)


def revoke_oauth_token(platform: str, token: str | None) -> bool:
    """Best-effort revocation at the provider; local deletion must still proceed."""
    if not token:
        return False
    try:
        if platform == "youtube":
            response = requests.post(
                "https://oauth2.googleapis.com/revoke",
                data={"token": token}, timeout=8,
            )
        elif platform == "twitch":
            client_id = os.getenv("TWITCH_CLIENT_ID")
            if not client_id:
                return False
            response = requests.post(
                "https://id.twitch.tv/oauth2/revoke",
                params={"client_id": client_id, "token": token}, timeout=8,
            )
        else:
            return False
        return response.status_code in (200, 204)
    except requests.RequestException:
        logger.warning("OAuth token revocation request failed for %s", platform)
        return False
