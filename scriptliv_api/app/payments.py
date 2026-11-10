"""Payment provider adapter (Stripe over HTTPS). Nothing is simulated: with keys missing every call raises
NotConfigured and the API returns 503 `payments_not_configured`; the UIs then show purchasing as unavailable.

NOTE: this adapter has not been exercised against live Stripe (no keys exist in this environment). It is written
to Stripe's documented Checkout / Billing Portal / webhook-signature behaviour and must be verified with test keys.
"""
import hashlib
import hmac
import time

import httpx

from .config import get_settings

API = "https://api.stripe.com/v1"


class NotConfigured(Exception):
    pass


def configured() -> bool:
    s = get_settings()
    return bool(s.stripe_secret_key and s.stripe_pro_price_id and s.stripe_addon_price_id and s.stripe_webhook_secret)


def _post(path: str, data: dict) -> dict:
    s = get_settings()
    if not configured():
        raise NotConfigured()
    r = httpx.post(f"{API}{path}", data=data, auth=(s.stripe_secret_key, ""), timeout=20)
    r.raise_for_status()
    return r.json()


def _get(path: str, params: dict | None = None) -> dict:
    s = get_settings()
    if not configured():
        raise NotConfigured()
    r = httpx.get(f"{API}{path}", params=params, auth=(s.stripe_secret_key, ""), timeout=20)
    r.raise_for_status()
    return r.json()


def checkout_url(kind: str, user_id: str, email: str, customer_id: str | None) -> str:
    """kind: 'pro' (subscription) or 'addon' (one-time). Plans are activated only by the webhook, never by the redirect."""
    s = get_settings()
    base = s.app_base_url.rstrip("/")
    data = {
        "mode": "subscription" if kind == "pro" else "payment",
        "line_items[0][price]": s.stripe_pro_price_id if kind == "pro" else s.stripe_addon_price_id,
        "line_items[0][quantity]": "1",
        "success_url": f"{base}/app/settings?billing=success",
        "cancel_url": f"{base}/app/settings?billing=cancelled",
        "client_reference_id": user_id,
        "metadata[user_id]": user_id,
        "metadata[kind]": kind,
    }
    if customer_id:
        data["customer"] = customer_id
    else:
        data["customer_email"] = email
    return _post("/checkout/sessions", data)["url"]


def portal_url(customer_id: str) -> str:
    base = get_settings().app_base_url.rstrip("/")
    return _post("/billing_portal/sessions", {"customer": customer_id, "return_url": f"{base}/app/settings"})["url"]


def cancel_at_period_end(subscription_id: str, value: bool) -> None:
    _post(f"/subscriptions/{subscription_id}", {"cancel_at_period_end": "true" if value else "false"})


def payment_method(customer_id: str) -> dict | None:
    pms = _get("/payment_methods", {"customer": customer_id, "type": "card", "limit": 1}).get("data", [])
    if not pms:
        return None
    c = pms[0]["card"]
    return {"brand": c["brand"], "last4": c["last4"], "exp_month": c["exp_month"], "exp_year": c["exp_year"]}


def retry_invoice(customer_id: str) -> dict:
    """Ask the provider to charge the customer's oldest open invoice again. The answer comes from the provider's own
    authenticated response (never from the client): {'paid': bool, 'declined': bool, 'status': str}."""
    s = get_settings()
    if not configured():
        raise NotConfigured()
    invs = _get("/invoices", {"customer": customer_id, "status": "open", "limit": 1}).get("data", [])
    if not invs:
        return {"paid": False, "declined": False, "status": "no_open_invoice"}
    r = httpx.post(f"{API}/invoices/{invs[0]['id']}/pay", data={}, auth=(s.stripe_secret_key, ""), timeout=20)
    if r.status_code == 402:   # the card was declined
        return {"paid": False, "declined": True, "status": "declined"}
    r.raise_for_status()
    status = r.json().get("status")
    return {"paid": status == "paid", "declined": False, "status": status}


def verify_webhook(payload: bytes, sig_header: str, tolerance: int = 300) -> bool:
    secret = get_settings().stripe_webhook_secret
    if not secret or not sig_header:
        return False
    parts = dict(p.split("=", 1) for p in sig_header.split(",") if "=" in p)
    t = parts.get("t")
    if not t or not t.isdigit() or abs(time.time() - int(t)) > tolerance:
        return False
    expect = hmac.new(secret.encode(), f"{t}.".encode() + payload, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expect, v) for k, v in (p.split("=", 1) for p in sig_header.split(",") if "=" in p) if k == "v1")
