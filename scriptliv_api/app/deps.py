import hmac
import time

from fastapi import Depends, Header, HTTPException
from bson import ObjectId

from .config import get_settings
from .db import get_db
from .security import decode_token


def db_dep():
    return get_db()


def current_user(authorization: str | None = Header(default=None), db=Depends(db_dep)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, {"code": "unauthenticated", "message": "Sign in required."})
    claims = decode_token(authorization[7:].strip())
    if not claims:
        raise HTTPException(401, {"code": "invalid_token", "message": "Session expired. Sign in again."})
    try:
        user = db.users.find_one({"_id": ObjectId(claims["sub"])})
    except Exception:
        user = None
    if not user or user.get("disabled") or user.get("pwv", 0) != claims.get("pwv"):
        raise HTTPException(401, {"code": "invalid_token", "message": "Session expired. Sign in again."})
    return user


EMAIL_NOT_VERIFIED = {"code": "email_not_verified",
                      "message": "Verify your email address first. Check your inbox for the link, or request a new one in Settings."}


def verified_user(user=Depends(current_user)) -> dict:
    """Signed in AND email verified. Required for starting transcription, creating share links and purchasing."""
    if not user.get("email_verified"):
        raise HTTPException(403, EMAIL_NOT_VERIFIED)
    return user


def relay_auth(x_relay_secret: str | None = Header(default=None)):
    secret = get_settings().relay_secret
    if not secret or not x_relay_secret or not hmac.compare_digest(secret, x_relay_secret):
        raise HTTPException(403, {"code": "forbidden", "message": "Relay credentials required."})


def public_user(u: dict) -> dict:
    """Never include password hash, token versions or other internals."""
    return {
        "id": str(u["_id"]), "name": u.get("name", ""), "email": u["email"], "email_verified": bool(u.get("email_verified")),
        "pending_email": u.get("pending_email"), "created_at": u.get("created_at"),
    }


def now() -> float:
    return time.time()
