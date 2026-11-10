"""Shared email-token logic (verification, email change, password reset). Independent of which provider delivers the mail.

Tokens: 32 random bytes (urlsafe); only the sha256 is stored. Expiring, single-use, consumed atomically so two parallel
requests with the same link cannot both succeed. Delivery outcomes are logged to `email_deliveries` (never the token,
never the link)."""
import datetime as dt
import logging
import time

from . import email_providers as ep
from .config import get_settings
from .security import hash_opaque, new_opaque_token

logger = logging.getLogger(__name__)

TTL = {"verify": 24 * 3600, "change": 24 * 3600, "reset": 3600}
SUBJECT = {"verify": "Confirm your email — ScriptLiv", "change": "Confirm your new email — ScriptLiv",
           "reset": "Reset your ScriptLiv password"}
PATH = {"verify": "verify-email", "change": "verify-email", "reset": "reset-password"}
BODY = {
    "verify": "Confirm your email address for ScriptLiv:\n{link}\n\nThis link expires in 24 hours and works once. "
              "If you did not create an account, ignore this email.",
    "change": "Confirm this as your new ScriptLiv email address:\n{link}\n\nThis link expires in 24 hours and works once. "
              "If you did not ask for this, ignore this email.",
    "reset": "Reset your ScriptLiv password:\n{link}\n\nThis link expires in 1 hour and works once. "
             "If you did not ask for this, ignore this email; your password has not changed.",
}


def issue_token(db, user_id: str, kind: str, email: str) -> str:
    token, h = new_opaque_token()
    t = time.time()
    # a newer link replaces older unused ones of the same kind, so only the latest email works
    db.email_tokens.update_many({"user_id": user_id, "kind": kind, "used": False}, {"$set": {"used": True}})
    db.email_tokens.insert_one({"token_hash": h, "user_id": user_id, "kind": kind, "email": email, "created_at": t,
                                "expires_at": t + TTL[kind], "expires_dt": dt.datetime.fromtimestamp(t + TTL[kind], dt.timezone.utc),
                                "used": False})
    return token


def consume_token(db, token: str, kinds: tuple[str, ...]):
    """Return the token row and mark it used, or None when unknown / expired / already used. Atomic."""
    if not token or len(token) > 200:
        return None
    return db.email_tokens.find_one_and_update(
        {"token_hash": hash_opaque(token), "used": False, "kind": {"$in": list(kinds)}, "expires_at": {"$gt": time.time()}},
        {"$set": {"used": True, "used_at": time.time()}})


def delivery_possible(to: str) -> bool:
    return ep.available_for(to) or get_settings().dev_return_tokens


def send_token(db, token: str, to: str, kind: str, user_id: str | None = None) -> dict:
    """Mail the link. {'delivery': 'email'|'unavailable'|'failed'|'dev'}. Only with SCRIPTLIV_DEV_RETURN_TOKENS=1 is the token
    handed back (local testing); it is never returned otherwise."""
    link = f"{get_settings().app_base_url.rstrip('/')}/{PATH[kind]}?token={token}"
    sent, attempts, err = ep.deliver(ep.Message(to=to, subject=SUBJECT[kind], text=BODY[kind].format(link=link)))
    status = "sent" if sent else ("no_provider" if err == "no_provider" else "failed")
    try:
        db.email_deliveries.insert_one({"user_id": user_id, "kind": kind, "to_domain": to.rsplit("@", 1)[-1].lower(),
                                        "provider": sent.provider if sent else None, "message_id": sent.message_id if sent else None,
                                        "status": status, "attempts": attempts, "error": err, "ts": time.time()})
    except Exception:  # logging must never break the request
        logger.exception("could not record email delivery")
    if sent:
        return {"delivery": "email"}
    if get_settings().dev_return_tokens:
        return {"delivery": "dev", "dev_token": token}
    return {"delivery": "unavailable" if err == "no_provider" else "failed"}
