import hashlib
import secrets
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer = HTTPBearer(auto_error=False)
_ITERATIONS = 100_000


def hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    raw_salt = salt if salt is not None else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), raw_salt, _ITERATIONS)
    return raw_salt.hex(), digest.hex()


def verify_password(password: str, salt_hex: str, password_hash: str) -> bool:
    _, digest = hash_password(password, bytes.fromhex(salt_hex))
    return secrets.compare_digest(digest, password_hash)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def get_bearer_token(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> str | None:
    if creds is None or creds.scheme.lower() != "bearer":
        return None
    return creds.credentials


def get_current_user(token: Annotated[str | None, Depends(get_bearer_token)]):
    if token is None:
        raise HTTPException(status_code=401, detail="Please sign in again.")
    from arch_morning_view.store import store

    user = store.user_for_token(token)
    if user is None:
        raise HTTPException(status_code=401, detail="Please sign in again.")
    return user
