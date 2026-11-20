import hmac
import os
import time

from fastapi import Depends, Header, HTTPException
from bson import ObjectId

from .config import get_settings
from .db import get_db
from .security import decode_token


def admin_emails() -> frozenset[str]:
    """Addresses that are always administrators, from SCRIPTLIV_ADMIN_EMAILS (comma separated).

    Fails closed: unset, empty or malformed entries grant nothing. Read on every call so a change needs no code edit.
    """
    out = set()
    for raw in os.environ.get("SCRIPTLIV_ADMIN_EMAILS", "").split(","):
        e = raw.strip().lower()
        if e.count("@") == 1 and not e.startswith("@") and not e.endswith("@") and " " not in e:
            out.add(e)
    return frozenset(out)


def is_admin_email(email: str | None) -> bool:
    return bool(email) and email.strip().lower() in admin_emails()


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

    # Automatically persist admin status if email is recognized as superadmin
    if is_admin_email(user.get("email")) and not user.get("is_admin"):
        try:
            db.users.update_one({"_id": user["_id"]}, {"$set": {"is_admin": True}})
            user["is_admin"] = True
        except Exception:
            user["is_admin"] = True

    return user


def admin_user(user=Depends(current_user)) -> dict:
    if not (user.get("is_admin") or is_admin_email(user.get("email"))):
        raise HTTPException(403, {"code": "forbidden", "message": "Admin privileges required."})
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


def public_user(u: dict, db=None) -> dict:
    """Never include password hash, token versions or other internals."""
    if db is None:
        try:
            db = get_db()
        except Exception:
            db = None
    plan = "free"
    if db is not None:
        try:
            sub = db.subscriptions.find_one({"user_id": str(u["_id"])})
            if sub and sub.get("plan"):
                plan = sub.get("plan")
        except Exception:
            pass
    elif u.get("plan"):
        plan = u.get("plan")

    return {
        "id": str(u["_id"]), "name": u.get("name", ""), "email": u["email"], "email_verified": bool(u.get("email_verified")),
        "pending_email": u.get("pending_email"), "created_at": u.get("created_at"),
        "is_admin": bool(u.get("is_admin") or is_admin_email(u.get("email"))),
        "plan": plan,
    }


def now() -> float:
    return time.time()
