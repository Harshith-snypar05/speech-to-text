from fastapi import APIRouter, Depends, Query

from .. import usage
from ..deps import current_user, db_dep

router = APIRouter(prefix="/v1/usage", tags=["usage"])


@router.get("")
def my_usage(user=Depends(current_user), db=Depends(db_dep)):
    return usage.summary(db, str(user["_id"]))


@router.get("/sessions")
def usage_sessions(limit: int = Query(50, ge=1, le=200), user=Depends(current_user), db=Depends(db_dep)):
    """Session-level usage for the current account (sessions they spoke in; viewing is never metered)."""
    rows = db.usage_sessions.find({"user_id": str(user["_id"])}).sort("started_at", -1).limit(limit)
    return {"sessions": [{"session_id": r["session_id"], "started_at": r["started_at"], "ended_at": r["ended_at"],
                          "metered_seconds": r["metered_seconds"], "included_seconds": r["included_seconds"],
                          "addon_seconds": r["addon_seconds"], "unbilled_overshoot_seconds": r.get("unbilled_overshoot_seconds", 0.0)} for r in rows]}


@router.get("/sessions/{session_id}/minutes")
def usage_minutes(session_id: str, user=Depends(current_user), db=Depends(db_dep)):
    """Minute-level usage for one session."""
    s = db.usage_sessions.find_one({"session_id": session_id, "user_id": str(user["_id"])})
    if not s:
        return {"minutes": []}
    rows = db.usage_minutes.find({"session_id": session_id}).sort("minute", 1)
    return {"minutes": [{"minute": r["minute"], "seconds": r["seconds"]} for r in rows]}
