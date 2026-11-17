"""Invoice email: amounts add up, the mail goes out once per recorded payment, and a mail failure never fails the webhook."""
import time

import pytest

from app import email_providers as ep
from app import invoice
from app.plans import PRO, PLANS, with_gst
from app.routers import billing


def _event(uid, sid="sub1", cf="CF-1"):
    return {"type": "SUBSCRIPTION_PAYMENT_SUCCESS", "data": {
        "subscription_details": {"subscription_id": f"pro-{uid}-{sid}", "cf_subscription_id": cf},
        "payment_amount": with_gst(PLANS[PRO].price_inr_month)}}


@pytest.fixture
def outbox(monkeypatch):
    sent = []

    def fake_deliver(m, sleep=None):
        sent.append(m)
        return ep.Sent("test", "id-1"), 1, None
    monkeypatch.setattr(ep, "deliver", fake_deliver)
    return sent


def test_gst_split_adds_up():
    net, gst = invoice.split_gst(1178.82)
    assert (net, gst) == (999.0, 179.82)
    assert round(net + gst, 2) == 1178.82


def test_render_contains_amounts_and_escapes(db):
    now = time.time()
    user = {"email": "a@example.com", "name": "<b>Ann</b>"}
    pay = {"amount_cents": 117882, "description": "ScriptLiv Pro", "created_at": now, "currency": "inr", "provider_ref": "REF-1"}
    inv = invoice.build(user, pay, {"period_start": now, "period_end": now + 86400 * 30})
    html, text = invoice.render_html(inv), invoice.render_text(inv)
    assert "₹1,178.82" in html and "₹179.82" in html and "₹999.00" in html and "REF-1" in html
    assert "<b>Ann</b>" not in html and "&lt;b&gt;Ann&lt;/b&gt;" in html
    assert "Total paid: ₹1,178.82" in text


def test_webhook_payment_sends_one_invoice(db, user, outbox):
    billing._apply_cashfree_event(db, _event(user["id"]))
    assert len(outbox) == 1
    m = outbox[0]
    assert m.to == "ann@example.com" and "SL-" in m.subject and m.html and "₹1,178.82" in m.html
    assert db.email_deliveries.count_documents({"kind": "invoice", "status": "sent"}) == 1
    billing._apply_cashfree_event(db, _event(user["id"]))     # same provider reference delivered again
    assert len(outbox) == 1


def test_mail_failure_does_not_break_payment(db, user, monkeypatch):
    monkeypatch.setattr(ep, "deliver", lambda m, sleep=None: (None, 3, "boom"))
    billing._apply_cashfree_event(db, _event(user["id"]))
    assert db.subscriptions.find_one({"user_id": user["id"]})["plan"] == PRO
    assert db.payments.count_documents({"user_id": user["id"], "status": "paid"}) == 1
    assert db.email_deliveries.find_one({"kind": "invoice"})["status"] == "failed"
