import os
import hashlib
from typing import Final, Dict

APP_NAME: Final = os.getenv("FYNTRIX_APP_NAME", "FYNTRIX")
APP_OWNER: Final = os.getenv("FYNTRIX_APP_OWNER", "Tradesurf Ventures Private Limited")
DEFAULT_LICENSEE: Final = os.getenv("FYNTRIX_LICENSEE", "Mahesh")
APP_ID: Final = os.getenv("FYNTRIX_APP_ID", "FYNTRIX-01")

# Stable code signature used as a watermark for this codebase.
# This is not a secret, but a persistent identifier that should
# remain the same across all deployments built from this repository.
CODE_SIGNATURE: Final = os.getenv(
    "FYNTRIX_CODE_SIGNATURE",
    "FYNTRIX-5d4e9f9a-92a1-4e2c-8bb2-3b1d9f4af123",
)

ENV_NAME: Final = (os.getenv("FYNTRIX_ENV_NAME", "local") or "local").strip() or "local"
_ENV_SECRET = (os.getenv("FYNTRIX_ENV_SECRET", "") or "").strip()
_ENV_BASIS = f"{ENV_NAME}::{_ENV_SECRET or 'NOSECRET'}".encode("utf-8")
_ENV_HASH = hashlib.sha256(_ENV_BASIS).hexdigest()
ENV_FINGERPRINT: Final = os.getenv(
    "FYNTRIX_ENV_FINGERPRINT",
    f"{ENV_NAME}:{_ENV_HASH[:12]}",
)


def get_branding_meta() -> Dict[str, str]:
    return {
        "app": APP_NAME,
        "owner": APP_OWNER,
        "licensee": DEFAULT_LICENSEE,
        "app_id": APP_ID,
        "signature": short_signature(),
        "env": ENV_NAME,
        "env_fingerprint": ENV_FINGERPRINT,
    }


def short_signature() -> str:
    """Return a shortened, human-friendly fragment of the code signature."""
    sig = CODE_SIGNATURE or ""
    if len(sig) >= 16:
        return f"{sig[:8]}-{sig[-8:]}"
    return sig
