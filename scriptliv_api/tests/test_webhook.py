"""Stripe webhook: signature, replay window, idempotency, failure handling. Uses a test signing secret only; no provider contact."""
import hashlib
import hmac
import json
import time

SECRET = "whsec_test_only"


def _signed(payload: dict, secret=SECRET, t=None):
    body = json.dumps(payload).encode()
    t = str(int(t or time.time()))
    sig = hmac.new(secret.encode(), t.encode() + b"." + body, hashlib.sha256).hexdigest()
    return body, {"Stripe-Signature": f"t={t},v1={sig}", "Content-Type": "application/json"}


def _post(client, payload, **kw):
    body, h = _signed(payload, **kw)
    return client.post("/v1/billing/webhook", content=body, headers=h)


def _addon_event(uid, eid="evt_1", intent="pi_1", status="paid"):
    return {"id": eid, "type": "checkout.session.completed", "data": {"object": {
        "id": "cs_1", "payment_status": status, "payment_intent": intent, "amount_total": 1000, "currency": "usd",
        "metadata": {"user_id": uid, "kind": "addon"}}}}


def test_bad_old_and_missing_signature_rejected(client, user, db, monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", SECRET)
    ev = _addon_event(user["id"])
    assert _post(client, ev, secret="wrong").status_code == 400
    assert _post(client, ev, t=time.time() - 3600).status_code == 400  # replayed old request
    assert client.post("/v1/billing/webhook", content=json.dumps(ev)).status_code == 400
    assert db.addons.count_documents({}) == 0 and db.payments.count_documents({}) == 0


def test_no_secret_configured_rejects_everything(client, user, db):
    assert _post(client, _addon_event(user["id"])).status_code == 400
    assert db.addons.count_documents({}) == 0


def test_duplicate_event_and_same_payment_grant_addon_once(client, user, db, monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", SECRET)
    assert _post(client, _addon_event(user["id"])).status_code == 200
    assert _post(client, _addon_event(user["id"])).json().get("duplicate") is True
    # same payment redelivered under a new event id: still no second add-on
    assert _post(client, _addon_event(user["id"], eid="evt_2")).status_code == 200
    assert db.addons.count_documents({}) == 1 and db.payments.count_documents({}) == 1


def test_unpaid_checkout_creates_nothing(client, user, db, monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", SECRET)
    assert _post(client, _addon_event(user["id"], status="unpaid")).status_code == 200
    pro = {"id": "evt_p", "type": "checkout.session.completed", "data": {"object": {
        "payment_status": "unpaid", "customer": "cus_1", "subscription": "sub_1", "metadata": {"user_id": user["id"], "kind": "pro"}}}}
    assert _post(client, pro).status_code == 200
    assert db.addons.count_documents({}) == 0 and db.payments.count_documents({}) == 0
    assert db.subscriptions.find_one({"user_id": user["id"]})["plan"] == "basic"


def test_failed_invoice_is_recorded_not_activated(client, user, db, monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", SECRET)
    client.get("/v1/subscription", headers=user["h"])  # makes sure the subscription row exists
    db.subscriptions.update_one({"user_id": user["id"]}, {"$set": {"provider_customer_id": "cus_1"}})
    ev = {"id": "evt_f", "type": "invoice.payment_failed", "data": {"object": {"id": "in_1", "customer": "cus_1", "amount_due": 2000, "currency": "usd"}}}
    assert _post(client, ev).status_code == 200
    assert db.payments.find_one({})["status"] == "failed"
    assert db.subscriptions.find_one({"user_id": user["id"]})["plan"] == "basic"


def test_failed_processing_releases_event_so_retry_applies(client, user, db, monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", SECRET)
    from app import subscriptions
    real = subscriptions.grant_addon

    def boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(subscriptions, "grant_addon", boom)
    assert _post(client, _addon_event(user["id"])).status_code == 500
    assert db.provider_events.count_documents({}) == 0 and db.payments.count_documents({}) == 0
    monkeypatch.setattr(subscriptions, "grant_addon", real)
    assert _post(client, _addon_event(user["id"])).status_code == 200
    assert db.addons.count_documents({}) == 1
