import base64
import hashlib
import os
from pathlib import Path

from cryptography.fernet import Fernet
from dotenv import load_dotenv


def _get_fernet() -> Fernet:
    key = os.getenv("ARISE_ENCRYPTION_KEY")
    if key and key.strip():
        return Fernet(key.strip())

    secret = os.getenv("ARISE_ENCRYPTION_SECRET")
    if secret and secret.strip():
        digest = hashlib.sha256(secret.strip().encode("utf-8")).digest()
        derived_key = base64.urlsafe_b64encode(digest)
        return Fernet(derived_key)

    # In local/dev, the backend loads env vars from backend/.env. If the
    # process was started before the secret was added, reload it lazily.
    try:
        backend_dir = Path(__file__).resolve().parents[2]
        env_path = backend_dir / ".env"
        if env_path.exists():
            load_dotenv(dotenv_path=str(env_path), override=True)
    except Exception:
        pass

    key = os.getenv("ARISE_ENCRYPTION_KEY")
    if key and key.strip():
        return Fernet(key.strip())

    secret = os.getenv("ARISE_ENCRYPTION_SECRET")
    if secret and secret.strip():
        digest = hashlib.sha256(secret.strip().encode("utf-8")).digest()
        derived_key = base64.urlsafe_b64encode(digest)
        return Fernet(derived_key)

    raise RuntimeError("Missing ARISE_ENCRYPTION_KEY (or ARISE_ENCRYPTION_SECRET) in environment")


def encrypt_text(plaintext: str) -> str:
    f = _get_fernet()
    token = f.encrypt((plaintext or "").encode("utf-8"))
    return token.decode("utf-8")


def decrypt_text(ciphertext: str) -> str:
    f = _get_fernet()
    raw = f.decrypt((ciphertext or "").encode("utf-8"))
    return raw.decode("utf-8")
