"""Speech-relay-only endpoints. Authenticated with a shared secret header; never exposed to browsers/apps."""
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import account_deletion, usage
from ..deps import db_dep, now, relay_auth
from ..security import decode_token

router = APIRouter(prefix="/internal/v1", tags=["internal"], dependencies=[Depends(relay_auth)])


class StartIn(BaseModel):
    token: str
    session_id: str = Field(min_length=6, max_length=64)


@router.post("/sessions/start")
def start(body: StartIn, db=Depends(db_dep)):
    """Called when a speaker connects: validates the customer token, checks quota, registers ownership."""
    claims = decode_token(body.token)
    user = None
    if claims:
        try:
            user = db.users.find_one({"_id": ObjectId(claims["sub"])})
        except Exception:
            user = None
    # a tombstoned account is refused like an unknown one: no session may start, or reconnect, once deletion has begun
    if not user or user.get("disabled") or user.get("deleting") or user.get("pwv", 0) != claims.get("pwv"):
        return {"allowed": False, "reason": "invalid_token", "remaining_seconds": 0}
    uid = str(user["_id"])
    if not user.get("email_verified"):
        return {"allowed": False, "reason": "email_not_verified", "remaining_seconds": 0, "user_id": uid}
    existing = db.sessions.find_one({"session_id": body.session_id})
    if existing and existing.get("owner_id") not in (None, uid):
        return {"allowed": False, "reason": "session_taken", "remaining_seconds": 0}
    auth = usage.authorize(db, uid, session_id=body.session_id)
    if auth["allowed"]:
        db.sessions.update_one({"session_id": body.session_id},
                               {"$set": {"owner_id": uid, "started_at": now(), "ended_at": None},
                                "$setOnInsert": {"title": None, "created_at": now()}}, upsert=True)
    if account_deletion.reconcile_after_write(db, uid):
        # the tombstone landed while this request was running: whatever it wrote (session row, reservation) is swept
        return {"allowed": False, "reason": "invalid_token", "remaining_seconds": 0}
    return {**auth, "user_id": uid}


class UsageIn(BaseModel):
    user_id: str
    session_id: str
    cumulative_seconds: float = Field(ge=0, le=7 * 24 * 3600)
    final: bool = False


@router.post("/usage")
def report(body: UsageIn, db=Depends(db_dep)):
    if account_deletion.account_unavailable(db, body.user_id):
        # Tombstoned or deleted: record nothing and tell the relay to stop the session (a non-final denial ends it; for the
        # final report a 200 stops its retries). The relay learns this within one report interval.
        return {"applied": {"applied_seconds": 0.0, "included": 0.0, "addon": 0.0, "unbilled_overshoot": 0.0},
                "allowed": False, "reason": "account_unavailable", "remaining_seconds": 0}
    try:
        applied = usage.record(db, body.user_id, body.session_id, body.cumulative_seconds, final=body.final)
    except usage.SessionOwnerMismatch:
        raise HTTPException(409, {"code": "session_owner_mismatch", "message": "Session belongs to another account."})
    if body.final:
        auth = usage.authorize(db, body.user_id)  # session is over: plain account answer, no reservation to extend
    else:
        # extends the live session's grant; a late report for a session that already ended reopens nothing
        auth = usage.authorize(db, body.user_id, session_id=body.session_id, midsession=True)
    if body.final:
        db.sessions.update_one({"session_id": body.session_id, "owner_id": body.user_id}, {"$set": {"ended_at": now()}})
    if account_deletion.reconcile_after_write(db, body.user_id):   # tombstone landed mid-request: sweep what it wrote
        return {"applied": {"applied_seconds": 0.0, "included": 0.0, "addon": 0.0, "unbilled_overshoot": 0.0},
                "allowed": False, "reason": "account_unavailable", "remaining_seconds": 0}
    return {"applied": applied, **auth}
