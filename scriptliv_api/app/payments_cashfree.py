"""Payment provider adapter: Cashfree (Orders API for add-ons, Subscriptions API for the recurring Pro
plan), over HTTPS. Sandbox by default (CASHFREE_LIVE=1 switches to the live base URL and must only be set
once real keys are in place). With CASHFREE_TEST_APP_ID/CASHFREE_SECRET_KEY missing, every call raises
NotConfigured and the API returns 503 payments_not_configured, same contract as payments.py (Stripe).

Written to Cashfree's documented API (docs.cashfree.com, Orders + Subscriptions, API version 2026-01-01)
and must be exercised against their real sandbox before trusting it blindly -- two things in particular
are inferred from REST convention rather than confirmed in their docs:
  - subscription_status(): GET /subscriptions/{id}, matching their GET /orders/{id} pattern.
  - saved_payment_instrument(): what a subscription's authorization_details actually contains once a
    mandate is live; Cashfree has no "list payment methods for a customer" endpoint the way Stripe does.

Three real differences from Stripe worth knowing before touching the router/frontend:
  1. No plain checkout URL. Cashfree's hosted checkout is a session id (payment_session_id /
     subscription_session_id) that the *frontend* hands to Cashfree's own JS SDK
     (cashfree.checkout() / cashfree.subscriptionsCheckout()) -- there is nothing to redirect to
     server-side. See scriptliv_web/lib/cashfree.ts.
  2. No customer object and no metadata field on orders/subscriptions. The user id and purchase kind
     are encoded directly into the order_id / subscription_id this module generates, and parsed back
     out of those same ids when a webhook arrives -- not read from a metadata dict.
  3. No separate webhook signing secret. Confirmed against Cashfree's own docs: webhook signatures use
     the SAME secret key as API auth (HMAC-SHA256 of `timestamp + raw_body`, base64-encoded, compared to
     the x-webhook-signature header). Stripe issues a distinct secret per endpoint; Cashfree does not.
"""
import base64
import hashlib
import hmac
import secrets

import httpx

from .config import get_settings
from .plans import with_gst

API_VERSION = "2026-01-01"


class NotConfigured(Exception):
    pass


def configured() -> bool:
    s = get_settings()
    return bool(s.cashfree_app_id and s.cashfree_secret_key)


def _base_url() -> str:
    return "https://api.cashfree.com/pg" if get_settings().cashfree_live else "https://sandbox.cashfree.com/pg"


def _headers() -> dict:
    s = get_settings()
    return {
        "x-api-version": API_VERSION,
        "x-client-id": s.cashfree_app_id,
        "x-client-secret": s.cashfree_secret_key,
        "Content-Type": "application/json",
    }


def _post(path: str, body: dict) -> dict:
    if not configured():
        raise NotConfigured()
    r = httpx.post(f"{_base_url()}{path}", json=body, headers=_headers(), timeout=20)
    r.raise_for_status()
    return r.json()


def _get(path: str) -> dict:
    if not configured():
        raise NotConfigured()
    r = httpx.get(f"{_base_url()}{path}", headers=_headers(), timeout=20)
    r.raise_for_status()
    return r.json()


def _new_reference(prefix: str, user_id: str) -> str:
    # user_id is embedded directly (not hashed/opaque) so the webhook handler can parse it back out
    # without a metadata lookup; Cashfree ids allow alphanumeric + . - _, same charset as a Mongo ObjectId hex string.
    return f"{prefix}-{user_id}-{secrets.token_hex(6)}"


def parse_reference(reference_id: str) -> tuple[str, str] | None:
    """Reverses _new_reference(): 'addon-<user_id>-<rand>' -> ('addon', user_id). None if it doesn't match."""
    parts = reference_id.split("-")
    if len(parts) < 3 or parts[0] not in ("addon", "pro"):
        return None
    return parts[0], "-".join(parts[1:-1])


_PLAN_ENSURED = False


def _pro_plan_id() -> str:
    """Derives the Cashfree plan id from the actual GST-inclusive amount, so a price or GST-rate change
    always creates a fresh plan instead of silently reusing a stale one that still has the old amount
    baked in (Cashfree plans aren't known to support an in-place price update)."""
    from . import plans as _plans
    amount_paise = int(round(with_gst(_plans.PLANS[_plans.PRO].price_inr_month) * 100))
    return f"{get_settings().cashfree_pro_plan_id}-{amount_paise}"


def _ensure_pro_plan() -> str:
    """Creates the Pro recurring plan on first use (idempotent: Cashfree's "plan already exists" error is
    swallowed). Done lazily rather than at import time so a missing/misconfigured secret key doesn't crash
    the whole API process on startup -- the actual purchase attempt is where that should surface. Returns
    the plan id to use."""
    global _PLAN_ENSURED
    plan_id = _pro_plan_id()
    if _PLAN_ENSURED == plan_id:
        return plan_id
    from . import plans as _plans
    amount = with_gst(_plans.PLANS[_plans.PRO].price_inr_month)
    try:
        _post("/plans", {
            "plan_id": plan_id,
            "plan_name": "ScriptLiv Pro",
            "plan_type": "PERIODIC",
            "plan_recurring_amount": amount,
            "plan_max_amount": amount,
            "plan_intervals": 1,
            "plan_interval_type": "MONTH",
            "plan_currency": "INR",
        })
    except httpx.HTTPStatusError as e:
        # Cashfree's exact "already exists" status/code is unverified; 400/409 both plausibly mean that,
        # but could also mean a real config error. If plan creation keeps silently failing, check this.
        if e.response.status_code not in (400, 409):
            raise
    _PLAN_ENSURED = plan_id
    return plan_id


def checkout_session(kind: str, user_id: str, email: str, name: str, phone: str | None) -> dict:
    """Starts a purchase. Returns {"kind": "order"|"subscription", "session_id": ..., "reference_id": ...}
    for the frontend to hand to Cashfree's JS SDK. kind is 'addon' (one-time Orders purchase) or 'pro'
    (recurring Subscriptions signup)."""
    from . import plans as _plans
    s = get_settings()
    base = s.app_base_url.rstrip("/")
    phone = phone or "9999999999"  # Cashfree requires a phone number; most test accounts have none on file
    if kind == "addon":
        order_id = _new_reference("addon", user_id)
        r = _post("/orders", {
            "order_id": order_id,
            "order_amount": with_gst(_plans.ADDON_PRICE_INR),
            "order_currency": "INR",
            "customer_details": {"customer_id": user_id, "customer_phone": phone, "customer_email": email},
            "order_meta": {
                "return_url": f"{base}/app/plans?billing=success",
                "notify_url": f"{base}/sl/v1/billing/webhook/cashfree",
            },
        })
        return {"kind": "order", "session_id": r["payment_session_id"], "reference_id": order_id}
    if kind == "pro":
        plan_id = _ensure_pro_plan()
        subscription_id = _new_reference("pro", user_id)
        r = _post("/subscriptions", {
            "subscription_id": subscription_id,
            "customer_details": {"customer_id": user_id, "customer_name": name, "customer_email": email, "customer_phone": phone},
            "plan_details": {"plan_id": plan_id},
            # authorization_details.authorization_amount is the token amount charged (and refunded) to set up
            # the mandate itself, separate from the recurring plan amount charged on each billing cycle.
            "authorization_details": {"authorization_amount": 1, "authorization_amount_refund": True, "payment_methods": ["upi", "cc", "dc"]},
            "subscription_meta": {"return_url": f"{base}/app/plans?billing=success"},
        })
        return {"kind": "subscription", "session_id": r["subscription_session_id"], "reference_id": subscription_id}
    raise ValueError(kind)


def cancel_subscription(subscription_id: str) -> None:
    _post(f"/subscriptions/{subscription_id}/manage", {"subscription_id": subscription_id, "action": "CANCEL", "action_details": {}})


def subscription_status(subscription_id: str) -> dict:
    """See module docstring: endpoint path inferred from REST convention, not confirmed in Cashfree's docs."""
    return _get(f"/subscriptions/{subscription_id}")


def verify_webhook(payload: bytes, signature: str, timestamp: str) -> bool:
    s = get_settings()
    if not s.cashfree_secret_key or not signature or not timestamp:
        return False
    expected = base64.b64encode(
        hmac.new(s.cashfree_secret_key.encode(), timestamp.encode() + payload, hashlib.sha256).digest()
    ).decode()
    return hmac.compare_digest(expected, signature)
