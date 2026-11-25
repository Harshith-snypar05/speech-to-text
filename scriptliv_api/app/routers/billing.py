import hashlib
import json
import time

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

import logging

from .. import account_deletion, payments, payments_cashfree, subscriptions, usage
from ..config import get_settings, promo_active
from ..deps import current_user, db_dep, now, verified_user
from ..plans import (
    ADDON_MAX_SESSION_MINUTES,
    ADDON_MINUTES,
    ADDON_NOTE,
    ADDON_PRICE_INR,
    ADDON_PRICE_USD,
    ADDON_TAX_NOTE,
    PLANS,
    PRO,
    PROMO_ALLOWANCE_MINUTES,
    with_gst,
)

router = APIRouter(prefix="/v1", tags=["billing"])


log = logging.getLogger("scriptliv.billing")


def _no_purchase_while_deleting(user: dict):
    """A purchase started while a deletion is claimed or tombstoned could be charged and then have nowhere to land."""
    if account_deletion.deletion_in_flight(user):
        _err(409, "delete_in_progress", "This account is being deleted, so it cannot start a purchase.")


def _deleting(db, uid, event: str, ref=None) -> bool:
    """Webhook guard. A provider event for a tombstoned account writes nothing (no subscription, add-on, payment row or
    email) and is acknowledged so the provider does not retry it forever. The ERROR line is the operator's cue to reconcile
    any charge at the provider by hand; billing policy and provider configuration are deliberately untouched."""
    if not account_deletion.is_deleting_uid(db, uid):
        return False
    log.error("billing_event_for_deleting_account uid=%s event=%s ref=%s", uid, event, ref)
    return True


def _err(status, code, message):
    raise HTTPException(status, {"code": code, "message": message})


def _not_configured():
    _err(503, "payments_not_configured", "Payments are not set up yet, so plans and add-ons cannot be purchased right now.")


@router.get("/plans")
def plans():
    return {
        "currency": "inr",
        "currency_symbol": "₹",
        "plans": [
            {
                "id": p.id,
                "name": p.name,
                "included_minutes": p.included_minutes,
                "max_session_minutes": p.max_session_minutes,
                "price_inr_month": p.price_inr_month,
                "price_usd_month": p.price_usd_month,
                "tax_note": p.tax_note,
                "price_display": p.price_display,
                "blurb": p.blurb,
            }
            for p in PLANS.values()
        ],
        "addon": {
            "minutes": ADDON_MINUTES,
            "price_inr": ADDON_PRICE_INR,
            "price_usd": ADDON_PRICE_USD,
            "tax_note": ADDON_TAX_NOTE,
            "max_session_minutes": ADDON_MAX_SESSION_MINUTES,
            "price_display": f"₹{ADDON_PRICE_INR:,} {ADDON_TAX_NOTE}",
            "note": ADDON_NOTE,
        },
        # buying is paused while the inaugural offer (free, fixed minutes per account) runs; clients hide plans and prices
        "purchasing_available": payments_cashfree.configured() and not promo_active(),
        "promo_active": promo_active(),
        "promo_until": get_settings().promo_unlimited_until if promo_active() else None,
        "promo_allowance_minutes": PROMO_ALLOWANCE_MINUTES if promo_active() else None,
    }


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
    return {
        "plan": p.id,
        "plan_name": p.name,
        "status": sub["status"],
        "period_start": sub["period_start"],
        "renews_or_resets_at": sub["period_end"],
        "cancel_at_period_end": sub["cancel_at_period_end"],
        # when cancelled, paid access lasts until the end of the period already paid for
        "access_ends_at": sub["period_end"] if sub["cancel_at_period_end"] else None,
        "price_inr_month": p.price_inr_month,
        "price_usd_month": p.price_usd_month,
        "price_display": p.price_display,
        "currency": "inr",
        "tax_note": p.tax_note,
        "payment": _payment_state(sub),
    }


@router.get("/subscription")
def subscription(user=Depends(current_user), db=Depends(db_dep)):
    return {"subscription": _sub_out(subscriptions.get_subscription(db, str(user["_id"]))), "purchasing_available": payments_cashfree.configured()}


class CheckoutIn(BaseModel):
    kind: str = Field(pattern="^(pro|addon)$")


@router.post("/billing/checkout")
def checkout(body: CheckoutIn, user=Depends(verified_user), db=Depends(db_dep)):
    """Unlike Stripe, Cashfree's checkout is not a URL: the frontend takes {kind, session_id} from
    here and hands it to Cashfree's own JS SDK (cashfree.checkout / cashfree.subscriptionsCheckout),
    which does the actual redirect. See scriptliv_web/lib/cashfree.ts."""
    _no_purchase_while_deleting(user)
    if promo_active():
        _err(409, "offer_active", "Minutes are free during our inaugural offer (each account gets a fixed allowance), so there is nothing to buy right now.")
    uid = str(user["_id"])
    sub = subscriptions.get_subscription(db, uid)
    if body.kind == "pro" and sub["plan"] == PRO:
        _err(409, "already_pro", "You are already on Pro." if sub["status"] == "active"
             else "Your Pro plan needs a payment. Update your payment method or retry the payment instead.")
    if body.kind == "addon":
        if sub["plan"] != PRO:
            _err(409, "addon_requires_pro", "Add-ons are a Pro perk. Upgrade to Pro first.")
        if sub["status"] != "active":
            _err(402, "payment_required", "Resolve your failed payment first: add-ons cannot be used while a payment is outstanding.")
    try:
        r = payments_cashfree.checkout_session(body.kind, uid, user["email"], user["name"], user.get("phone"))
        # "live" tells the frontend which Cashfree JS SDK mode to initialize with (sandbox vs production) --
        # carried per-request rather than duplicated into frontend build config, so the two can never drift.
        return {"kind": r["kind"], "session_id": r["session_id"], "live": get_settings().cashfree_live}
    except payments_cashfree.NotConfigured:
        _not_configured()
    except Exception:
        _err(502, "provider_error", "The payment provider could not start checkout. Try again shortly.")


@router.post("/billing/portal")
def portal(user=Depends(current_user), db=Depends(db_dep)):
    """Cashfree has no hosted self-service billing portal (unlike Stripe's Billing Portal) -- there is
    nothing to return a URL for. Cancel/resume are handled by our own endpoints below instead."""
    _not_configured()


@router.post("/billing/retry-payment")
def retry_payment(user=Depends(current_user), db=Depends(db_dep)):
    """Ask the provider to charge the outstanding invoice again. Access is restored only if the provider itself reports
    the invoice paid; clicking Retry never changes the subscription on its own.

    Still calls payments.py (Stripe) rather than Cashfree: no manual "retry this specific charge" endpoint was
    found in Cashfree's Subscriptions docs, so this intentionally falls through to NotConfigured/503 for every
    Cashfree subscription today (Stripe's own key is never set), which is an honest "not supported yet" rather
    than a guess at an unverified endpoint. Revisit once Cashfree's retry semantics are confirmed."""
    _no_purchase_while_deleting(user)
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
    if sub.get("provider") == "cashfree" and sub.get("provider_subscription_id"):
        # Cashfree subscriptions cancel immediately and permanently -- there is no "at period end" option
        # the way Stripe has. Stop future billing right now; the already-paid-for access this period is
        # still honored until period_end by our own cancel_at_period_end flag below, same as before from
        # the user's point of view. See resume()'s comment for the consequence of this.
        try:
            payments_cashfree.cancel_subscription(sub["provider_subscription_id"])
        except payments_cashfree.NotConfigured:
            _not_configured()
        except Exception:
            _err(502, "provider_error", "The payment provider could not cancel the plan. Nothing was changed.")
    return {"subscription": _sub_out(subscriptions.cancel(db, uid))}


@router.post("/subscription/resume")
def resume(user=Depends(current_user), db=Depends(db_dep)):
    _no_purchase_while_deleting(user)   # resuming re-arms billing, which would defeat the "cancel first" rule of a deletion
    uid = str(user["_id"])
    sub = subscriptions.get_subscription(db, uid)
    if sub["plan"] != PRO or not sub.get("cancel_at_period_end"):
        _err(409, "nothing_to_resume", "Your plan is not scheduled to cancel.")
    if sub.get("provider") == "cashfree":
        # cancel() above already cancelled the Cashfree mandate immediately and irreversibly -- there is
        # nothing left to "resume" the way un-setting Stripe's cancel_at_period_end could. This is a real
        # product gap from switching providers, not an oversight: flag it rather than silently letting the
        # user believe Pro will keep auto-renewing when there is no live mandate charging them anymore.
        _err(409, "resume_not_supported", "This plan's payment was already cancelled and cannot be resumed. Start a new Pro checkout instead.")
    return {"subscription": _sub_out(subscriptions.resume(db, uid))}


@router.get("/billing/payment-method")
def payment_method(user=Depends(current_user), db=Depends(db_dep)):
    """Deliberately always unavailable right now: Cashfree has no "list this customer's saved cards/UPI"
    endpoint the way Stripe does, so there is nothing honest to show here yet (not a Stripe leftover --
    payments.configured() is always False since Stripe's key is never set, which is exactly the point)."""
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


@router.post("/billing/webhook/cashfree")
async def cashfree_webhook(request: Request, x_webhook_signature: str | None = Header(default=None),
                            x_webhook_timestamp: str | None = Header(default=None), db=Depends(db_dep)):
    payload = await request.body()
    if not payments_cashfree.verify_webhook(payload, x_webhook_signature or "", x_webhook_timestamp or ""):
        _err(400, "bad_signature", "Invalid signature.")
    try:
        ev = json.loads(payload)
    except ValueError:
        _err(400, "bad_payload", "Invalid payload.")
    if not isinstance(ev, dict) or not ev.get("type"):
        _err(400, "bad_payload", "Invalid payload.")
    # Cashfree webhooks carry no confirmed unique event id (unlike Stripe's ev["id"]) -- a hash of the
    # signed timestamp+payload stands in for one instead. A genuine retry of the same delivery has the
    # same signature over the same payload, so this still dedupes correctly; two different real events
    # happening to collide is not a realistic risk at this volume.
    event_id = "cf:" + hashlib.sha256((x_webhook_timestamp or "").encode() + payload).hexdigest()
    try:
        db.provider_events.insert_one({"event_id": event_id, "type": ev.get("type"), "at": now()})
    except DuplicateKeyError:
        return {"received": True, "duplicate": True}
    try:
        _apply_cashfree_event(db, ev)
    except Exception:
        db.provider_events.delete_one({"event_id": event_id})
        _err(500, "webhook_failed", "Event could not be processed; the provider should retry.")
    return {"received": True}


def _dig(d: dict, *paths: str):
    """Looks up the first of several plausible dotted paths that exists. Cashfree's exact webhook envelope
    nesting isn't fully confirmed from their docs (some fields read as flat, others as nested under e.g.
    "order"/"subscription_details") -- this tries the shapes that showed up in their published examples
    instead of committing to one that might not match a real delivery."""
    for path in paths:
        cur = d
        for key in path.split("."):
            if not isinstance(cur, dict) or key not in cur:
                cur = None
                break
            cur = cur[key]
        if cur is not None:
            return cur
    return None


def _apply_cashfree_event(db, ev: dict):
    data = ev.get("data", {}) or {}
    t = ev.get("type")
    ts = now()

    if t == "PAYMENT_SUCCESS_WEBHOOK":
        order_id = _dig(data, "order.order_id", "order_id")
        amount = _dig(data, "order.order_amount", "payment.payment_amount", "order_amount") or 0
        ref = payments_cashfree.parse_reference(order_id or "")
        if ref and ref[0] == "addon":
            _, uid = ref
            if _deleting(db, uid, t, order_id):
                return
            pid = _record_payment(db, {"user_id": uid, "created_at": ts, "description": f"Add-on {ADDON_MINUTES} minutes",
                                       "amount_cents": int(round(float(amount) * 100)), "currency": "inr",
                                       "status": "paid", "provider_ref": order_id})
            if pid is not None:
                try:
                    subscriptions.grant_addon(db, uid, payment_id=str(pid))
                except Exception:
                    db.payments.delete_one({"_id": pid})
                    raise
                _send_invoice(db, uid, pid)

    elif t == "SUBSCRIPTION_PAYMENT_SUCCESS":
        subscription_id = _dig(data, "subscription_details.subscription_id", "subscription_id")
        cf_subscription_id = _dig(data, "subscription_details.cf_subscription_id", "cf_subscription_id")
        amount = _dig(data, "subscription_details.plan_details.plan_recurring_amount", "payment_amount") or with_gst(PLANS[PRO].price_inr_month)
        ref = payments_cashfree.parse_reference(subscription_id or "")
        if ref and ref[0] == "pro":
            _, uid = ref
            if _deleting(db, uid, t, subscription_id):
                return
            existing = db.subscriptions.find_one({"user_id": uid})
            if existing and existing.get("provider_subscription_id") == subscription_id and existing.get("plan") == PRO:
                subscriptions.payment_succeeded(db, uid, ts)  # renewal of an already-active Pro subscription
            else:
                subscriptions.activate_pro(db, uid, provider="cashfree", customer_id=uid, subscription_id=subscription_id)
            pid = _record_payment(db, {"user_id": uid, "created_at": ts, "description": "ScriptLiv Pro",
                                       "amount_cents": int(round(float(amount) * 100)), "currency": "inr",
                                       "status": "paid", "provider_ref": cf_subscription_id or subscription_id})
            if pid is not None:   # a duplicate delivery recorded nothing, so it sends no second invoice
                _send_invoice(db, uid, pid)

    elif t == "SUBSCRIPTION_PAYMENT_FAILED":
        subscription_id = _dig(data, "subscription_details.subscription_id", "subscription_id")
        ref = payments_cashfree.parse_reference(subscription_id or "")
        if ref and ref[0] == "pro":
            _, uid = ref
            if _deleting(db, uid, t, subscription_id):
                return
            _record_payment(db, {"user_id": uid, "created_at": ts, "description": "ScriptLiv Pro",
                                 "amount_cents": 0, "currency": "inr", "status": "failed",
                                 "provider_ref": "failed:" + subscription_id + ":" + str(int(ts))})
            # Cashfree's retry-count/next-attempt fields for this event aren't confirmed from their docs
            # (unlike Stripe's attempt_count/next_payment_attempt); treat every failure as attempt 1 with
            # another attempt due in an hour so one failure doesn't immediately restrict access before we
            # can verify the real retry cadence against a live sandbox failure.
            subscriptions.payment_failed(db, uid, 1, ts + 3600, ts)

    elif t == "SUBSCRIPTION_STATUS_CHANGE_WEBHOOK":
        subscription_id = _dig(data, "subscription_details.subscription_id", "subscription_id")
        status = _dig(data, "subscription_details.subscription_status", "subscription_status")
        if status in ("CANCELLED", "COMPLETED", "EXPIRED"):
            sub = db.subscriptions.find_one({"provider_subscription_id": subscription_id})
            if sub:
                db.subscriptions.update_one({"_id": sub["_id"]}, {"$set": {"cancel_at_period_end": True}})


def _send_invoice(db, uid: str, payment_id):
    """Email the invoice for a just-recorded paid payment. Best effort: it never fails the webhook."""
    from bson import ObjectId

    from .. import invoice
    try:
        user = db.users.find_one({"_id": ObjectId(uid)})
        payment = db.payments.find_one({"_id": payment_id})
        if user and payment:
            invoice.send(db, user, payment, db.subscriptions.find_one({"user_id": uid}))
    except Exception:
        pass


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
        if uid and kind in ("pro", "addon") and _deleting(db, uid, t, obj.get("id")):
            return
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
        if sub and _deleting(db, sub["user_id"], t, obj.get("id")):
            return
        if sub:
            subscriptions.payment_succeeded(db, obj.get("customer"), ev.get("created") or now())
            _record_payment(db, {"user_id": sub["user_id"], "created_at": now(), "description": "ScriptLiv Pro",
                                 "amount_cents": obj.get("amount_paid", 0), "currency": obj.get("currency", "usd"),
                                 "status": "paid", "provider_ref": obj.get("id"), "receipt_url": obj.get("hosted_invoice_url")})
    elif t == "invoice.payment_failed":
        sub = db.subscriptions.find_one({"provider_customer_id": obj.get("customer")})
        if sub and _deleting(db, sub["user_id"], t, obj.get("id")):
            return
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
