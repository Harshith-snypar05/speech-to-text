"""Security audit tests: account isolation, token security, billing authorization, internal/relay exposure."""
import base64
import json
import time

import jwt
import pytest

from tests.conftest import _register

R = {"X-Relay-Secret": "test-relay-secret"}


def _verified(client, email):
    u = _register(client, email)
    assert client.post("/v1/auth/verify-email", json={"token": u["verify"]["dev_token"]}).status_code == 200
    return u


@pytest.fixture
def two(client):
    return _verified(client, "a@example.com"), _verified(client, "b@example.com")


def _b64(d):
    return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()


# ---- token security -------------------------------------------------------------------------------------------------

def test_jwt_alg_none_and_wrong_secret_and_expired_rejected(client, user):
    uid = user["id"]
    none_tok = _b64({"alg": "none", "typ": "JWT"}) + "." + _b64({"sub": uid, "pwv": 1, "exp": int(time.time()) + 999, "typ": "access"}) + "."
    wrong = jwt.encode({"sub": uid, "pwv": 1, "exp": int(time.time()) + 999, "typ": "access"}, "z" * 40, algorithm="HS256")
    old = jwt.encode({"sub": uid, "pwv": 1, "exp": int(time.time()) - 5, "typ": "access"}, "test-jwt-secret-not-real-0123456789abcdef", algorithm="HS256")
    wrong_typ = jwt.encode({"sub": uid, "pwv": 1, "exp": int(time.time()) + 999, "typ": "refresh"}, "test-jwt-secret-not-real-0123456789abcdef", algorithm="HS256")
    for t in (none_tok, wrong, old, wrong_typ, "garbage", ""):
        assert client.get("/v1/me", headers={"Authorization": "Bearer " + t}).status_code == 401, t


def test_disabled_account_token_is_dead(client, user, db):
    from bson import ObjectId
    assert client.get("/v1/me", headers=user["h"]).status_code == 200
    db.users.update_one({"_id": ObjectId(user["id"])}, {"$set": {"disabled": True}})
    assert client.get("/v1/me", headers=user["h"]).status_code == 401


def test_verification_and_reset_tokens_are_not_session_tokens(client, user):
    """A mailed token must never authenticate API calls, and an access token must never verify/reset."""
    dev = client.post("/v1/auth/forgot-password", json={"email": "ann@example.com"}).json()["dev_token"]
    assert client.get("/v1/me", headers={"Authorization": "Bearer " + dev}).status_code == 401
    assert client.post("/v1/auth/reset-password", json={"token": user["token"], "new_password": "Brand-new-pass-9"}).status_code in (400, 422)
    assert client.post("/v1/auth/verify-email", json={"token": dev}).status_code == 400   # a reset token cannot verify email


def test_login_does_not_reveal_which_part_was_wrong(client, user):
    a = client.post("/v1/auth/login", json={"email": "ann@example.com", "password": "wrong-wrong-1"})
    b = client.post("/v1/auth/login", json={"email": "nobody@example.com", "password": "wrong-wrong-1"})
    assert a.status_code == b.status_code == 401 and a.json() == b.json()


# ---- account isolation ----------------------------------------------------------------------------------------------

def test_usage_billing_and_settings_are_per_account(client, two, db):
    a, b = two
    client.post("/internal/v1/sessions/start", headers=R, json={"token": a["token"], "session_id": "sess-a1"})
    client.post("/internal/v1/usage", headers=R, json={"user_id": a["id"], "session_id": "sess-a1", "cumulative_seconds": 30, "final": True})
    assert client.get("/v1/usage", headers=a["h"]).json()["included_used_seconds"] == 30
    assert client.get("/v1/usage", headers=b["h"]).json()["included_used_seconds"] == 0
    assert client.get("/v1/usage/sessions", headers=b["h"]).json()["sessions"] == []
    # B cannot read A's per-minute breakdown, or learn that the session exists
    r = client.get("/v1/usage/sessions/sess-a1/minutes", headers=b["h"])
    assert r.status_code in (404,) or r.json().get("minutes") in ([], None), r.text
    client.put("/v1/settings", headers=a["h"], json={"personal_limit_minutes": 5})
    assert client.get("/v1/settings", headers=b["h"]).json()["settings"].get("personal_limit_minutes") != 5


def test_cannot_rename_unshare_or_read_transcript_of_other_users_session(client, two, db):
    a, b = two
    client.post("/internal/v1/sessions/start", headers=R, json={"token": a["token"], "session_id": "sess-a1"})
    db.transcript_events.insert_one({"session_id": "sess-a1", "seq": 1, "text": "secret words"})
    tok = client.post("/v1/sessions/sess-a1/share", headers=a["h"]).json()["share_url"].rsplit("/", 1)[1]
    assert client.patch("/v1/sessions/sess-a1", headers=b["h"], json={"title": "pwned"}).status_code == 404
    assert client.delete("/v1/sessions/sess-a1/share", headers=b["h"]).status_code == 404
    assert client.get("/v1/sessions/sess-a1", headers=b["h"]).status_code == 404
    assert "secret words" not in client.get("/v1/sessions", headers=b["h"]).text
    assert client.get(f"/v1/shared/{tok}").status_code == 200          # still shared; B's attempt changed nothing
    assert db.sessions.find_one({"session_id": "sess-a1"}).get("title") != "pwned"


def test_relay_start_cannot_hijack_other_accounts_session_id(client, two):
    a, b = two
    assert client.post("/internal/v1/sessions/start", headers=R, json={"token": a["token"], "session_id": "sess-a1"}).json()["allowed"]
    r = client.post("/internal/v1/sessions/start", headers=R, json={"token": b["token"], "session_id": "sess-a1"}).json()
    assert r["allowed"] is False and r["reason"] == "session_taken"


def test_relay_usage_cannot_bill_a_session_owned_by_someone_else(client, two, db):
    a, b = two
    client.post("/internal/v1/sessions/start", headers=R, json={"token": a["token"], "session_id": "sess-a1"})
    client.post("/internal/v1/usage", headers=R, json={"user_id": b["id"], "session_id": "sess-a1", "cumulative_seconds": 50})
    assert client.get("/v1/usage", headers=b["h"]).json()["included_used_seconds"] == 0
    assert client.get("/v1/usage", headers=a["h"]).json()["included_used_seconds"] == 0


# ---- share links ----------------------------------------------------------------------------------------------------

def test_share_token_is_unguessable_and_view_leaks_nothing_private(client, user, db):
    client.post("/internal/v1/sessions/start", headers=R, json={"token": user["token"], "session_id": "sess-01"})
    t1 = client.post("/v1/sessions/sess-01/share", headers=user["h"]).json()["share_url"].rsplit("/", 1)[1]
    client.delete("/v1/sessions/sess-01/share", headers=user["h"])
    t2 = client.post("/v1/sessions/sess-01/share", headers=user["h"]).json()["share_url"].rsplit("/", 1)[1]
    assert t1 != t2 and len(t2) >= 20                                      # revoked link never comes back; enough entropy
    assert client.get(f"/v1/shared/{t1}").status_code == 404
    body = client.get(f"/v1/shared/{t2}").text
    for private in (user["id"], "ann@example.com", "pwhash", "owner_id", "email"):
        assert private not in body
    # the public endpoint takes no state-changing verbs
    assert client.delete(f"/v1/shared/{t2}").status_code == 405
    assert client.post(f"/v1/shared/{t2}").status_code == 405


# ---- billing authorization ------------------------------------------------------------------------------------------

def test_billing_endpoints_need_auth_and_act_only_on_own_subscription(client, two, db):
    a, b = two
    for method, path in (("get", "/v1/subscription"), ("post", "/v1/billing/portal"), ("post", "/v1/billing/retry-payment"),
                         ("post", "/v1/subscription/cancel"), ("get", "/v1/billing/payments"), ("put", "/v1/billing/details")):
        assert getattr(client, method)(path).status_code == 401, path
    # B has no provider billing account of their own: nothing to retry, and A's customer id is never reachable
    db.subscriptions.update_one({"user_id": a["id"]}, {"$set": {"plan": "pro", "status": "past_due", "provider_customer_id": "cus_A"}}, upsert=True)
    r = client.post("/v1/billing/retry-payment", headers=b["h"])
    assert r.status_code == 409
    assert client.post("/v1/billing/portal", headers=b["h"]).status_code == 404
    assert "cus_A" not in client.get("/v1/subscription", headers=b["h"]).text


def test_retry_click_never_activates_without_provider_confirmation(client, user, db, monkeypatch):
    from app import payments
    db.subscriptions.update_one({"user_id": user["id"]}, {"$set": {"plan": "pro", "status": "past_due", "provider_customer_id": "cus_X",
                                                                    "payment_failed_count": 1}}, upsert=True)
    monkeypatch.setattr(payments, "retry_invoice", lambda cid: {"paid": False, "declined": True, "status": "open"})
    assert client.post("/v1/billing/retry-payment", headers=user["h"]).status_code == 402
    assert db.subscriptions.find_one({"user_id": user["id"]})["status"] == "past_due"


# ---- internal / relay surface ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("secret", [None, "", "wrong", "test-relay-secre", "test-relay-secret "])
def test_internal_endpoints_reject_missing_or_near_miss_secret(client, user, secret):
    h = {} if secret is None else {"X-Relay-Secret": secret}
    assert client.post("/internal/v1/sessions/start", headers=h, json={"token": user["token"], "session_id": "sess-01"}).status_code == 403
    assert client.post("/internal/v1/usage", headers=h, json={"user_id": user["id"], "session_id": "sess-01", "cumulative_seconds": 1}).status_code == 403


def test_internal_endpoints_closed_when_relay_secret_unset(client, user, monkeypatch):
    monkeypatch.setenv("SCRIPTLIV_RELAY_SECRET", "")
    assert client.post("/internal/v1/sessions/start", headers={"X-Relay-Secret": ""}, json={"token": user["token"], "session_id": "sess-01"}).status_code == 403


def test_cors_is_never_wildcard_and_credentials_off():
    from app.main import app
    from app.config import get_settings
    assert "*" not in get_settings().cors_origins
    cors = [m for m in app.user_middleware if m.cls.__name__ == "CORSMiddleware"][0]
    assert cors.kwargs["allow_credentials"] is False


def test_api_docs_disabled_unless_enabled(monkeypatch):
    """Interactive docs / openapi.json describe every route; staging/production must not publish them by default."""
    from app.main import app
    assert app.docs_url is None and app.openapi_url is None


def test_errors_do_not_leak_internals(client, user):
    r = client.get("/v1/sessions/%00", headers=user["h"])
    assert "Traceback" not in r.text and "pymongo" not in r.text.lower()
    r = client.post("/v1/auth/login", content=b"{not json", headers={"Content-Type": "application/json"})
    assert r.status_code == 422 and "Traceback" not in r.text
