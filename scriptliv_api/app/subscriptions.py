"""Subscription state and period rollover. Provider calls live in payments.py; this module only changes our own records."""
import time

from .config import get_settings
from .periods import add_months, period_for
from .plans import ADDON_MINUTES, BASIC, PLANS, PRO


def _now():
    return time.time()


# statuses: active -> past_due (provider is retrying) -> restricted | canceled (final failure). Only the first two keep paid
# allowance for new sessions; see docs/SCRIPTLIV_PLATFORM.md "Payment failure and access".
ACCESS_RESTRICTED = ("restricted", "canceled")


def is_restricted(sub: dict) -> bool:
    return sub.get("status") in ACCESS_RESTRICTED


def final_status() -> str:
    s = get_settings().payment_final_status
    return s if s in ACCESS_RESTRICTED else "restricted"


def payment_failed(db, customer_id: str, attempt_count: int, next_attempt_at: float | None, event_ts: float, now: float | None = None):
    """A provider-confirmed failed invoice. Moves to past_due while the provider keeps retrying, to the configured final
    status once the retries are used up. Older events (by provider timestamp) never override a newer state."""
    sub = db.subscriptions.find_one({"provider_customer_id": customer_id})
    if not sub or sub["plan"] != PRO or event_ts < sub.get("payment_state_at", 0):
        return None
    final = next_attempt_at is None or attempt_count >= get_settings().payment_max_retries
    upd = {"status": final_status() if final else "past_due", "payment_failed_count": attempt_count,
           "last_payment_failed_at": event_ts, "next_payment_attempt_at": None if final else next_attempt_at,
           "payment_state_at": event_ts}
    db.subscriptions.update_one({"_id": sub["_id"]}, {"$set": upd})
    return {**sub, **upd}


def payment_succeeded(db, customer_id: str, event_ts: float):
    """A provider-confirmed paid invoice restores (or keeps) full access."""
    sub = db.subscriptions.find_one({"provider_customer_id": customer_id})
    if not sub or event_ts < sub.get("payment_state_at", 0):
        return None
    upd = {"status": "active", "payment_failed_count": 0, "next_payment_attempt_at": None, "payment_state_at": event_ts}
    db.subscriptions.update_one({"_id": sub["_id"]}, {"$set": upd})
    return {**sub, **upd}


def create_basic(db, user_id: str, now: float | None = None) -> dict:
    now = now or _now()
    start, end, _ = period_for(now, now)
    sub = {
        "user_id": user_id, "plan": BASIC, "anchor": now, "period_start": start, "period_end": end,
        "included_used_seconds": 0.0, "cancel_at_period_end": False, "status": "active",
        "provider": None, "provider_customer_id": None, "provider_subscription_id": None, "created_at": now,
    }
    db.subscriptions.insert_one(sub)
    return sub


def get_subscription(db, user_id: str, now: float | None = None) -> dict:
    """Current subscription with the period rolled forward to `now` (persisted)."""
    now = now or _now()
    sub = db.subscriptions.find_one({"user_id": user_id})
    if sub is None:
        sub = create_basic(db, user_id, now)
    if now >= sub["period_end"]:
        if sub["plan"] == PRO and sub.get("cancel_at_period_end"):
            # paid access ended: back to Basic, anchored where the paid period ended
            sub.update(plan=BASIC, anchor=sub["period_end"], cancel_at_period_end=False, provider_subscription_id=None,
                       status="active")
        start, end, _ = period_for(sub["anchor"], now)
        # included minutes reset each period (no rollover)
        sub.update(period_start=start, period_end=end, included_used_seconds=0.0)
        db.subscriptions.update_one({"_id": sub["_id"]}, {"$set": {k: v for k, v in sub.items() if k != "_id"}})
    return sub


def activate_pro(db, user_id: str, now: float | None = None, provider=None, customer_id=None, subscription_id=None):
    """Called only after a payment provider confirmed payment (webhook) -- never directly from a client request."""
    now = now or _now()
    sub = get_subscription(db, user_id, now)
    db.subscriptions.update_one({"_id": sub["_id"]}, {"$set": {
        "plan": PRO, "anchor": now, "period_start": now, "period_end": add_months(now, 1), "included_used_seconds": 0.0,
        "cancel_at_period_end": False, "status": "active", "provider": provider, "payment_failed_count": 0,
        "next_payment_attempt_at": None, "provider_customer_id": customer_id, "provider_subscription_id": subscription_id}})
    return db.subscriptions.find_one({"_id": sub["_id"]})


def cancel(db, user_id: str, now: float | None = None) -> dict:
    sub = get_subscription(db, user_id, now)
    if sub["plan"] != PRO:
        raise ValueError("only a paid plan can be cancelled")
    db.subscriptions.update_one({"_id": sub["_id"]}, {"$set": {"cancel_at_period_end": True}})
    sub["cancel_at_period_end"] = True
    return sub


def resume(db, user_id: str, now: float | None = None) -> dict:
    sub = get_subscription(db, user_id, now)
    if sub["plan"] != PRO or not sub.get("cancel_at_period_end"):
        raise ValueError("nothing to resume")
    db.subscriptions.update_one({"_id": sub["_id"]}, {"$set": {"cancel_at_period_end": False}})
    sub["cancel_at_period_end"] = False
    return sub


def grant_addon(db, user_id: str, now: float | None = None, payment_id: str | None = None) -> dict:
    """1,000 extra minutes, valid until the end of the period they were bought in. Call only after payment confirmed."""
    now = now or _now()
    sub = get_subscription(db, user_id, now)
    doc = {"user_id": user_id, "seconds_total": ADDON_MINUTES * 60, "seconds_used": 0.0, "purchased_at": now,
           "expires_at": sub["period_end"], "payment_id": payment_id}
    db.addons.insert_one(doc)
    return doc


def active_addons(db, user_id: str, now: float | None = None) -> list[dict]:
    now = now or _now()
    return list(db.addons.find({"user_id": user_id, "expires_at": {"$gt": now}}).sort([("expires_at", 1), ("purchased_at", 1)]))


def plan_of(sub: dict):
    return PLANS[sub["plan"]]
