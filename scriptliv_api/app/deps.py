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


def is_admin_account(u: dict | None) -> bool:
    """True for an account that holds administrator rights: env-listed email or persisted is_admin flag."""
    return bool(u) and bool(u.get("is_admin") or is_admin_email(u.get("email")))


def other_admin_exists(db, exclude_oid) -> bool:
    """True if some account other than `exclude_oid` is a usable administrator: enabled, not tombstoned, and not itself claimed
    for deletion. Called AFTER the caller has published its own claim (see account_deletion): every concurrent deleter has
    published its claim before it looks, so of any two simultaneous deleters at least one sees the other's claim and refuses
    (never both succeed). An expired claim does not count as a claim (its tombstone step would be refused anyway)."""
    emails = list(admin_emails())
    clauses = [{"is_admin": True}] + ([{"email": {"$in": emails}}] if emails else [])
    return db.users.count_documents({"_id": {"$ne": exclude_oid}, "disabled": {"$ne": True}, "deleting": {"$ne": True},
                                     "$or": clauses, "delete_claim_until": {"$not": {"$gt": now()}}}) > 0


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
    # A tombstoned account (deleting) is refused exactly like a disabled or unknown one: a deletion in progress never reverts.
    if not user or user.get("disabled") or user.get("deleting") or user.get("pwv", 0) != claims.get("pwv"):
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
