"""Attempt throttling shared by every API worker.

Hits are stored in MongoDB (`throttle` collection, one document per hit, expired by a TTL index), so the limit holds
across restarts and across several processes behind a load balancer. Callers key by account/email AND by client IP.
"""
import datetime as dt
import os
import time

from fastapi import HTTPException, Request

from .db import get_db


def client_ip(request: Request) -> str:
    """The caller's address. X-Forwarded-For is trusted only when SCRIPTLIV_TRUST_PROXY=1 (set it behind Caddy/a load balancer)."""
    if os.environ.get("SCRIPTLIV_TRUST_PROXY") == "1":
        fwd = request.headers.get("x-forwarded-for", "")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def hit(key: str, limit: int = 10, window: int = 300) -> None:
    """Record one attempt for `key`; raise 429 when more than `limit` happened in the last `window` seconds."""
    db = get_db()
    t = time.time()
    if db.throttle.count_documents({"key": key, "ts": {"$gte": t - window}}) >= limit:
        raise HTTPException(429, {"code": "too_many_attempts", "message": "Too many attempts. Try again in a few minutes."})
    db.throttle.insert_one({"key": key, "ts": t, "expires_at": dt.datetime.fromtimestamp(t + window, dt.timezone.utc)})


def forget(key: str) -> None:
    get_db().throttle.delete_many({"key": key})


def hit_ip(request: Request, scope: str, limit: int = 30, window: int = 300) -> None:
    hit(f"ip:{scope}:{client_ip(request)}", limit=limit, window=window)
