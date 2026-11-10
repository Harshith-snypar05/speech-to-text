import base64
import hashlib
import secrets
import time

import bcrypt
import jwt

from .config import get_settings


def _prep(password: str) -> bytes:
    # bcrypt only reads 72 bytes; pre-hash so long passphrases are fully used
    return base64.b64encode(hashlib.sha256(password.encode("utf-8")).digest())


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prep(password), bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_prep(password), hashed.encode())
    except ValueError:
        return False


def _secret() -> str:
    s = get_settings().jwt_secret
    if len(s) < 32:
        raise RuntimeError("SCRIPTLIV_JWT_SECRET must be set (>= 32 chars)")
    return s


def make_token(user_id: str, pwv: int) -> str:
    now = int(time.time())
    return jwt.encode(
        {"sub": user_id, "pwv": pwv, "iat": now, "exp": now + get_settings().token_ttl_seconds, "typ": "access"},
        _secret(), algorithm="HS256",
    )


def decode_token(token: str) -> dict | None:
    try:
        d = jwt.decode(token, _secret(), algorithms=["HS256"])
        return d if d.get("typ") == "access" else None
    except jwt.PyJWTError:
        return None


def new_opaque_token() -> tuple[str, str]:
    """(token to give the user, sha256 hash to store)."""
    t = secrets.token_urlsafe(32)
    return t, hashlib.sha256(t.encode()).hexdigest()


def hash_opaque(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
