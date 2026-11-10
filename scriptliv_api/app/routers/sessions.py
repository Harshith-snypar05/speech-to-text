"""Sessions, transcripts and share links. The relay (via /internal) creates the session record when the owner starts
speaking and mirrors final utterances into `transcript_events`; this router only reads/administers them."""
import secrets

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..config import get_settings
from ..deps import current_user, db_dep, now, verified_user

router = APIRouter(prefix="/v1", tags=["sessions"])


def _err(status, code, message):
    raise HTTPException(status, {"code": code, "message": message})


def _owned(db, uid, session_id):
    s = db.sessions.find_one({"session_id": session_id, "owner_id": uid})
    if not s:
        _err(404, "not_found", "Session not found.")
    return s


def _item(s, events=None):
    out = {"session_id": s["session_id"], "title": s.get("title") or "Untitled session", "started_at": s.get("started_at"),
           "ended_at": s.get("ended_at"), "sharing": bool(s.get("share_token")),
           "share_url": f"{get_settings().app_base_url.rstrip('/')}/s/{s['share_token']}" if s.get("share_token") else None}
    if events is not None:
        out["transcript"] = events
    return out


@router.get("/sessions")
def list_sessions(limit: int = Query(50, ge=1, le=200), user=Depends(current_user), db=Depends(db_dep)):
    rows = db.sessions.find({"owner_id": str(user["_id"])}).sort("started_at", -1).limit(limit)
    return {"sessions": [_item(s) for s in rows]}


@router.get("/sessions/{session_id}")
def get_session(session_id: str, user=Depends(current_user), db=Depends(db_dep)):
    s = _owned(db, str(user["_id"]), session_id)
    ev = [e["text"] for e in db.transcript_events.find({"session_id": session_id}).sort("seq", 1)]
    return _item(s, ev)


class TitleIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)


@router.patch("/sessions/{session_id}")
def rename_session(session_id: str, body: TitleIn, user=Depends(current_user), db=Depends(db_dep)):
    s = _owned(db, str(user["_id"]), session_id)
    db.sessions.update_one({"_id": s["_id"]}, {"$set": {"title": body.title.strip()}})
    return _item(db.sessions.find_one({"_id": s["_id"]}))


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(session_id: str, user=Depends(current_user), db=Depends(db_dep)):
    s = _owned(db, str(user["_id"]), session_id)
    db.transcript_events.delete_many({"session_id": session_id})
    db.sessions.delete_one({"_id": s["_id"]})  # usage records are kept: they are billing history, not transcript content


@router.post("/sessions/{session_id}/share")
def enable_share(session_id: str, user=Depends(verified_user), db=Depends(db_dep)):
    s = _owned(db, str(user["_id"]), session_id)
    token = s.get("share_token") or secrets.token_urlsafe(16)
    db.sessions.update_one({"_id": s["_id"]}, {"$set": {"share_token": token, "shared_at": now()}})
    return _item(db.sessions.find_one({"_id": s["_id"]}))


@router.delete("/sessions/{session_id}/share")
def disable_share(session_id: str, user=Depends(current_user), db=Depends(db_dep)):
    s = _owned(db, str(user["_id"]), session_id)
    db.sessions.update_one({"_id": s["_id"]}, {"$unset": {"share_token": ""}})
    return _item(db.sessions.find_one({"_id": s["_id"]}))


@router.get("/shared/{token}")
def shared(token: str, db=Depends(db_dep)):
    """Public (no sign-in): viewers never consume minutes and need no account."""
    s = db.sessions.find_one({"share_token": token})
    if not s:
        _err(404, "not_found", "This link is no longer active.")
    cfg = get_settings()
    ev = [e["text"] for e in db.transcript_events.find({"session_id": s["session_id"]}).sort("seq", 1)]
    return {"session_id": s["session_id"], "title": s.get("title") or "Untitled session", "live": s.get("ended_at") is None,
            "started_at": s.get("started_at"), "ended_at": s.get("ended_at"), "transcript": ev,
            "app_links": {"deep_link": f"scriptliv://s/{token}", "android_store": cfg.android_store_url or None,
                          "ios_store": cfg.ios_store_url or None}}
