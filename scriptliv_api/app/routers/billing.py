import json
import time

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

from .. import payments, subscriptions, usage
from ..config import get_settings
from ..deps import current_user, db_dep, now, verified_user
from ..plans import ADDON_MINUTES, ADDON_PRICE_USD, PLANS, PRO

router = APIRouter(prefix="/v1", tags=["billing"])


def _err(status, code, message):
    raise HTTPException(status, {"code": code, "message": message})


def _not_configured():
    _err(503, "payments_not_configured", "Payments are not set up yet, so plans and add-ons cannot be purchased right now.")


@router.get("/plans")
def plans():
    return {"plans": [{"id": p.id, "name": p.name, "included_minutes": p.included_minutes, "max_session_minutes": p.max_session_minutes, "price_usd_month": p.price_usd_month,
                       "blurb": p.blurb} for p in PLANS.values()],
            "addon": {"minutes": ADDON_MINUTES, "price_usd": ADDON_PRICE_USD,
                      "note": "Add-on minutes are valid until the end of the billing period you buy them in."},
            "purchasing_available": payments.configured()}


PAYMENT_MESSAGES = {
    "past_due": "We could not charge your payment method. Your plan stays active while the payment is retried. "
                "Update your payment method or retry the payment now.",
    "restricted": "Payment required. After repeated failed payments your Pro minutes and add-ons are paused; you can "
                  "still record with the free Basic allowance. Update your payment method or retry the payment to restore your plan.",
    "canceled": "Payment required. Your paid plan was cancelled after repeated failed payments; you can still record with "
                "the free Basic allowance. Update your payment method to subscribe again.",
}


def _payment_state(sub):
    """What the customer needs to know about a failed payment (None while everything is paid)."""
    st = sub["status"]
    if st == "active":
        return None
    cfg = get_settings()
    last = sub.get("last_retry_at") or 0
    wait = max(0, int(last + cfg.payment_retry_cooldown - now()))
    return {"state": st, "access_restricted": subscriptions.is_restricted(sub), "message": PAYMENT_MESSAGES.get(st, PAYMENT_MESSAGES["restricted"]),
            "failed_attempts": sub.get("payment_failed_count", 0), "max_retries": cfg.payment_max_retries,
            "next_attempt_at": sub.get("next_payment_attempt_at"), "can_retry": st in ("past_due", "restricted") and wait == 0,
            "retry_in_seconds": wait}


def _sub_out(sub):
    p = PLANS[sub["plan"]]
    return {"plan": p.id, "plan_name": p.name, "status": sub["status"], "period_start": sub["period_start"],
            "renews_or_resets_at": sub["period_end"], "cancel_at_period_end": sub["cancel_at_period_end"],
            # when cancelled, paid access lasts until the end of the period already paid for
            "access_ends_at": sub["period_end"] if sub["cancel_at_period_end"] else None,
            "price_usd_month": p.price_usd_month, "payment": _payment_state(sub)}


@router.get("/subscription")
def subscription(user=Depends(current_user), db=Depends(db_dep)):
    return {"subscription": _sub_out(subscriptions.get_subscription(db, str(user["_id"]))), "purchasing_available": payments.configured()}


class CheckoutIn(BaseModel):
    kind: str = Field(pattern="^(pro|addon)$")


@router.post("/billing/checkout")
def checkout(body: CheckoutIn, user=Depends(verified_user), db=Depends(db_dep)):
    uid = str(user["_id"])
    sub = subscriptions.get_subscription(db, uid)
    if body.kind == "pro" and sub["plan"] == PRO:
        _err(409, "already_pro", "You are already on Pro." if sub["status"] == "active"
             else "Your Pro plan needs a payment. Update your payment method or retry the payment instead.")
    if body.kind == "addon" and sub["status"] != "active":
        _err(402, "payment_required", "Resolve your failed payment first: add-ons cannot be used while a payment is outstanding.")
    try:
        return {"url": payments.checkout_url(body.kind, uid, user["email"], sub.get("provider_customer_id"))}
    except payments.NotConfigured:
        _not_configured()
    except Exception:
        _err(502, "provider_error", "The payment provider could not start checkout. Try again shortly.")


@router.post("/billing/portal")
def portal(user=Depends(current_user), db=Depends(db_dep)):
    sub = subscriptions.get_subscription(db, str(user["_id"]))
    if not sub.get("provider_customer_id"):
        _err(404, "no_billing_account", "You do not have a billing account yet.")
    try:
        return {"url": payments.portal_url(sub["provider_customer_id"])}
    except payments.NotConfigured:
        _not_configured()
    except Exception:
        _err(502, "provider_error", "The payment provider is unavailable. Try again shortly.")


@router.post("/billing/retry-payment")
def retry_payment(user=Depends(current_user), db=Depends(db_dep)):
    """Ask the provider to charge the outstanding invoice again. Access is restored only if the provider itself reports
    the invoice paid; clicking Retry never changes the subscription on its own."""
    uid = str(user["_id"])
    sub = subscriptions.get_subscription(db, uid)
    if sub["plan"] != PRO or sub["status"] not in ("past_due", "restricted") or not sub.get("provider_customer_id"):
        _err(409, "nothing_to_retry", "There is no outstanding payment to retry.")
    wait = int(sub.get("last_retry_at", 0) + get_settings().payment_retry_cooldown - now())
    if wait > 0:
        _err(429, "retry_too_soon", f"Please wait {wait} seconds before retrying the payment.")
    # claim the attempt first so two clicks cannot both reach the provider
    claim = db.subscriptions.update_one({"_id": sub["_id"], "last_retry_at": sub.get("last_retry_at")}, {"$set": {"last_retry_at": now()}})
    if claim.modified_count != 1:
        _err(429, "retry_too_soon", "A retry is already in progress.")
    try:
        res = payments.retry_invoice(sub["provider_customer_id"])
    except payments.NotConfigured:
        _not_configured()
    except Exception:
        _err(502, "provider_error", "The payment provider could not be reached. Nothing was changed; try again shortly.")
    if res["paid"]:
        subscriptions.payment_succeeded(db, sub["provider_customer_id"], now())
        return {"result": "paid", "subscription": _sub_out(subscriptions.get_subscription(db, uid))}
    if res["declined"]:
        _err(402, "payment_failed", "The payment was declined. Update your payment method, then retry.")
    _err(409, "nothing_to_retry", "There is no outstanding payment to retry.")


@router.post("/subscription/cancel")
def cancel(user=Depends(current_user), db=Depends(db_dep)):
    uid = str(user["_id"])
    sub = subscriptions.get_subscription(db, uid)
    if sub["plan"] != PRO:
        _err(409, "nothing_to_cancel", "You are on the free Basic plan, so there is nothing to cancel.")
    if sub.get("cancel_at_period_end"):
        return {"subscription": _sub_out(sub)}
    if sub.get("provider_subscription_id"):
        try:
            payments.cancel_at_period_end(sub["provider_subscription_id"], True)
        except payments.NotConfigured:
            _not_configured()
        except Exception:
            _err(502, "provider_error", "The payment provider could not cancel the plan. Nothing was changed.")
    return {"subscription": _sub_out(subscriptions.cancel(db, uid))}


@router.post("/subscription/resume")
def resume(user=Depends(current_user), db=Depends(db_dep)):
    uid = str(user["_id"])
    sub = subscriptions.get_subscription(db, uid)
    if sub["plan"] != PRO or not sub.get("cancel_at_period_end"):
        _err(409, "nothing_to_resume", "Your plan is not scheduled to cancel.")
    if sub.get("provider_subscription_id"):
        try:
            payments.cancel_at_period_end(sub["provider_subscription_id"], False)
        except payments.NotConfigured:
            _not_configured()
        except Exception:
            _err(502, "provider_error", "The payment provider could not resume the plan. Nothing was changed.")
    return {"subscription": _sub_out(subscriptions.resume(db, uid))}


@router.get("/billing/payment-method")
def payment_method(user=Depends(current_user), db=Depends(db_dep)):
    sub = subscriptions.get_subscription(db, str(user["_id"]))
    if not payments.configured():
        return {"available": False, "payment_method": None, "reason": "payments_not_configured"}
    if not sub.get("provider_customer_id"):
        return {"available": True, "payment_method": None}
    try:
        return {"available": True, "payment_method": payments.payment_method(sub["provider_customer_id"])}
    except Exception:
        _err(502, "provider_error", "Could not load the payment method. Try again shortly.")


@router.get("/billing/payments")
def payment_history(user=Depends(current_user), db=Depends(db_dep)):
    rows = db.payments.find({"user_id": str(user["_id"])}).sort("created_at", -1).limit(100)
    return {"available": payments.configured() or db.payments.count_documents({"user_id": str(user["_id"])}) > 0,
            "payments": [{"id": str(r["_id"]), "created_at": r["created_at"], "description": r["description"],
                          "amount_cents": r["amount_cents"], "currency": r["currency"], "status": r["status"],
                          "receipt_url": r.get("receipt_url")} for r in rows]}


class BillingDetailsIn(BaseModel):
    name: str = Field(default="", max_length=120)
    company: str = Field(default="", max_length=120)
    address: str = Field(default="", max_length=300)
    country: str = Field(default="", max_length=2)
    tax_id: str = Field(default="", max_length=40)


@router.get("/billing/details")
def get_details(user=Depends(current_user), db=Depends(db_dep)):
    return {"details": (db.billing_details.find_one({"user_id": str(user["_id"])}) or {}).get("details", {})}


@router.put("/billing/details")
def put_details(body: BillingDetailsIn, user=Depends(current_user), db=Depends(db_dep)):
    db.billing_details.update_one({"user_id": str(user["_id"])}, {"$set": {"details": body.model_dump()}}, upsert=True)
    return {"details": body.model_dump()}


@router.post("/billing/webhook")
async def webhook(request: Request, stripe_signature: str | None = Header(default=None), db=Depends(db_dep)):
    payload = await request.body()
    if not payments.verify_webhook(payload, stripe_signature or ""):
        _err(400, "bad_signature", "Invalid signature.")
    try:
        ev = json.loads(payload)
    except ValueError:
        _err(400, "bad_payload", "Invalid payload.")
    if not isinstance(ev, dict) or not ev.get("id"):
        _err(400, "bad_payload", "Invalid payload.")
    # claim the event id first (unique index): a duplicate or concurrent delivery stops here, so it is applied once
    try:
        db.provider_events.insert_one({"event_id": ev["id"], "type": ev.get("type"), "at": now()})
    except DuplicateKeyError:
        return {"received": True, "duplicate": True}
    try:
        _apply_event(db, ev)
    except Exception:
        # not applied: release the claim so the provider's retry is processed instead of being ignored
        db.provider_events.delete_one({"event_id": ev["id"]})
        _err(500, "webhook_failed", "Event could not be processed; the provider should retry.")
    return {"received": True}


def _record_payment(db, row: dict):
    """Insert a payment once per provider reference. Returns the id, or None when already recorded."""
    try:
        return db.payments.insert_one(row).inserted_id
    except DuplicateKeyError:
        return None


def _apply_event(db, ev: dict):
    obj = ev.get("data", {}).get("object", {})
    t = ev.get("type")
    if t == "checkout.session.completed" and obj.get("payment_status") in ("paid", "no_payment_required"):
        uid, kind = (obj.get("metadata") or {}).get("user_id"), (obj.get("metadata") or {}).get("kind")
        if uid and kind == "pro":
            subscriptions.activate_pro(db, uid, provider="stripe", customer_id=obj.get("customer"), subscription_id=obj.get("subscription"))
        elif uid and kind == "addon":
            pid = _record_payment(db, {"user_id": uid, "created_at": now(), "description": f"Add-on {ADDON_MINUTES} minutes",
                                       "amount_cents": obj.get("amount_total", 0), "currency": obj.get("currency", "usd"),
                                       "status": "paid", "provider_ref": obj.get("payment_intent") or obj.get("id")})
            if pid is not None:  # the add-on is granted only for a payment that was not already recorded
                try:
                    subscriptions.grant_addon(db, uid, payment_id=str(pid))
                except Exception:
                    db.payments.delete_one({"_id": pid})
                    raise
    elif t == "invoice.paid":
        sub = db.subscriptions.find_one({"provider_customer_id": obj.get("customer")})
        if sub:
            subscriptions.payment_succeeded(db, obj.get("customer"), ev.get("created") or now())
            _record_payment(db, {"user_id": sub["user_id"], "created_at": now(), "description": "ScriptLiv Pro",
                                 "amount_cents": obj.get("amount_paid", 0), "currency": obj.get("currency", "usd"),
                                 "status": "paid", "provider_ref": obj.get("id"), "receipt_url": obj.get("hosted_invoice_url")})
    elif t == "invoice.payment_failed":
        sub = db.subscriptions.find_one({"provider_customer_id": obj.get("customer")})
        if sub:  # recorded as failed only; it never creates or extends a subscription
            _record_payment(db, {"user_id": sub["user_id"], "created_at": now(), "description": "ScriptLiv Pro",
                                 "amount_cents": obj.get("amount_due", 0), "currency": obj.get("currency", "usd"),
                                 "status": "failed", "provider_ref": "failed:" + str(obj.get("id"))})
            # the provider's retry schedule decides: still retrying -> past_due; out of retries -> the configured final status
            subscriptions.payment_failed(db, obj.get("customer"), int(obj.get("attempt_count") or 1),
                                         obj.get("next_payment_attempt"), ev.get("created") or now())
    elif t == "customer.subscription.updated" and obj.get("status") in ("unpaid", "past_due"):
        sub = db.subscriptions.find_one({"provider_subscription_id": obj.get("id")})
        if sub and sub["plan"] == PRO and sub["status"] == "active":
            ts = ev.get("created") or now()
            if obj["status"] == "unpaid":
                db.subscriptions.update_one({"_id": sub["_id"]}, {"$set": {"status": subscriptions.final_status(), "payment_state_at": ts}})
            else:
                db.subscriptions.update_one({"_id": sub["_id"]}, {"$set": {"status": "past_due", "payment_state_at": ts}})
    elif t == "customer.subscription.deleted":
        sub = db.subscriptions.find_one({"provider_subscription_id": obj.get("id")})
        if sub:
            db.subscriptions.update_one({"_id": sub["_id"]}, {"$set": {"cancel_at_period_end": True}})
