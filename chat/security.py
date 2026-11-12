import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken


def _fernet() -> Fernet:
    # Derive a dedicated encryption key from the app's existing session secret.
    # This avoids introducing another required environment variable.
    secret = os.getenv("SESSION_SECRET")
    if not secret or len(secret) < 32:
        raise RuntimeError("Set SESSION_SECRET to a random value of at least 32 characters before connecting chat accounts.")
    key = base64.urlsafe_b64encode(hashlib.sha256((secret + ":llamaqueue-chat-tokens").encode("utf-8")).digest())
    return Fernet(key)


def encrypt_token(value: str | None) -> str | None:
    if not value:
        return None
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_token(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise RuntimeError("Unable to decrypt saved chat credentials. Check that SESSION_SECRET has not changed.") from exc
