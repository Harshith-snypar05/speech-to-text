"""Admin dashboard endpoints: system-wide analytics, user access control, plan assignment, and session management."""
import time
from typing import Optional
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..deps import ADMIN_EMAILS, admin_user, db_dep, now, public_user

router = APIRouter(prefix="/v1/admin", tags=["admin"], dependencies=[Depends(admin_user)])


def _err(status: int, code: str, message: str):
    raise HTTPException(status, {"code": code, "message": message})


@router.get("/analytics")
def get_analytics(db=Depends(db_dep)):
    """System-wide stats: user counts, transcription hours, subscription breakdown, and revenue."""
    total_users = db.users.count_documents({})
    verified_users = db.users.count_documents({"email_verified": True})
    disabled_users = db.users.count_documents({"disabled": True})
    admin_users = db.users.count_documents({"$or": [{"is_admin": True}, {"email": {"$in": list(ADMIN_EMAILS)}}]})

    total_sessions = db.sessions.count_documents({})
    live_sessions = db.sessions.count_documents({"ended_at": None})

    # Total transcription seconds across all sessions
    usage_pipeline = [
        {"$group": {"_id": None, "total_seconds": {"$sum": "$metered_seconds"}}}
    ]
    usage_agg = list(db.usage_sessions.aggregate(usage_pipeline))
    total_seconds = float(usage_agg[0]["total_seconds"]) if usage_agg else 0.0
    total_hours = round(total_seconds / 3600.0, 2)

    # Subscriptions breakdown
    pro_subs = db.subscriptions.count_documents({"plan": "pro", "status": "active"})
    free_subs = max(0, total_users - pro_subs)

    # Revenue
    rev_pipeline = [
        {"$match": {"status": {"$in": ["succeeded", "paid"]}}},
        {"$group": {"_id": None, "total_amount": {"$sum": {"$ifNull": ["$amount_cents", "$amount"]}}}},
    ]
    rev_agg = list(db.payments.aggregate(rev_pipeline))
    total_revenue_inr = round(float(rev_agg[0]["total_amount"]) / 100.0, 2) if rev_agg else 0.0

    return {
        "users": {
            "total": total_users,
            "verified": verified_users,
            "disabled": disabled_users,
            "admins": admin_users,
        },
        "sessions": {
            "total": total_sessions,
            "live": live_sessions,
            "total_seconds": total_seconds,
            "total_hours": total_hours,
        },
        "subscriptions": {
            "pro": pro_subs,
            "free": free_subs,
        },
        "revenue_usd": total_revenue_inr,
        "revenue_inr": total_revenue_inr,
        "currency": "inr",
        "currency_symbol": "₹",
    }


@router.get("/users")
def list_users(
    q: Optional[str] = Query(None, description="Search by name or email"),
    limit: int = Query(50, ge=1, le=500),
    skip: int = Query(0, ge=0),
    db=Depends(db_dep),
):
    """List users with plan status, session counts, and access state."""
    filter_dict = {}
    if q and q.strip():
        term = q.strip()
        filter_dict["$or"] = [
            {"email": {"$regex": term, "$options": "i"}},
            {"name": {"$regex": term, "$options": "i"}},
        ]

    users_cursor = db.users.find(filter_dict).sort("created_at", -1).skip(skip).limit(limit)
    users_list = []

    for u in users_cursor:
        uid = str(u["_id"])
        sub = db.subscriptions.find_one({"user_id": uid})
        plan = sub.get("plan", "free") if sub else "free"

        session_count = db.sessions.count_documents({"owner_id": uid})
        
        # Calculate total usage
        user_usage = list(db.usage_sessions.aggregate([
            {"$match": {"user_id": uid}},
            {"$group": {"_id": None, "total": {"$sum": "$metered_seconds"}}}
        ]))
        seconds = float(user_usage[0]["total"]) if user_usage else 0.0

        users_list.append({
            "id": uid,
            "name": u.get("name", ""),
            "email": u.get("email", ""),
            "email_verified": bool(u.get("email_verified")),
            "is_admin": bool(u.get("is_admin") or u.get("email") in ADMIN_EMAILS),
            "disabled": bool(u.get("disabled")),
            "created_at": u.get("created_at", 0),
            "plan": plan,
            "total_sessions": session_count,
            "total_minutes": round(seconds / 60.0, 1),
        })

    return {"users": users_list, "count": len(users_list)}


class UserAccessPatch(BaseModel):
    is_admin: Optional[bool] = None
    disabled: Optional[bool] = None
    email_verified: Optional[bool] = None
    plan: Optional[str] = None  # "free" | "pro"
    grant_addon_minutes: Optional[int] = Field(None, ge=1, le=100000)


@router.patch("/users/{user_id}")
def update_user_access(user_id: str, body: UserAccessPatch, db=Depends(db_dep)):
    """Admin modify user privileges, plan, email verification, account state, or grant bonus minutes."""
    try:
        oid = ObjectId(user_id)
    except Exception:
        _err(400, "invalid_id", "Invalid user id.")

    user = db.users.find_one({"_id": oid})
    if not user:
        _err(404, "not_found", "User not found.")

    upd = {}
    if body.is_admin is not None:
        upd["is_admin"] = body.is_admin
    if body.disabled is not None:
        upd["disabled"] = body.disabled
    if body.email_verified is not None:
        upd["email_verified"] = body.email_verified

    if upd:
        db.users.update_one({"_id": oid}, {"$set": upd})

    # Plan change
    if body.plan in ("free", "basic", "pro"):
        t = now()
        target_plan = "pro" if body.plan == "pro" else "basic"
        db.subscriptions.update_one(
            {"user_id": user_id},
            {"$set": {
                "plan": target_plan,
                "status": "active",
                "period_end": t + 30 * 86400,
                "cancel_at_period_end": False,
            }},
            upsert=True
        )

    # Add-on / bonus minutes grant
    if body.grant_addon_minutes and body.grant_addon_minutes > 0:
        sec = body.grant_addon_minutes * 60.0
        t = now()
        db.addons.insert_one({
            "user_id": user_id,
            "seconds_total": sec,
            "seconds_used": 0.0,
            "expires_at": t + 365 * 86400,
            "purchased_at": t,
            "note": "Admin granted",
        })

    refreshed = db.users.find_one({"_id": oid})
    sub = db.subscriptions.find_one({"user_id": user_id})
    return {
        "id": user_id,
        "name": refreshed.get("name", ""),
        "email": refreshed.get("email", ""),
        "email_verified": bool(refreshed.get("email_verified")),
        "is_admin": bool(refreshed.get("is_admin") or refreshed.get("email") in ADMIN_EMAILS),
        "disabled": bool(refreshed.get("disabled")),
        "created_at": refreshed.get("created_at", 0),
        "plan": sub.get("plan", "free") if sub else "free",
    }


@router.get("/sessions")
def list_all_sessions(limit: int = Query(50, ge=1, le=500), skip: int = Query(0, ge=0), db=Depends(db_dep)):
    """System-wide recent sessions with duration and speaker email."""
    rows = list(db.sessions.find({}).sort("started_at", -1).skip(skip).limit(limit))

    # Map owner emails in bulk safely
    owner_ids = [ObjectId(r["owner_id"]) for r in rows if r.get("owner_id") and ObjectId.is_valid(r["owner_id"])]
    user_map = {str(u["_id"]): u.get("email", "") for u in db.users.find({"_id": {"$in": owner_ids}})}

    out = []
    for s in rows:
        owner_id = s.get("owner_id")
        started = s.get("started_at")
        ended = s.get("ended_at")
        duration = (ended - started) if (started and ended) else (time.time() - started if started else 0)

        out.append({
            "session_id": s["session_id"],
            "owner_id": owner_id,
            "owner_email": user_map.get(owner_id, "Unknown"),
            "title": s.get("title") or "Untitled session",
            "started_at": started,
            "ended_at": ended,
            "duration_seconds": round(max(0, duration), 1),
            "sharing": bool(s.get("share_token")),
            "live": ended is None,
        })

    return {"sessions": out}


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(session_id: str, db=Depends(db_dep)):
    """Admin delete session and events permanently."""
    db.transcript_events.delete_many({"session_id": session_id})
    db.sessions.delete_one({"session_id": session_id})
    return None

