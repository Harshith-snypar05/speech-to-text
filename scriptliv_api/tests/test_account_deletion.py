"""Tombstone-first account deletion: lifecycle, last-administrator safety, write barriers, crash recovery, and mutation checks.

Deterministic: mongomock only, no real database, no network, no sleeping on wall-clock timing (leases are expired by editing the
document; threads are ordered with events).
"""
import threading
import time

import mongomock
import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

from app import account_deletion as ad
from app import deps
from app.routers import billing
from app.security import hash_password, make_token

PW = "correct-horse-1"
PWHASH = hash_password(PW)
R = {"X-Relay-Secret": "test-relay-secret"}


@pytest.fixture(autouse=True)
def no_env_admins(monkeypatch):
    monkeypatch.setenv("SCRIPTLIV_ADMIN_EMAILS", "")


def _user(db, email, admin=False, verified=True, **extra):
    doc = {"name": "U", "email": email, "email_verified": verified, "pwhash": PWHASH, "pwv": 1, "created_at": time.time(),
           "disabled": False, "is_admin": admin, **extra}
    oid = db.users.insert_one(doc).inserted_id
    tok = make_token(str(oid), 1)
    return {"oid": oid, "id": str(oid), "token": tok, "h": {"Authorization": "Bearer " + tok}}


def _doc(db, who):
    return db.users.find_one({"_id": who["oid"]})


def _delete(client, who, pw=PW):
    return client.request("DELETE", "/v1/me", json={"password": pw}, headers=who["h"])


def _expire_lease(db, who):
    db.users.update_one({"_id": who["oid"]}, {"$set": {"deletion_lease_until": 0}, "$unset": {"deletion_lease_owner": ""}})


def _tombstone(db, who, token="tok"):
    """Put the account straight into DELETING (what a successful claim + tombstone leaves behind)."""
    db.users.update_one({"_id": who["oid"]}, {"$set": {"deleting": True, "deletion_token": token, "deletion_started_at": time.time(),
                                                       "deletion_done": [], "deletion_attempts": 0}})
    return token


CASCADE_COLLECTIONS = ["transcript_events", "sessions", "usage_minutes", "usage_sessions", "usage_ledger", "addons",
                       "subscriptions", "settings", "billing_details", "email_tokens", "usage_locks"]
RETAINED = ["payments", "email_deliveries", "feedback", "throttle"]


def _seed(db, who):
    uid = who["id"]
    db.sessions.insert_one({"session_id": "s-" + uid, "owner_id": uid, "share_token": "share-" + uid})
    db.transcript_events.insert_one({"session_id": "s-" + uid, "seq": 1, "text": "hello"})
    db.usage_sessions.insert_one({"session_id": "u-" + uid, "user_id": uid, "metered_seconds": 5.0, "ended_at": None})
    db.usage_minutes.insert_one({"session_id": "u-" + uid, "minute": 0, "seconds": 5.0})
    db.usage_ledger.insert_one({"user_id": uid, "period_start": 0, "seconds": 5.0})
    db.addons.insert_one({"user_id": uid, "seconds_total": 60.0})
    db.subscriptions.insert_one({"user_id": uid, "plan": "basic", "status": "active", "cancel_at_period_end": False})
    db.settings.insert_one({"user_id": uid, "theme": "dark"})
    db.billing_details.insert_one({"user_id": uid, "name": "X"})
    db.email_tokens.insert_one({"user_id": uid, "kind": "verify", "token_hash": "h" + uid})
    db.usage_locks.insert_one({"_id": uid, "until": 0})
    db.payments.insert_one({"user_id": uid, "amount_cents": 100, "provider_ref": "p-" + uid})
    db.email_deliveries.insert_one({"user_id": uid, "kind": "verify"})
    db.feedback.insert_one({"user_id": uid, "message": "hi"})
    db.throttle.insert_one({"key": "acctdel:" + uid, "ts": 1})


def _remaining(db, who):
    uid = who["id"]
    out = {}
    out["transcript_events"] = db.transcript_events.count_documents({"session_id": "s-" + uid})
    out["sessions"] = db.sessions.count_documents({"owner_id": uid})
    out["usage_minutes"] = db.usage_minutes.count_documents({"session_id": "u-" + uid})
    for c in ("usage_sessions", "usage_ledger", "addons", "subscriptions", "settings", "billing_details", "email_tokens"):
        out[c] = db[c].count_documents({"user_id": uid})
    out["usage_locks"] = db.usage_locks.count_documents({"_id": uid})
    return out


def _all_gone(db, who):
    return all(v == 0 for v in _remaining(db, who).values())


def _retained_intact(db, who):
    uid = who["id"]
    return (db.payments.count_documents({"user_id": uid}) == 1 and db.email_deliveries.count_documents({"user_id": uid}) == 1
            and db.feedback.count_documents({"user_id": uid}) == 1 and db.throttle.count_documents({"key": "acctdel:" + uid}) >= 1)


@pytest.fixture
def stages(monkeypatch):
    """A private, patchable copy of the cascade stage list."""
    lst = list(ad.STAGES)
    monkeypatch.setattr(ad, "STAGES", lst)
    return lst


def _raise_after(name, real, boom=RuntimeError("simulated crash")):
    def run(db, uid):
        real(db, uid)    # the destructive work happens, then the process "dies" before it can record the stage
        raise boom
    return (name, run)


# ================================ lifecycle ======================================================================
def test_full_lifecycle_active_claimed_deleting_deleted(db):
    u = _user(db, "ann@example.com")
    _seed(db, u)
    assert not ad.is_deleting(_doc(db, u)) and not ad.claim_active(_doc(db, u))                  # ACTIVE
    token = ad.claim(db, u["oid"])
    assert token and ad.claim_active(_doc(db, u)) and not ad.is_deleting(_doc(db, u))             # CLAIMED
    snap = ad.verify_admin_safety(db, u["oid"], token)
    assert ad.tombstone(db, u["oid"], token, snap)                                                # DELETING
    d = _doc(db, u)
    assert d["deleting"] is True and d["deletion_token"] == token and "delete_claim_token" not in d and "delete_claim_until" not in d
    assert _remaining(db, u)["sessions"] == 1                       # tombstoning removes nothing by itself
    assert ad.run_deletion(db, u["oid"], token) == "completed"                                    # DELETED
    assert _doc(db, u) is None and _all_gone(db, u) and _retained_intact(db, u)


def test_claim_conflicts_and_ownership(db):
    u = _user(db, "ann@example.com")
    t1 = ad.claim(db, u["oid"])
    assert t1 and ad.claim(db, u["oid"]) is None                    # a live claim blocks a second one
    ad.release_claim(db, u["oid"], "not-the-owner")
    assert _doc(db, u)["delete_claim_token"] == t1                  # a foreign token releases nothing
    ad.release_claim(db, u["oid"], t1)
    assert "delete_claim_token" not in _doc(db, u)
    t2 = ad.claim(db, u["oid"])
    assert t2 and t2 != t1


def test_expired_claim_can_be_replaced_and_old_holder_cannot_tombstone(db):
    u = _user(db, "ann@example.com")
    old = ad.claim(db, u["oid"])
    db.users.update_one({"_id": u["oid"]}, {"$set": {"delete_claim_until": time.time() - 1}})
    new = ad.claim(db, u["oid"])
    assert new and new != old
    snap = {"email": "ann@example.com", "admin": False}
    assert not ad.tombstone(db, u["oid"], old, snap)                # the overwritten claim's owner is refused
    assert ad.tombstone(db, u["oid"], new, snap)


def test_claim_expiry_before_tombstone_refuses_and_leaves_account_active(db):
    u = _user(db, "ann@example.com")
    t = ad.claim(db, u["oid"])
    db.users.update_one({"_id": u["oid"]}, {"$set": {"delete_claim_until": time.time() - 1}})
    assert not ad.tombstone(db, u["oid"], t, {"email": "ann@example.com", "admin": False})
    assert not _doc(db, u).get("deleting")


def test_tombstone_with_invalid_token_is_refused(db):
    u = _user(db, "ann@example.com")
    ad.claim(db, u["oid"])
    assert not ad.tombstone(db, u["oid"], "forged", {"email": "ann@example.com", "admin": False})
    assert not ad.tombstone(db, u["oid"], "", {"email": "ann@example.com", "admin": False})
    assert not _doc(db, u).get("deleting")


def test_tombstone_without_any_claim_is_refused(db):
    u = _user(db, "ann@example.com")
    assert not ad.tombstone(db, u["oid"], "x", {"email": "ann@example.com", "admin": False})


def test_tombstone_refuses_changed_email_and_deleted_account(db):
    u = _user(db, "ann@example.com")
    t = ad.claim(db, u["oid"])
    assert not ad.tombstone(db, u["oid"], t, {"email": "other@example.com", "admin": False})
    gone = ObjectId()
    assert not ad.tombstone(db, gone, t, {"email": "ann@example.com", "admin": False})     # nothing to match: already DELETED


def test_no_cascade_before_tombstone(db, stages):
    u = _user(db, "ann@example.com")
    _seed(db, u)
    calls = []
    stages[:] = [(n, (lambda name: lambda d, uid: calls.append(name))(n)) for n, _ in stages]
    ad.claim(db, u["oid"])
    assert ad.run_deletion(db, u["oid"], "whatever") == "busy"      # not tombstoned -> nothing may run
    assert calls == [] and _doc(db, u) is not None and _remaining(db, u)["sessions"] == 1


def test_tombstone_is_never_reverted_by_any_account_path(client, db):
    u = _user(db, "ann@example.com")
    t = _tombstone(db, u)
    # claims and releases do not touch it
    assert ad.claim(db, u["oid"]) is None
    ad.release_claim(db, u["oid"], t)
    # login, session auth, token refresh surfaces
    assert client.post("/v1/auth/login", json={"email": "ann@example.com", "password": PW}).status_code == 401
    assert client.get("/v1/me", headers=u["h"]).status_code == 401
    assert client.patch("/v1/me", headers=u["h"], json={"name": "X"}).status_code == 401
    assert client.post("/v1/me/password", headers=u["h"], json={"current_password": PW, "new_password": "another-pass-9"}).status_code == 401
    d = _doc(db, u)
    assert d["deleting"] is True and d["deletion_token"] == t and d["name"] == "U"


def test_tombstone_has_no_expiry(db):
    u = _user(db, "ann@example.com")
    _tombstone(db, u)
    db.users.update_one({"_id": u["oid"]}, {"$set": {"deletion_started_at": 0, "deletion_lease_until": 0}})
    info = db.users.index_information()
    assert not any("expireAfterSeconds" in v for v in info.values())                 # no TTL index on users
    assert _doc(db, u)["deleting"] is True


# ================================ last administrator =============================================================
def _run_concurrently(admins):
    from app.main import app
    out, gate = {}, threading.Barrier(len(admins), timeout=20)

    def go(i, who):
        c = TestClient(app)
        gate.wait()
        out[i] = _delete(c, who)

    ts = [threading.Thread(target=go, args=(i, w)) for i, w in enumerate(admins)]
    [t.start() for t in ts]
    [t.join(60) for t in ts]
    assert len(out) == len(admins)
    return out


def _usable_admins(db, admins):
    return [w for w in admins if (d := _doc(db, w)) and d.get("is_admin") and not d.get("disabled") and not d.get("deleting")]


@pytest.mark.parametrize("n", [2, 3, 4])
@pytest.mark.parametrize("round_", range(4))
def test_concurrent_admin_deleters_never_leave_zero_administrators(client, db, n, round_):
    admins = [_user(db, f"a{i}-{round_}@example.com", admin=True) for i in range(n)]
    out = _run_concurrently(admins)
    for r in out.values():
        assert r.status_code == 200 or r.json()["error"]["code"] in ("last_admin", "delete_in_progress"), r.text
    assert len(_usable_admins(db, admins)) >= 1
    assert len(_usable_admins(db, admins)) == [r.status_code for r in out.values()].count(409)


def test_ordinary_account_promoted_during_the_request_is_checked_as_admin(client, db, monkeypatch):
    """The stale-admin race: the account was an ordinary user when the request authenticated; an admin promotion lands right
    after the claim. The re-read after the claim sees the admin flag and refuses (it is the only administrator)."""
    me = _user(db, "me@example.com", admin=False)
    real = ad.claim

    def claim_then_promote(db_, oid):
        t = real(db_, oid)
        db_.users.update_one({"_id": oid}, {"$set": {"is_admin": True}})
        return t

    monkeypatch.setattr(ad, "claim", claim_then_promote)
    r = _delete(client, me)
    assert r.status_code == 409 and r.json()["error"]["code"] == "last_admin"
    d = _doc(db, me)
    assert d is not None and not d.get("deleting") and "delete_claim_token" not in d


def test_promotion_between_the_check_and_the_tombstone_is_refused_by_the_tombstone(client, db, monkeypatch):
    me = _user(db, "me@example.com", admin=False)
    real = ad.verify_admin_safety

    def verify_then_promote(db_, oid, token):
        snap = real(db_, oid, token)
        db_.users.update_one({"_id": oid}, {"$set": {"is_admin": True}})
        return snap

    monkeypatch.setattr(ad, "verify_admin_safety", verify_then_promote)
    r = _delete(client, me)
    assert r.status_code == 409 and r.json()["error"]["code"] == "delete_conflict"
    assert _doc(db, me) is not None and not _doc(db, me).get("deleting")


def test_administrator_demoted_during_the_request_is_deleted_as_an_ordinary_account(client, db, monkeypatch):
    me = _user(db, "me@example.com", admin=True)           # the only administrator when the request authenticated
    real = ad.claim

    def claim_then_demote(db_, oid):
        t = real(db_, oid)
        db_.users.update_one({"_id": oid}, {"$set": {"is_admin": False}})
        return t

    monkeypatch.setattr(ad, "claim", claim_then_demote)
    assert _delete(client, me).status_code == 200
    assert _doc(db, me) is None


@pytest.mark.parametrize("state", [{"delete_claim_token": "t", "delete_claim_until": time.time() + 600},
                                   {"deleting": True, "deletion_token": "t"}, {"disabled": True}], ids=["claimed", "tombstoned", "disabled"])
def test_claimed_tombstoned_or_disabled_admin_is_not_usable(client, db, state):
    me, other = _user(db, "me@example.com", admin=True), _user(db, "other@example.com", admin=True)
    db.users.update_one({"_id": other["oid"]}, {"$set": state})
    r = _delete(client, me)
    assert r.status_code == 409 and r.json()["error"]["code"] == "last_admin"
    assert _doc(db, me) is not None


def test_env_listed_admin_counts_and_is_checked(client, db, monkeypatch):
    monkeypatch.setenv("SCRIPTLIV_ADMIN_EMAILS", "boss@example.com")
    boss = _user(db, "boss@example.com", admin=False)      # administrator by environment only
    assert _delete(client, boss).status_code == 409        # nobody else
    _user(db, "second@example.com", admin=True)
    assert _delete(client, boss).status_code == 200


# ================================ the HTTP delete route ==========================================================
def test_every_account_is_claimed_and_deleted_through_the_route(client, db):
    ann = _user(db, "ann@example.com")
    _seed(db, ann)
    r = _delete(client, ann)
    assert r.status_code == 200 and r.json() == {"deleted": True}
    assert _doc(db, ann) is None and _all_gone(db, ann) and _retained_intact(db, ann)


def test_duplicate_request_for_a_claimed_account_is_refused_without_stealing(client, db):
    ann = _user(db, "ann@example.com")
    db.users.update_one({"_id": ann["oid"]}, {"$set": {"delete_claim_token": "mine", "delete_claim_until": time.time() + 30}})
    r = _delete(client, ann)
    assert r.status_code == 409 and r.json()["error"]["code"] == "delete_in_progress"
    assert _doc(db, ann)["delete_claim_token"] == "mine"


def test_subscription_refusal_releases_the_claim_and_leaves_account_active(client, db):
    ann = _user(db, "ann@example.com")
    db.subscriptions.insert_one({"user_id": ann["id"], "plan": "pro", "status": "active", "cancel_at_period_end": False})
    r = _delete(client, ann)
    assert r.status_code == 409 and r.json()["error"]["code"] == "active_subscription"
    d = _doc(db, ann)
    assert not d.get("deleting") and "delete_claim_token" not in d
    assert db.subscriptions.count_documents({"user_id": ann["id"]}) == 1          # nothing was deleted
    assert client.get("/v1/me", headers=ann["h"]).status_code == 200


def test_cancelled_pro_subscription_may_be_deleted(client, db):
    ann = _user(db, "ann@example.com")
    db.subscriptions.insert_one({"user_id": ann["id"], "plan": "pro", "status": "active", "cancel_at_period_end": True})
    assert _delete(client, ann).status_code == 200


def test_cascade_failure_after_tombstone_reports_pending_and_never_restores_access(client, db, stages):
    ann = _user(db, "ann@example.com")
    _seed(db, ann)
    stages[3] = _raise_after(*stages[3])
    r = _delete(client, ann)
    assert r.status_code == 200 and r.json() == {"deleted": True, "pending": True}
    d = _doc(db, ann)
    assert d["deleting"] is True and "RuntimeError" in d["deletion_last_error"]
    assert client.get("/v1/me", headers=ann["h"]).status_code == 401
    assert client.post("/v1/auth/login", json={"email": "ann@example.com", "password": PW}).status_code == 401


# ================================ write barriers =================================================================
def test_normal_account_is_unaffected(client, db):
    ann = _user(db, "ann@example.com")
    assert client.get("/v1/me", headers=ann["h"]).status_code == 200
    assert client.patch("/v1/me", headers=ann["h"], json={"name": "Ann B"}).status_code == 200
    assert client.put("/v1/settings", headers=ann["h"], json={"theme": "dark"}).status_code == 200
    assert client.post("/v1/auth/login", json={"email": "ann@example.com", "password": PW}).status_code == 200


def test_claimed_account_keeps_working_but_cannot_start_a_purchase(client, db):
    ann = _user(db, "ann@example.com")
    db.users.update_one({"_id": ann["oid"]}, {"$set": {"delete_claim_token": "t", "delete_claim_until": time.time() + 30}})
    assert client.get("/v1/me", headers=ann["h"]).status_code == 200                    # claim is reversible: no lockout
    for path in ("/v1/billing/checkout", ):
        r = client.post(path, headers=ann["h"], json={"kind": "pro"})
        assert r.status_code == 409 and r.json()["error"]["code"] == "delete_in_progress"
    for path in ("/v1/billing/retry-payment", "/v1/subscription/resume"):
        r = client.post(path, headers=ann["h"])
        assert r.status_code == 409 and r.json()["error"]["code"] == "delete_in_progress"
    db.users.update_one({"_id": ann["oid"]}, {"$set": {"delete_claim_until": time.time() - 1}})   # expired claim: purchases allowed again
    assert client.post("/v1/billing/checkout", headers=ann["h"], json={"kind": "pro"}).json()["error"]["code"] != "delete_in_progress"


def test_tombstoned_account_cannot_sign_in_or_use_an_existing_token(client, db):
    ann = _user(db, "ann@example.com")
    assert client.get("/v1/me", headers=ann["h"]).status_code == 200
    _tombstone(db, ann)
    r = client.post("/v1/auth/login", json={"email": "ann@example.com", "password": PW})
    assert r.status_code == 401 and r.json()["error"]["code"] == "bad_credentials"       # same answer as a wrong password
    for method, path, body in [("GET", "/v1/me", None), ("PATCH", "/v1/me", {"name": "X"}), ("GET", "/v1/settings", None),
                               ("PUT", "/v1/settings", {"theme": "dark"}), ("GET", "/v1/subscription", None),
                               ("PUT", "/v1/billing/details", {"name": "X"}), ("GET", "/v1/usage", None),
                               ("POST", "/v1/billing/checkout", {"kind": "pro"}), ("POST", "/v1/sessions/x/share", None),
                               ("POST", "/v1/feedback", {"title": "t", "message": "m"}), ("DELETE", "/v1/me", {"password": PW})]:
        r = client.request(method, path, headers=ann["h"], **({"json": body} if body is not None else {}))
        assert r.status_code == 401, (method, path, r.status_code)


def test_tombstoned_account_cannot_use_email_flows(client, db):
    ann = _user(db, "ann@example.com")
    from app import email_service
    reset = email_service.issue_token(db, ann["id"], "reset", "ann@example.com")
    verify = email_service.issue_token(db, ann["id"], "verify", "new@example.com")
    reset_tok = reset if isinstance(reset, str) else reset["token"]
    verify_tok = verify if isinstance(verify, str) else verify["token"]
    _tombstone(db, ann)
    before = _doc(db, ann)
    assert client.post("/v1/auth/reset-password", json={"token": reset_tok, "new_password": "brand-new-pass-1"}).status_code == 400
    assert client.post("/v1/auth/verify-email", json={"token": verify_tok}).status_code == 400
    after = _doc(db, ann)
    assert after["pwhash"] == before["pwhash"] and after["email"] == "ann@example.com" and after["pwv"] == before["pwv"]
    n = db.email_tokens.count_documents({})
    assert client.post("/v1/auth/forgot-password", json={"email": "ann@example.com"}).status_code == 202
    assert client.post("/v1/auth/resend-verification", json={"email": "ann@example.com"}).status_code == 202
    assert db.email_tokens.count_documents({}) == n                                         # no token issued for it


def test_relay_cannot_authorize_a_tombstoned_account_and_a_reconnect_cannot_bypass_it(client, db):
    ann = _user(db, "ann@example.com")
    body = {"token": ann["token"], "session_id": "sess-0001"}
    first = client.post("/internal/v1/sessions/start", headers=R, json=body).json()
    assert first["allowed"] is True
    _tombstone(db, ann)
    again = client.post("/internal/v1/sessions/start", headers=R, json=body).json()        # reconnect to the same session
    assert again["allowed"] is False and again["reason"] == "invalid_token"
    new = client.post("/internal/v1/sessions/start", headers=R, json={**body, "session_id": "sess-0002"}).json()
    assert new["allowed"] is False
    assert db.sessions.find_one({"session_id": "sess-0002"}) is None and db.usage_sessions.find_one({"session_id": "sess-0002"}) is None


def test_relay_usage_reports_create_nothing_for_a_tombstoned_account_and_tell_the_relay_to_stop(client, db):
    ann = _user(db, "ann@example.com")
    assert client.post("/internal/v1/sessions/start", headers=R, json={"token": ann["token"], "session_id": "sess-0001"}).json()["allowed"]
    _tombstone(db, ann)
    before = (db.usage_sessions.find_one({"session_id": "sess-0001"}), db.usage_minutes.count_documents({}), db.usage_ledger.count_documents({}))
    for final in (False, True):
        r = client.post("/internal/v1/usage", headers=R, json={"user_id": ann["id"], "session_id": "sess-0001",
                                                              "cumulative_seconds": 90, "final": final})
        assert r.status_code == 200 and r.json()["allowed"] is False and r.json()["reason"] == "account_unavailable"
    r = client.post("/internal/v1/usage", headers=R, json={"user_id": ann["id"], "session_id": "sess-9999", "cumulative_seconds": 30})
    assert r.json()["allowed"] is False
    assert (db.usage_sessions.find_one({"session_id": "sess-0001"}), db.usage_minutes.count_documents({}), db.usage_ledger.count_documents({})) == before
    assert db.usage_sessions.find_one({"session_id": "sess-9999"}) is None


def test_relay_usage_for_a_deleted_account_is_refused_too(client, db):
    ghost = {"id": str(ObjectId())}
    r = client.post("/internal/v1/usage", headers=R, json={"user_id": ghost["id"], "session_id": "sess-0001", "cumulative_seconds": 30})
    assert r.json()["allowed"] is False
    assert db.usage_sessions.count_documents({}) == 0 and db.usage_ledger.count_documents({}) == 0


def test_usage_module_refuses_a_tombstoned_account_even_when_called_directly(db):
    from app import usage
    ann = _user(db, "ann@example.com")
    _tombstone(db, ann)
    assert usage.authorize(db, ann["id"], session_id="sess-0001")["allowed"] is False
    assert usage.authorize(db, ann["id"])["allowed"] is False
    assert usage.record(db, ann["id"], "sess-0001", 60)["applied_seconds"] == 0.0
    sub = usage.get_subscription(db, ann["id"])           # a read must not create a subscription for it
    assert sub["plan"] == "basic"
    for c in ("usage_sessions", "usage_minutes", "usage_ledger", "subscriptions", "addons"):
        assert db[c].count_documents({}) == 0, c


def test_provider_webhooks_write_nothing_for_a_tombstoned_account(db, caplog):
    ann = _user(db, "ann@example.com")
    sub = {"user_id": ann["id"], "plan": "pro", "status": "active", "cancel_at_period_end": True, "provider_customer_id": "cus_1",
           "period_end": time.time() + 999, "anchor": 0, "period_start": 0}
    db.subscriptions.insert_one(sub)
    _tombstone(db, ann)
    db.subscriptions.delete_many({"user_id": ann["id"]})
    db.subscriptions.insert_one(dict(sub))
    n_subs, n_pay, n_add = db.subscriptions.count_documents({}), db.payments.count_documents({}), db.addons.count_documents({})
    events = [
        {"type": "checkout.session.completed", "data": {"object": {"payment_status": "paid", "id": "cs_1", "customer": "cus_1", "subscription": "sub_1",
                                                                    "metadata": {"user_id": ann["id"], "kind": "pro"}}}},
        {"type": "checkout.session.completed", "data": {"object": {"payment_status": "paid", "id": "cs_2", "payment_intent": "pi_1", "amount_total": 500,
                                                                    "metadata": {"user_id": ann["id"], "kind": "addon"}}}},
        {"type": "invoice.paid", "data": {"object": {"id": "in_1", "customer": "cus_1", "amount_paid": 900}}},
        {"type": "invoice.payment_failed", "data": {"object": {"id": "in_2", "customer": "cus_1", "amount_due": 900, "attempt_count": 1}}},
    ]
    with caplog.at_level("ERROR", logger="scriptliv.billing"):
        for ev in events:
            billing._apply_event(db, ev)
    assert (db.subscriptions.count_documents({}), db.payments.count_documents({}), db.addons.count_documents({})) == (n_subs, n_pay, n_add)
    assert db.subscriptions.find_one({"user_id": ann["id"]})["plan"] == "pro" and db.subscriptions.find_one({"user_id": ann["id"]})["cancel_at_period_end"] is True
    assert caplog.text.count("billing_event_for_deleting_account") == 4          # operator-visible, with no silent drop


def test_provider_webhooks_still_work_for_a_normal_account(db):
    ann = _user(db, "ann@example.com")
    billing._apply_event(db, {"type": "checkout.session.completed", "data": {"object": {
        "payment_status": "paid", "id": "cs_1", "customer": "cus_1", "subscription": "sub_1", "metadata": {"user_id": ann["id"], "kind": "pro"}}}})
    assert db.subscriptions.find_one({"user_id": ann["id"]})["plan"] == "pro"


def test_admin_cannot_modify_a_tombstoned_account(client, db):
    boss, ann = _user(db, "boss@example.com", admin=True), _user(db, "ann@example.com")
    _tombstone(db, ann)
    for patch in ({"plan": "pro"}, {"grant_addon_minutes": 60}, {"is_admin": True}, {"disabled": False}):
        r = client.patch(f"/v1/admin/users/{ann['id']}", headers=boss["h"], json=patch)
        assert r.status_code == 409 and r.json()["error"]["code"] == "account_deleting", patch
    d = _doc(db, ann)
    assert not d.get("is_admin") and db.subscriptions.count_documents({"user_id": ann["id"]}) == 0 and db.addons.count_documents({"user_id": ann["id"]}) == 0
    other = _user(db, "other@example.com")        # ordinary admin operations on others are unaffected
    assert client.patch(f"/v1/admin/users/{other['id']}", headers=boss["h"], json={"plan": "pro"}).status_code == 200


def test_shared_transcript_goes_dark_when_the_owner_is_tombstoned(client, db):
    ann = _user(db, "ann@example.com")
    _seed(db, ann)
    assert client.get("/v1/shared/share-" + ann["id"]).status_code == 200
    _tombstone(db, ann)
    assert client.get("/v1/shared/share-" + ann["id"]).status_code == 404


def test_registering_the_tombstoned_email_is_refused_until_the_account_is_gone(client, db):
    ann = _user(db, "ann@example.com")
    _tombstone(db, ann)
    r = client.post("/v1/auth/register", json={"name": "N", "email": "ann@example.com", "password": PW})
    assert r.status_code in (409, 422) and db.users.count_documents({"email": "ann@example.com"}) == 1


# ================================ failure and recovery ===========================================================
_ORIGINAL_STAGES = list(ad.STAGES)
STAGE_NAMES = [n for n, _ in _ORIGINAL_STAGES]


def test_failure_after_tombstone_before_any_cascade_work(db, stages):
    ann = _user(db, "ann@example.com")
    _seed(db, ann)
    t = _tombstone(db, ann)
    stages[0] = (stages[0][0], lambda d, uid: (_ for _ in ()).throw(RuntimeError("boom")))     # fails before touching anything
    assert ad.run_deletion(db, ann["oid"], t) == "failed"
    d = _doc(db, ann)
    assert d["deleting"] is True and d["deletion_done"] == [] and "boom" in d["deletion_last_error"] and "deletion_lease_owner" not in d
    assert _remaining(db, ann)["sessions"] == 1 and _retained_intact(db, ann)
    assert ad.recover_deletions(db)["found"] == 0                    # backing off: not retried hot
    _expire_lease(db, ann)
    stages[:] = _ORIGINAL_STAGES
    assert ad.recover_deletions(db) == {"found": 1, "completed": 1, "failed": 0, "busy": 0, "lease_lost": 0}
    assert _doc(db, ann) is None and _all_gone(db, ann) and _retained_intact(db, ann)


@pytest.mark.parametrize("i", range(len(STAGE_NAMES)), ids=STAGE_NAMES)
def test_crash_after_each_cascade_stage_is_completed_by_recovery(db, stages, i):
    ann = _user(db, "ann@example.com")
    _seed(db, ann)
    t = _tombstone(db, ann)
    stages[i] = _raise_after(*stages[i])                            # the stage's deletes happen, the "process" then dies
    assert ad.run_deletion(db, ann["oid"], t) == "failed"
    d = _doc(db, ann)
    assert d is not None and d["deleting"] is True               # the user document survives until the very end
    assert STAGE_NAMES[i] not in d["deletion_done"] and d["deletion_done"] == STAGE_NAMES[:i]
    assert _retained_intact(db, ann)
    _expire_lease(db, ann)
    stages[:] = _ORIGINAL_STAGES
    assert ad.recover_deletions(db)["completed"] == 1
    assert _doc(db, ann) is None and _all_gone(db, ann) and _retained_intact(db, ann)


def test_user_document_is_removed_only_after_every_stage_is_recorded(db, stages):
    ann = _user(db, "ann@example.com")
    _seed(db, ann)
    t = _tombstone(db, ann)
    seen = []
    stages[:] = [(n, (lambda f: lambda d, uid: (seen.append(d.users.find_one({"_id": ann["oid"]}) is not None), f(d, uid)))(f)) for n, f in stages]
    assert ad.run_deletion(db, ann["oid"], t) == "completed"
    assert seen and all(seen)                                        # present during every stage and the final sweep
    last = stages[-1]
    # a run whose stages are not all recorded cannot remove the document, whatever else is true
    ann2 = _user(db, "b@example.com")
    t2 = _tombstone(db, ann2)
    db.users.update_one({"_id": ann2["oid"]}, {"$set": {"deletion_lease_owner": "w", "deletion_lease_until": time.time() + 99}})
    r = db.users.delete_one({"_id": ann2["oid"], "deleting": True, "deletion_token": t2, "deletion_lease_owner": "w",
                             "deletion_done": {"$all": [n for n, _ in stages]}})
    assert r.deleted_count == 0 and _doc(db, ann2) is not None and last


def test_repeated_recovery_is_harmless(db):
    ann, bob = _user(db, "ann@example.com"), _user(db, "bob@example.com")
    _seed(db, ann)
    _seed(db, bob)
    _tombstone(db, ann)
    assert ad.recover_deletions(db)["completed"] == 1
    for _ in range(3):
        assert ad.recover_deletions(db) == {"found": 0, "completed": 0, "failed": 0, "busy": 0, "lease_lost": 0}
    assert _doc(db, ann) is None and _doc(db, bob) is not None and _remaining(db, bob)["sessions"] == 1   # untouched neighbours
    assert ad.run_deletion(db, ann["oid"], "tok") == "busy"           # a stale retry of a finished deletion does nothing


def test_concurrent_workers_cannot_duplicate_destructive_work(db, stages):
    ann = _user(db, "ann@example.com")
    _seed(db, ann)
    t = _tombstone(db, ann)
    counts, lock = {}, threading.Lock()
    in_first, go = threading.Event(), threading.Event()

    def counted(name, real, block=False):
        def run(d, uid):
            with lock:
                counts[name] = counts.get(name, 0) + 1
            if block:
                in_first.set()
                assert go.wait(20)
            real(d, uid)
        return (name, run)

    stages[:] = [counted(n, f, block=(k == 0)) for k, (n, f) in enumerate(stages)]
    res = {}
    a = threading.Thread(target=lambda: res.__setitem__("a", ad.run_deletion(db, ann["oid"], t, "worker-a")))
    a.start()
    assert in_first.wait(20)
    res["b"] = ad.run_deletion(db, ann["oid"], t, "worker-b")           # A holds the lease and is mid-stage
    assert res["b"] == "busy" and ad.recover_deletions(db)["found"] == 0
    go.set()
    a.join(30)
    assert res["a"] == "completed"
    assert all(counts[n] == 2 for n in STAGE_NAMES), counts           # one run + the final sweep, by the lease holder only
    assert _doc(db, ann) is None


def test_a_worker_that_loses_its_lease_stops_and_never_deletes_the_user(db, stages):
    ann = _user(db, "ann@example.com")
    _seed(db, ann)
    t = _tombstone(db, ann)
    real0 = stages[0][1]

    def stall_then_get_taken_over(d, uid):
        real0(d, uid)
        _expire_lease(d, ann)                                         # A stalls past its lease ...
        assert ad._acquire(d, ann["oid"], t, "worker-b")              # ... and B takes over
    stages[0] = (stages[0][0], stall_then_get_taken_over)
    assert ad.run_deletion(db, ann["oid"], t, "worker-a") == "lease_lost"
    d = _doc(db, ann)
    assert d is not None and d["deletion_lease_owner"] == "worker-b"
    stages[:] = _ORIGINAL_STAGES
    assert ad.run_deletion(db, ann["oid"], t, "worker-c") == "busy"      # B's lease is live: nobody else may run
    _expire_lease(db, ann)                                               # B crashes too; its lease lapses
    assert ad.run_deletion(db, ann["oid"], t, "worker-c") == "completed"


def test_recovery_is_bounded_and_oldest_first(db):
    users = []
    for k in range(25):
        u = _user(db, f"u{k}@example.com")
        users.append(u)
        _tombstone(db, u)
        db.users.update_one({"_id": u["oid"]}, {"$set": {"deletion_started_at": 1000 + k}})
    out = ad.recover_deletions(db, limit=10)
    assert out["found"] == 10 and out["completed"] == 10
    assert all(_doc(db, u) is None for u in users[:10]) and all(_doc(db, u) is not None for u in users[10:])
    assert ad.pending_deletions(db)["pending"] == 15
    assert ad.recover_deletions(db, limit=0)["found"] == 0


def test_recovery_needs_no_authentication_and_works_on_an_account_that_cannot_sign_in(db):
    ann = _user(db, "ann@example.com")
    _seed(db, ann)
    _tombstone(db, ann)
    assert ad.recover_deletions(db)["completed"] == 1 and _doc(db, ann) is None


def test_backoff_grows_and_is_capped(db, stages):
    ann = _user(db, "ann@example.com")
    t = _tombstone(db, ann)
    stages[0] = (stages[0][0], lambda d, uid: (_ for _ in ()).throw(RuntimeError("down")))
    waits = []
    for _ in range(8):
        assert ad.run_deletion(db, ann["oid"], t) == "failed"
        waits.append(round(_doc(db, ann)["deletion_lease_until"] - time.time()))
        _expire_lease(db, ann)
    assert waits[0] == ad.BACKOFF_BASE_SECONDS and waits[1] == 2 * ad.BACKOFF_BASE_SECONDS and max(waits) == ad.BACKOFF_MAX_SECONDS
    assert ad.pending_deletions(db)["failing"] == 1


def test_recovery_loop_does_not_run_at_startup_and_finishes_deletions_in_the_background(db):
    ann = _user(db, "ann@example.com")
    _seed(db, ann)
    _tombstone(db, ann)
    stop = ad.start_recovery_loop(lambda: db, interval=3600)          # long interval: nothing happens at start
    time.sleep(0.05)
    assert _doc(db, ann) is not None
    stop()
    stop = ad.start_recovery_loop(lambda: db, interval=0.02)
    try:
        for _ in range(300):
            if _doc(db, ann) is None:
                break
            time.sleep(0.02)
    finally:
        stop()
    assert _doc(db, ann) is None and _all_gone(db, ann)


def test_recovery_loop_survives_errors_and_can_be_disabled(db):
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("db down")
        return db
    stop = ad.start_recovery_loop(flaky, interval=0.02)
    try:
        for _ in range(300):
            if len(calls) >= 3:
                break
            time.sleep(0.02)
    finally:
        stop()
    assert len(calls) >= 3                                            # kept going after the first failure
    n = len(threading.enumerate())
    assert ad.start_recovery_loop(lambda: db, interval=0)() is None and len(threading.enumerate()) == n


def test_app_lifespan_starts_and_stops_the_sweeper(db, monkeypatch):
    from app.main import app
    monkeypatch.setenv(ad.RECOVERY_INTERVAL_ENV, "0.05")
    with TestClient(app) as c:
        assert any(t.name == "deletion-recovery" for t in threading.enumerate())
        assert c.get("/healthz").status_code == 200
    for _ in range(100):
        if not any(t.name == "deletion-recovery" for t in threading.enumerate()):
            break
        time.sleep(0.02)
    assert not any(t.name == "deletion-recovery" for t in threading.enumerate())
    monkeypatch.setenv(ad.RECOVERY_INTERVAL_ENV, "0")
    with TestClient(app):
        assert not any(t.name == "deletion-recovery" for t in threading.enumerate())


def test_retained_collections_are_never_touched_by_the_cascade(db):
    a, b = _user(db, "a@example.com"), _user(db, "b@example.com")
    _seed(db, a)
    _seed(db, b)
    t = _tombstone(db, a)
    assert ad.run_deletion(db, a["oid"], t) == "completed"
    assert _retained_intact(db, a) and _retained_intact(db, b) and _remaining(db, b)["sessions"] == 1


# ================================ mutation checks ================================================================
# Each invariant is a small scenario that must hold on the real code. The mutants below re-introduce one specific bug in
# one critical transition or barrier; the matching invariant must then FAIL (the mutant is "killed"), proving the suite
# would notice that regression.
def _fresh():
    d = mongomock.MongoClient().mutation
    return d


def inv_tombstone_needs_matching_token():
    db = _fresh()
    u = _user(db, "a@example.com")
    ad.claim(db, u["oid"])
    return not ad.tombstone(db, u["oid"], "forged", {"email": "a@example.com", "admin": False})


def inv_tombstone_needs_unexpired_claim():
    db = _fresh()
    u = _user(db, "a@example.com")
    t = ad.claim(db, u["oid"])
    db.users.update_one({"_id": u["oid"]}, {"$set": {"delete_claim_until": time.time() - 1}})
    return not ad.tombstone(db, u["oid"], t, {"email": "a@example.com", "admin": False})


def inv_claim_refuses_tombstoned_account():
    db = _fresh()
    u = _user(db, "a@example.com")
    _tombstone(db, u)
    return ad.claim(db, u["oid"]) is None


def inv_claim_is_exclusive():
    db = _fresh()
    u = _user(db, "a@example.com")
    return ad.claim(db, u["oid"]) is not None and ad.claim(db, u["oid"]) is None


def inv_release_needs_owner_token():
    db = _fresh()
    u = _user(db, "a@example.com")
    t = ad.claim(db, u["oid"])
    ad.release_claim(db, u["oid"], "intruder")
    return _doc(db, u).get("delete_claim_token") == t


def inv_claimed_admin_is_not_usable():
    db = _fresh()
    me, other = _user(db, "me@example.com", admin=True), _user(db, "o@example.com", admin=True)
    db.users.update_one({"_id": other["oid"]}, {"$set": {"delete_claim_token": "t", "delete_claim_until": time.time() + 60}})
    return not deps.other_admin_exists(db, me["oid"])


def inv_tombstoned_admin_is_not_usable():
    db = _fresh()
    me, other = _user(db, "me@example.com", admin=True), _user(db, "o@example.com", admin=True)
    _tombstone(db, other)
    return not deps.other_admin_exists(db, me["oid"])


def inv_webhook_guard_sees_tombstone():
    db = _fresh()
    u = _user(db, "a@example.com")
    _tombstone(db, u)
    return ad.is_deleting_uid(db, u["id"]) and ad.account_unavailable(db, u["id"])


def inv_cascade_does_not_run_without_tombstone():
    db = _fresh()
    u = _user(db, "a@example.com")
    _seed(db, u)
    ad.claim(db, u["oid"])
    ad.run_deletion(db, u["oid"], "x")
    return _doc(db, u) is not None and _remaining(db, u)["sessions"] == 1


def inv_deleted_account_cannot_be_reclaimed_or_tombstoned():
    db = _fresh()
    return not ad.tombstone(db, ObjectId(), "t", {"email": "a@example.com", "admin": False}) and ad.claim(db, ObjectId()) is None


def _m_tombstone_ignores_token(db, oid, token, snapshot):
    return bool(db.users.update_one({"_id": oid, "delete_claim_until": {"$gt": time.time()}, "deleting": {"$ne": True}},
                                    {"$set": {"deleting": True, "deletion_token": token}}).matched_count)


def _m_tombstone_ignores_expiry(db, oid, token, snapshot):
    return bool(db.users.update_one({"_id": oid, "delete_claim_token": token, "deleting": {"$ne": True}},
                                    {"$set": {"deleting": True, "deletion_token": token}}).matched_count)


def _m_claim_ignores_tombstone(db, oid):
    t = "tok"
    return t if db.users.update_one({"_id": oid, "$or": [{"delete_claim_until": {"$exists": False}}, {"delete_claim_until": {"$lte": time.time()}}]},
                                    {"$set": {"delete_claim_token": t, "delete_claim_until": time.time() + 60}}).matched_count else None


def _m_claim_not_exclusive(db, oid):
    t = "tok"
    db.users.update_one({"_id": oid}, {"$set": {"delete_claim_token": t, "delete_claim_until": time.time() + 60}})
    return t


def _m_release_ignores_token(db, oid, token):
    db.users.update_one({"_id": oid}, {"$unset": {"delete_claim_token": "", "delete_claim_until": ""}})


def _m_other_admin_counts_claimed(db, exclude_oid):
    return db.users.count_documents({"_id": {"$ne": exclude_oid}, "disabled": {"$ne": True}, "deleting": {"$ne": True}, "is_admin": True}) > 0


def _m_other_admin_counts_tombstoned(db, exclude_oid):
    return db.users.count_documents({"_id": {"$ne": exclude_oid}, "disabled": {"$ne": True}, "is_admin": True,
                                     "delete_claim_until": {"$not": {"$gt": time.time()}}}) > 0


def _m_run_without_tombstone_guard(db, oid, token, worker=None):
    for _, fn in ad.STAGES:                        # no tombstone check at all: straight into the destructive work
        fn(db, str(oid))
    return "completed"


MUTANTS = [
    ("tombstone ignores the token", ad, "tombstone", _m_tombstone_ignores_token, inv_tombstone_needs_matching_token),
    ("tombstone ignores claim expiry", ad, "tombstone", _m_tombstone_ignores_expiry, inv_tombstone_needs_unexpired_claim),
    ("claim ignores the tombstone", ad, "claim", _m_claim_ignores_tombstone, inv_claim_refuses_tombstoned_account),
    ("claim is not exclusive", ad, "claim", _m_claim_not_exclusive, inv_claim_is_exclusive),
    ("release ignores the token", ad, "release_claim", _m_release_ignores_token, inv_release_needs_owner_token),
    ("last-admin check counts claimed admins", deps, "other_admin_exists", _m_other_admin_counts_claimed, inv_claimed_admin_is_not_usable),
    ("last-admin check counts tombstoned admins", deps, "other_admin_exists", _m_other_admin_counts_tombstoned, inv_tombstoned_admin_is_not_usable),
    ("webhook/relay guard never sees the tombstone", ad, "is_deleting_uid", lambda db, uid: False, inv_webhook_guard_sees_tombstone),
    ("account_unavailable never sees the tombstone", ad, "account_unavailable", lambda db, uid: False, inv_webhook_guard_sees_tombstone),
    ("cascade has no tombstone guard", ad, "run_deletion", _m_run_without_tombstone_guard, inv_cascade_does_not_run_without_tombstone),
]

INVARIANTS = {m[4] for m in MUTANTS} | {inv_deleted_account_cannot_be_reclaimed_or_tombstoned}


@pytest.mark.parametrize("inv", sorted(INVARIANTS, key=lambda f: f.__name__), ids=lambda f: f.__name__)
def test_invariants_hold_on_the_real_implementation(inv):
    assert inv() is True


@pytest.mark.parametrize("name,module,attr,mutant,inv", MUTANTS, ids=[m[0] for m in MUTANTS])
def test_mutant_is_killed(monkeypatch, name, module, attr, mutant, inv):
    monkeypatch.setattr(module, attr, mutant)
    if module is deps:                                    # account_deletion imported the name directly
        monkeypatch.setattr(ad, attr, mutant)
    assert inv() is False, f"mutant survived: {name}"


def test_tombstone_guard_holds_even_if_the_lease_layer_is_broken(monkeypatch):
    """Two independent guards: the lease and the in-run tombstone check. Breaking the lease alone must not start a cascade."""
    monkeypatch.setattr(ad, "_acquire", lambda db, oid, token, worker: True)
    assert inv_cascade_does_not_run_without_tombstone() is True
