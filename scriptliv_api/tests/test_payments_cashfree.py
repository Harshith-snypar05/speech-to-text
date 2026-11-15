"""Unit tests for the Cashfree adapter in isolation: reference-id encode/decode, webhook signature
verification, and configured()/NotConfigured gating. httpx.post/get are stubbed -- real sandbox calls
are a separate, manual verification step (see payments_cashfree.py's module docstring), not something
this suite can prove on its own."""
import base64
import hashlib
import hmac

import httpx
import pytest

from app import payments_cashfree as cf

APP_ID, SECRET = "TEST-app-id", "test-secret-key"


def _resp(status, json_body):
    # real httpx.post() attaches a request to its response automatically, which raise_for_status() needs;
    # a bare httpx.Response(...) built by hand in a test stub does not, so it's attached here instead.
    return httpx.Response(status, json=json_body, request=httpx.Request("POST", "https://sandbox.cashfree.com/pg/x"))


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("CASHFREE_TEST_APP_ID", APP_ID)
    monkeypatch.setenv("CASHFREE_SECRET_KEY", SECRET)
    cf._PLAN_ENSURED = False  # each test gets a clean slate for the lazy plan-creation flag
    yield


def test_not_configured_by_default():
    assert cf.configured() is False


def test_configured_once_both_keys_are_set(configured):
    assert cf.configured() is True


def test_reference_id_round_trips_kind_and_user_id():
    ref = cf._new_reference("addon", "65f0c1a2b3d4e5f6a7b8c9d0")
    assert cf.parse_reference(ref) == ("addon", "65f0c1a2b3d4e5f6a7b8c9d0")


def test_parse_reference_rejects_unknown_shapes():
    assert cf.parse_reference("not-a-reference") is None
    assert cf.parse_reference("unknown-kind-userid-abc123") is None


def test_checkout_session_raises_not_configured_without_keys():
    with pytest.raises(cf.NotConfigured):
        cf.checkout_session("addon", "user1", "a@example.com", "Ann", None)


def test_checkout_session_addon_posts_to_orders_and_returns_session(configured, monkeypatch):
    captured = {}

    def fake_post(url, json, headers, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return _resp(200, {"payment_session_id": "session_abc", "cf_order_id": "1", "order_status": "ACTIVE"})

    monkeypatch.setattr(httpx, "post", fake_post)
    r = cf.checkout_session("addon", "user1", "a@example.com", "Ann", "9876543210")

    assert r == {"kind": "order", "session_id": "session_abc", "reference_id": captured["json"]["order_id"]}
    assert captured["url"].endswith("/orders")
    assert captured["headers"]["x-client-id"] == APP_ID
    assert captured["headers"]["x-client-secret"] == SECRET
    assert captured["headers"]["x-api-version"] == cf.API_VERSION
    assert captured["json"]["customer_details"]["customer_id"] == "user1"
    assert cf.parse_reference(captured["json"]["order_id"]) == ("addon", "user1")
    assert captured["json"]["order_amount"] == 706.82  # 599 base + 18% GST


def test_checkout_session_pro_creates_plan_then_subscription(configured, monkeypatch):
    calls = []

    def fake_post(url, json, headers, timeout):
        calls.append((url, json))
        if url.endswith("/plans"):
            return _resp(200, {"plan_id": json["plan_id"], "plan_status": "ACTIVE"})
        return _resp(200, {"subscription_session_id": "subs_session_xyz", "cf_subscription_id": "1"})

    monkeypatch.setattr(httpx, "post", fake_post)
    r = cf.checkout_session("pro", "user2", "b@example.com", "Bob", None)

    assert r["kind"] == "subscription"
    assert r["session_id"] == "subs_session_xyz"
    assert cf.parse_reference(r["reference_id"]) == ("pro", "user2")
    assert [c[0].rsplit("/", 1)[-1] for c in calls] == ["plans", "subscriptions"]
    # customer_name must be an actual person name -- Cashfree's sandbox 400s on an email/id there
    assert calls[-1][1]["customer_details"]["customer_name"] == "Bob"
    plan_call = next(c for c in calls if c[0].endswith("/plans"))
    assert plan_call[1]["plan_recurring_amount"] == 1178.82  # 999 base + 18% GST
    assert plan_call[1]["plan_id"].endswith("-117882")  # the GST-inclusive amount (in paise) is baked into the id
    # the plan is only ever created once per process -- a second "pro" checkout should skip straight to /subscriptions
    calls.clear()
    cf.checkout_session("pro", "user3", "c@example.com", "Cara", None)
    assert [c[0].rsplit("/", 1)[-1] for c in calls] == ["subscriptions"]


def test_checkout_session_pro_tolerates_plan_already_existing(configured, monkeypatch):
    def fake_post(url, json, headers, timeout):
        if url.endswith("/plans"):
            return _resp(409, {"message": "plan already exists"})
        return _resp(200, {"subscription_session_id": "s", "cf_subscription_id": "1"})

    monkeypatch.setattr(httpx, "post", fake_post)
    r = cf.checkout_session("pro", "user4", "d@example.com", "Dan", None)
    assert r["session_id"] == "s"


def test_checkout_session_rejects_unknown_kind(configured):
    with pytest.raises(ValueError):
        cf.checkout_session("enterprise", "user1", "a@example.com", "Ann", None)


def test_cancel_subscription_posts_manage_action(configured, monkeypatch):
    captured = {}

    def fake_post(url, json, headers, timeout):
        captured["url"] = url
        captured["json"] = json
        return _resp(200, {"subscription_status": "CANCELLED"})

    monkeypatch.setattr(httpx, "post", fake_post)
    cf.cancel_subscription("pro-user1-abcdef")
    assert captured["url"].endswith("/subscriptions/pro-user1-abcdef/manage")
    assert captured["json"] == {"subscription_id": "pro-user1-abcdef", "action": "CANCEL", "action_details": {}}


def _sign(secret, timestamp, payload):
    return base64.b64encode(hmac.new(secret.encode(), timestamp.encode() + payload, hashlib.sha256).digest()).decode()


def test_verify_webhook_accepts_a_correctly_signed_payload(configured):
    payload = b'{"type":"PAYMENT_SUCCESS_WEBHOOK"}'
    ts = "1700000000"
    assert cf.verify_webhook(payload, _sign(SECRET, ts, payload), ts) is True


def test_verify_webhook_rejects_a_tampered_payload(configured):
    ts = "1700000000"
    sig = _sign(SECRET, ts, b'{"type":"PAYMENT_SUCCESS_WEBHOOK"}')
    assert cf.verify_webhook(b'{"type":"SUBSCRIPTION_PAYMENT_SUCCESS"}', sig, ts) is False


def test_verify_webhook_rejects_a_mismatched_timestamp(configured):
    payload = b'{"type":"PAYMENT_SUCCESS_WEBHOOK"}'
    sig = _sign(SECRET, "1700000000", payload)
    assert cf.verify_webhook(payload, sig, "1700000001") is False


def test_verify_webhook_rejects_missing_secret():
    payload = b'{"type":"PAYMENT_SUCCESS_WEBHOOK"}'
    ts = "1700000000"
    assert cf.verify_webhook(payload, _sign(SECRET, ts, payload), ts) is False


def test_verify_webhook_rejects_empty_signature_or_timestamp(configured):
    payload = b"{}"
    assert cf.verify_webhook(payload, "", "1700000000") is False
    assert cf.verify_webhook(payload, "abc", "") is False
