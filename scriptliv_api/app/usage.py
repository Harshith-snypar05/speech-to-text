"""Usage ledger. Only the speaker's account is metered; viewers never reach this module.

Metering unit: whole seconds of speaker session time, shown to customers in minutes. The relay reports the
*cumulative* seconds of a session, so a retried or duplicated report cannot bill twice (only the increase is applied).
Included minutes are consumed first, then add-on minutes (soonest expiry first). Included and add-on usage are
stored separately: subscription.included_used_seconds, addons[].seconds_used, and one ledger row per application.
Minute-level tracking: usage_minutes holds seconds per (session, minute-of-session).
"""
import math
import time
from contextlib import contextmanager

from pymongo.errors import DuplicateKeyError

from .plans import BASIC, PLANS
from .subscriptions import active_addons, get_subscription, is_restricted, plan_of

DEFAULT_WARN_PERCENTS = [80, 95]
# A running session holds a *grant*: the highest cumulative second count it may reach. Grants of one account's open
# sessions never add up to more than the account can still spend, so concurrent sessions cannot overspend.
# Each grant looks only GRANT_WINDOW seconds ahead and is extended by every usage report; a session whose reports
# stop for SESSION_STALE seconds no longer holds its reservation.
GRANT_WINDOW = 300
SESSION_STALE = 90


class SessionOwnerMismatch(Exception):
    pass


def remaining(db, user_id: str, now: float | None = None) -> dict:
    now = now or time.time()
    sub = get_subscription(db, user_id, now)
    restricted = is_restricted(sub)
    # A restricted (payment-failed) account keeps only the free Basic allowance: no paid plan minutes, no add-ons.
    plan = PLANS[BASIC] if restricted else plan_of(sub)
    inc_rem = max(0.0, plan.included_seconds - sub["included_used_seconds"])
    addons = [] if restricted else active_addons(db, user_id, now)
    add_rem = sum(max(0.0, a["seconds_total"] - a["seconds_used"]) for a in addons)
    return {"sub": sub, "plan": plan, "restricted": restricted, "included_remaining": inc_rem, "addon_remaining": add_rem,
            "addons": addons, "total_remaining": inc_rem + add_rem}


@contextmanager
def user_lock(db, user_id: str, wait: float = 3.0):
    """Short per-account mutex (a TTL-style lock document) so grant calculation is atomic across API workers."""
    t0 = time.time()
    while True:
        now = time.time()
        try:
            r = db.usage_locks.update_one({"_id": user_id, "until": {"$lt": now}}, {"$set": {"until": now + 5}}, upsert=True)
            if r.modified_count == 1 or r.upserted_id is not None:
                break
        except DuplicateKeyError:
            pass
        if time.time() - t0 > wait:
            raise TimeoutError("usage lock busy")
        time.sleep(0.01)
    try:
        yield
    finally:
        db.usage_locks.update_one({"_id": user_id}, {"$set": {"until": 0}})


def _cas_take(coll, doc_id, field: str, cap: float, want: float) -> float:
    """Atomically add up to `want` to coll[doc_id][field] without letting it pass `cap`. Returns what was added."""
    for _ in range(50):
        d = coll.find_one({"_id": doc_id}, {field: 1})
        take = min(want, cap - d[field])
        if take <= 1e-9:
            return 0.0
        if coll.update_one({"_id": doc_id, field: d[field]}, {"$inc": {field: take}}).modified_count == 1:
            return take
    raise RuntimeError("usage counter contention")


def _personal_room(db, user_id: str, r: dict) -> float:
    """Seconds the account may still spend before its own personal limit (inf when none is set)."""
    st = db.settings.find_one({"user_id": user_id}) or {}
    cap_min = st.get("personal_limit_minutes")
    if not cap_min:
        return float("inf")
    used = r["sub"]["included_used_seconds"] + sum(a["seconds_used"] for a in r["addons"])
    return max(0.0, cap_min * 60 - used)


def _allowance(db, user_id: str, r: dict) -> float:
    return min(r["total_remaining"], _personal_room(db, user_id, r))


def authorize(db, user_id: str, now: float | None = None, session_id: str | None = None, midsession: bool = False) -> dict:
    """May this account start (or keep) speaking? Includes the user's own personal limit setting.

    With a `session_id` the answer is a reservation: remaining_seconds is how far past what this session has already
    been billed it may run, after setting aside what the account's other open sessions hold. Without one it is the
    plain account-level answer (used by tests and read-only checks).

    `midsession=True` is the answer to a periodic usage report: it extends the grant of a session that is still open, but
    never reopens a session that has already ended (a late report must not resurrect a released reservation)."""
    now = now or time.time()
    if session_id is None:
        return _decide(db, user_id, now, 0.0)
    with user_lock(db, user_id):
        row = db.usage_sessions.find_one({"session_id": session_id})
        if row is not None and row["user_id"] != user_id:
            return {"allowed": False, "reason": "session_taken", "remaining_seconds": 0}
        if midsession and (row is None or row["ended_at"] is not None):
            return {"allowed": False, "reason": "session_ended", "remaining_seconds": 0,
                    "base_seconds": row["metered_seconds"] if row else 0.0}
        metered = row["metered_seconds"] if row else 0.0
        held = 0.0
        for o in db.usage_sessions.find({"user_id": user_id, "ended_at": None, "session_id": {"$ne": session_id},
                                         "last_report_at": {"$gt": now - SESSION_STALE}}):
            held += max(0.0, o.get("grant_seconds", 0.0) - o["metered_seconds"])
        out = _decide(db, user_id, now, held, metered)
        if row is None:
            try:
                db.usage_sessions.insert_one({"session_id": session_id, "user_id": user_id, "started_at": now, "ended_at": None,
                                              "metered_seconds": 0.0, "included_seconds": 0.0, "addon_seconds": 0.0,
                                              "unbilled_overshoot_seconds": 0.0, "last_report_at": now, "grant_seconds": 0.0})
            except DuplicateKeyError:
                pass
        grant = metered + (min(out["remaining_seconds"], GRANT_WINDOW) if out["allowed"] else 0)
        # an allowed reconnect to the same session reopens it (one row, so no second reservation); its cumulative count
        # carries on from `metered`. A denied one releases nothing and holds nothing.
        upd = {"grant_seconds": grant, "last_report_at": now}
        if out["allowed"]:
            upd["ended_at"] = None
        db.usage_sessions.update_one({"session_id": session_id}, {"$set": upd})
        out["remaining_seconds"] = int(grant - metered) if out["allowed"] else 0
        out["base_seconds"] = metered
        return out


def _decide(db, user_id: str, now: float, held: float, session_metered: float | None = None) -> dict:
    r = remaining(db, user_id, now)
    cap = r["plan"].max_session_seconds
    if r["total_remaining"] <= 0:
        return {"allowed": False, "reason": "payment_required" if r["restricted"] else "quota_exhausted", "remaining_seconds": 0}
    room = _personal_room(db, user_id, r)
    if room <= 0:
        return {"allowed": False, "reason": "personal_limit", "remaining_seconds": 0}
    free = min(r["total_remaining"], room) - held
    if free < 1:  # everything left is held by this account's other running sessions
        return {"allowed": False, "reason": "allowance_reserved", "remaining_seconds": 0}
    out = {"allowed": True, "reason": None, "remaining_seconds": int(free)}
    if cap is not None and session_metered is not None:
        # per-session cap (free tier): one session may never run past `cap` cumulative seconds
        out["session_cap_seconds"] = cap
        left = cap - session_metered
        if left < 1:
            return {"allowed": False, "reason": "session_limit", "remaining_seconds": 0, "session_cap_seconds": cap}
        out["remaining_seconds"] = int(min(free, left))
    return out


def _spread_minutes(db, user_id, session_id, prev_cum, delta, now):
    """Add `delta` seconds to the per-minute buckets covering session time [prev_cum, prev_cum + delta)."""
    t, left = prev_cum, delta
    while left > 1e-9:
        minute = int(t // 60)
        take = min(left, (minute + 1) * 60 - t)
        db.usage_minutes.update_one({"session_id": session_id, "minute": minute},
                                    {"$inc": {"seconds": take}, "$setOnInsert": {"user_id": user_id, "ts": now}}, upsert=True)
        t += take
        left -= take


def record(db, user_id: str, session_id: str, cumulative_seconds: float, now: float | None = None, final: bool = False) -> dict:
    """Apply a cumulative speaker-seconds report for one session. Idempotent; returns what was applied."""
    now = now or time.time()
    cum = float(math.ceil(round(cumulative_seconds, 3))) if final else float(math.floor(round(cumulative_seconds, 3)))
    cum = max(0.0, cum)
    row = db.usage_sessions.find_one({"session_id": session_id})
    if row is None:
        try:
            db.usage_sessions.insert_one({"session_id": session_id, "user_id": user_id, "started_at": now, "ended_at": None,
                                          "metered_seconds": 0.0, "included_seconds": 0.0, "addon_seconds": 0.0,
                                          "unbilled_overshoot_seconds": 0.0, "last_report_at": now})
        except Exception:  # raced with another first report: re-read below
            pass
        row = db.usage_sessions.find_one({"session_id": session_id})
    if row["user_id"] != user_id:
        raise SessionOwnerMismatch(session_id)
    prev = row["metered_seconds"]
    delta = cum - prev
    none = {"applied_seconds": 0.0, "included": 0.0, "addon": 0.0, "unbilled_overshoot": 0.0}
    if delta <= 0:
        # nothing new to bill, but the report still proves the session is alive (keeps its reservation) or ended
        db.usage_sessions.update_one({"session_id": session_id}, {"$set": {"last_report_at": now, **({"ended_at": now} if final and row["ended_at"] is None else {})}})
        return none
    # claim the increase first so a retry can never apply it twice
    claim = db.usage_sessions.update_one({"session_id": session_id, "metered_seconds": prev},
                                         {"$set": {"metered_seconds": cum, "last_report_at": now}})
    if claim.modified_count != 1:
        return {**none, "note": "concurrent report"}
    _spread_minutes(db, user_id, session_id, prev, delta, now)
    r = remaining(db, user_id, now)
    sub = r["sub"]
    # Strict limit. Only seconds the account can still fund AND this session's reservation (grant) covers are deducted:
    # never past the plan, the add-ons, the account's personal limit or the grant. Whatever is left over (audio that got
    # through before the relay stopped, the up-to-1 s from rounding a closing report up) is NOT charged: it is recorded
    # as `unbilled_overshoot` on the session and in the ledger, so it stays auditable and never extends the allowance.
    grant = row.get("grant_seconds")
    left = min(delta, _personal_room(db, user_id, r))
    if grant is not None:   # sessions that went through authorize() carry a grant; direct reports (tests/tools) do not
        left = min(left, max(0.0, grant - prev))
    inc = _cas_take(db.subscriptions, sub["_id"], "included_used_seconds", r["plan"].included_seconds, left) if left > 0 else 0.0
    if inc > 0:
        db.usage_ledger.insert_one({"user_id": user_id, "session_id": session_id, "seconds": inc, "source": "included",
                                    "addon_id": None, "period_start": sub["period_start"], "ts": now})
    left -= inc
    add_total = 0.0
    for a in r["addons"]:
        if left <= 1e-9:
            break
        take = _cas_take(db.addons, a["_id"], "seconds_used", a["seconds_total"], left)
        if take > 0:
            db.usage_ledger.insert_one({"user_id": user_id, "session_id": session_id, "seconds": take, "source": "addon",
                                        "addon_id": str(a["_id"]), "period_start": sub["period_start"], "ts": now})
            left -= take
            add_total += take
    overshoot = max(0.0, delta - inc - add_total)
    if overshoot > 1e-9:
        db.usage_ledger.insert_one({"user_id": user_id, "session_id": session_id, "seconds": overshoot, "source": "unbilled_overshoot",
                                    "addon_id": None, "period_start": sub["period_start"], "ts": now})
    upd = {"$inc": {"included_seconds": inc, "addon_seconds": add_total, "unbilled_overshoot_seconds": overshoot}}
    if final:
        upd["$set"] = {"ended_at": now}
    db.usage_sessions.update_one({"session_id": session_id}, upd)
    return {"applied_seconds": delta, "included": inc, "addon": add_total, "unbilled_overshoot": overshoot}


def summary(db, user_id: str, now: float | None = None) -> dict:
    now = now or time.time()
    r = remaining(db, user_id, now)
    sub, plan = r["sub"], r["plan"]    # `plan` is the plan whose minutes apply now (Basic while restricted)
    shown = plan_of(sub)
    used_inc = sub["included_used_seconds"]
    addon_used = sum(a["seconds_used"] for a in r["addons"])
    st = db.settings.find_one({"user_id": user_id}) or {}
    pct = 100.0 * used_inc / plan.included_seconds if plan.included_seconds else 0.0
    thresholds = st.get("warn_percents") or DEFAULT_WARN_PERCENTS
    exhausted = r["total_remaining"] <= 0
    warnings = [{"level": t, "message": f"You have used {t}% of your included minutes."} for t in sorted(thresholds) if t <= pct < 100]
    if exhausted:
        warnings.append({"level": 100, "message": "Payment required: update your payment method to restore your plan."
                         if r["restricted"] else "You are out of minutes. Buy an add-on or wait for your reset date."})
    return {
        "plan": shown.id, "plan_name": shown.name, "effective_plan": plan.id, "restricted": r["restricted"],
        "period_start": sub["period_start"], "reset_at": sub["period_end"],
        "included_minutes": plan.included_minutes, "included_used_seconds": used_inc,
        "included_remaining_seconds": r["included_remaining"], "percent_used": round(pct, 1),
        "addon_remaining_seconds": r["addon_remaining"], "addon_used_seconds": addon_used,
        "addons": [{"id": str(a["_id"]), "minutes_total": a["seconds_total"] / 60,
                    "remaining_seconds": max(0.0, a["seconds_total"] - a["seconds_used"]), "expires_at": a["expires_at"]}
                   for a in r["addons"]],
        "total_remaining_seconds": r["total_remaining"], "warnings": warnings,
        "cancel_at_period_end": sub["cancel_at_period_end"],
    }
