"""Payment failure flow: past_due while the provider retries, restricted after the configured retries, restored only by a
provider-confirmed payment (webhook or the provider's authenticated answer to a retry). Signed with a test secret; the
provider is never contacted (payments.retry_invoice is replaced by a stub), so none of this proves live Stripe behaviour."""
import json
import time

from app import payments, usage

from .test_webhook import SECRET, _post

R = {"X-Relay-Secret": "test-relay-secret"}
BASIC_S = 300 * 60


def _pro(client, user, db, monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", SECRET)
    client.get("/v1/subscription", headers=user["h"])
    from app import subscriptions
    subscriptions.activate_pro(db, user["id"], provider="stripe", customer_id="cus_1", subscription_id="sub_1")


def _failed(n, nxt, eid, created=None):
    return {"id": eid, "type": "invoice.payment_failed", "created": created or int(time.time()),
            "data": {"object": {"id": f"in_{eid}", "customer": "cus_1", "amount_due": 2000, "currency": "usd",
                                "attempt_count": n, "next_payment_attempt": nxt}}}


def _paid(eid, created=None):
    return {"id": eid, "type": "invoice.paid", "created": created or int(time.time()),
            "data": {"object": {"id": f"in_{eid}", "customer": "cus_1", "amount_paid": 2000, "currency": "usd"}}}


def _sub(client, user):
    return client.get("/v1/subscription", headers=user["h"]).json()["subscription"]


def test_first_failures_are_past_due_and_access_is_kept(client, user, db, monkeypatch):
    _pro(client, user, db, monkeypatch)
    assert _post(client, _failed(1, int(time.time()) + 86400, "e1")).status_code == 200
    s = _sub(client, user)
    assert s["status"] == "past_due" and s["payment"]["access_restricted"] is False
    assert s["payment"]["failed_attempts"] == 1 and s["payment"]["max_retries"] == 3 and s["payment"]["can_retry"]
    assert "payment method" in s["payment"]["message"]
    assert usage.summary(db, user["id"])["total_remaining_seconds"] > BASIC_S   # still the paid allowance


def test_final_failure_restricts_paid_access_but_keeps_account_history_and_billing(client, user, db, monkeypatch):
    _pro(client, user, db, monkeypatch)
    db.addons.insert_one({"user_id": user["id"], "seconds_total": 60000, "seconds_used": 0.0, "purchased_at": 1, "expires_at": time.time() + 9e6, "payment_id": "p"})
    t = int(time.time())
    for i, nxt in enumerate((t + 100, t + 200, None), 1):
        _post(client, _failed(i, nxt, f"e{i}", t + i))
    s = _sub(client, user)
    assert s["status"] == "restricted" and s["payment"]["access_restricted"] is True
    assert "Payment required" in s["payment"]["message"]
    u = client.get("/v1/usage", headers=user["h"]).json()
    assert u["restricted"] is True and u["total_remaining_seconds"] == BASIC_S and u["addon_remaining_seconds"] == 0
    # account, history and billing pages keep working
    assert client.get("/v1/me", headers=user["h"]).status_code == 200
    assert client.get("/v1/sessions", headers=user["h"]).status_code == 200
    assert client.get("/v1/billing/payments", headers=user["h"]).status_code == 200
    assert client.get("/v1/billing/details", headers=user["h"]).status_code == 200
    assert db.subscriptions.count_documents({"user_id": user["id"]}) == 1 and db.addons.count_documents({"user_id": user["id"]}) == 1


def test_restricted_new_session_gets_free_allowance_then_payment_required(client, user, db, monkeypatch):
    _pro(client, user, db, monkeypatch)
    _post(client, _failed(3, None, "e3"))
    ok = client.post("/internal/v1/sessions/start", headers=R, json={"token": user["token"], "session_id": "sess-01"}).json()
    assert ok["allowed"] and ok["remaining_seconds"] <= BASIC_S      # not the 2,500 Pro minutes
    db.subscriptions.update_one({"user_id": user["id"]}, {"$set": {"included_used_seconds": BASIC_S}})
    no = client.post("/internal/v1/sessions/start", headers=R, json={"token": user["token"], "session_id": "sess-02"}).json()
    assert no["allowed"] is False and no["reason"] == "payment_required"
    # add-ons cannot be bought into a restricted account
    c = client.post("/v1/billing/checkout", headers=user["h"], json={"kind": "addon"})
    assert c.status_code == 402 and c.json()["error"]["code"] == "payment_required"


def test_running_recording_is_not_cut_and_not_extended_by_a_temporary_failure(client, user, db, monkeypatch):
    _pro(client, user, db, monkeypatch)
    a = client.post("/internal/v1/sessions/start", headers=R, json={"token": user["token"], "session_id": "sess-01"}).json()
    _post(client, _failed(1, int(time.time()) + 86400, "e1"))                                    # past_due mid-recording
    r = client.post("/internal/v1/usage", headers=R, json={"user_id": user["id"], "session_id": "sess-01", "cumulative_seconds": 30}).json()
    assert a["allowed"] and r["allowed"] is True             # a temporary provider failure does not interrupt the recording
    assert r["base_seconds"] + r["remaining_seconds"] <= 2500 * 60   # and the ceiling is still only what the plan funds
    _post(client, _failed(3, None, "e3", int(time.time()) + 5))                                   # restricted mid-recording
    r = client.post("/internal/v1/usage", headers=R, json={"user_id": user["id"], "session_id": "sess-01", "cumulative_seconds": 60}).json()
    assert r["allowed"] is True                    # not interrupted ...
    assert r["base_seconds"] + r["remaining_seconds"] <= BASIC_S      # ... and never beyond the (now free) allowance


def test_retry_click_alone_never_restores_access(client, user, db, monkeypatch):
    _pro(client, user, db, monkeypatch)
    _post(client, _failed(3, None, "e3"))
    monkeypatch.setattr(payments, "configured", lambda: True)
    monkeypatch.setattr(payments, "retry_invoice", lambda cid: {"paid": False, "declined": True, "status": "declined"})
    r = client.post("/v1/billing/retry-payment", headers=user["h"])
    assert r.status_code == 402 and r.json()["error"]["code"] == "payment_failed"
    assert _sub(client, user)["status"] == "restricted"


def test_retry_cooldown_and_provider_down_change_nothing(client, user, db, monkeypatch):
    _pro(client, user, db, monkeypatch)
    _post(client, _failed(1, int(time.time()) + 86400, "e1"))
    calls = []
    def boom(cid):
        calls.append(cid)
        raise RuntimeError("provider down")
    monkeypatch.setattr(payments, "retry_invoice", boom)
    r = client.post("/v1/billing/retry-payment", headers=user["h"])
    assert r.status_code == 502 and _sub(client, user)["status"] == "past_due"
    r2 = client.post("/v1/billing/retry-payment", headers=user["h"])      # immediately again: cooldown, provider not hit
    assert r2.status_code == 429 and r2.json()["error"]["code"] == "retry_too_soon" and len(calls) == 1


def test_provider_confirmed_retry_restores_access(client, user, db, monkeypatch):
    _pro(client, user, db, monkeypatch)
    _post(client, _failed(3, None, "e3"))
    monkeypatch.setattr(payments, "retry_invoice", lambda cid: {"paid": True, "declined": False, "status": "paid"})
    r = client.post("/v1/billing/retry-payment", headers=user["h"])
    assert r.status_code == 200 and r.json()["result"] == "paid"
    s = _sub(client, user)
    assert s["status"] == "active" and s["payment"] is None
    assert usage.summary(db, user["id"])["total_remaining_seconds"] > BASIC_S


def test_paid_webhook_restores_access_and_stale_failure_does_not_undo_it(client, user, db, monkeypatch):
    _pro(client, user, db, monkeypatch)
    t = int(time.time())
    _post(client, _failed(3, None, "e3", t))
    _post(client, _paid("p1", t + 10))
    assert _sub(client, user)["status"] == "active"
    _post(client, _failed(3, None, "e_old", t + 5))     # an older failure delivered late
    assert _sub(client, user)["status"] == "active"


def test_nothing_to_retry_when_paid_or_basic(client, user, db, monkeypatch):
    r = client.post("/v1/billing/retry-payment", headers=user["h"])
    assert r.status_code == 409 and r.json()["error"]["code"] == "nothing_to_retry"


def test_retry_settings_are_configurable(client, user, db, monkeypatch):
    monkeypatch.setenv("SCRIPTLIV_PAYMENT_MAX_RETRIES", "5")
    monkeypatch.setenv("SCRIPTLIV_PAYMENT_FINAL_STATUS", "canceled")
    from app import config
    config.get_settings.cache_clear() if hasattr(config.get_settings, "cache_clear") else None
    _pro(client, user, db, monkeypatch)
    _post(client, _failed(4, int(time.time()) + 100, "e4"))      # 4 < 5 and the provider still has a retry scheduled
    assert _sub(client, user)["status"] == "past_due"
    _post(client, _failed(5, int(time.time()) + 100, "e5", int(time.time()) + 3))
    assert _sub(client, user)["status"] == "canceled"
    assert usage.summary(db, user["id"])["restricted"] is True
