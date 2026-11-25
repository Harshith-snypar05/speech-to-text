"""Phase 3 Part C: API writes racing with the tombstone, and the compensating sweep (`reconcile_after_write`).

Deterministic: mongomock only, no network, no sleeping. A race is staged by wrapping the write so the tombstone lands at an
exact point (before the write, or straight after it), which is the interleaving a real second request would produce.
"""
import time

import pytest

from app import account_deletion as ad
from app import email_service, subscriptions
from app.security import hash_password, make_token

from .test_account_deletion import (R, _all_gone, _doc, _remaining, _retained_intact, _seed,
                                    _tombstone, _user)

PWHASH = hash_password("correct-horse-1")


@pytest.fixture(autouse=True)
def no_env_admins(monkeypatch):
    monkeypatch.setenv("SCRIPTLIV_ADMIN_EMAILS", "")


def _admin(db, email):
    doc = {"name": "Admin", "email": email, "email_verified": True, "pwhash": PWHASH, "pwv": 1, "created_at": time.time(),
           "disabled": False, "is_admin": True}
    oid = db.users.insert_one(doc).inserted_id
    return {"oid": oid, "id": str(oid), "h": {"Authorization": "Bearer " + make_token(str(oid), 1)}}


def _race(monkeypatch, coll, method, db, who, when):
    """Wrap `coll.<method>` so the tombstone lands 'before' the real write or 'after' it. Returns a call counter."""
    real = getattr(coll, method)
    calls = []

    def wrapped(*a, **kw):
        calls.append(1)
        if when == "before" and len(calls) == 1:
            _tombstone(db, who)
        out = real(*a, **kw)
        if when == "after" and len(calls) == 1:
            _tombstone(db, who)
        return out
    monkeypatch.setattr(coll, method, wrapped)
    return calls


def _no_account_rows(db, who):
    r = _remaining(db, who)
    return {k: v for k, v in r.items() if v}


WHEN = ["before", "after"]


# ---------------------------------------------------------------- reconcile_after_write itself
def test_reconcile_is_a_noop_for_an_active_account(db):
    u = _user(db, "ann@example.com")
    _seed(db, u)
    assert ad.reconcile_after_write(db, u["id"]) is False
    assert not _all_gone(db, u) and all(v == 1 for v in _remaining(db, u).values())


def test_reconcile_sweeps_every_keyed_collection_for_a_tombstoned_account_and_keeps_retained(db):
    u = _user(db, "ann@example.com")
    _seed(db, u)
    _tombstone(db, u)
    assert ad.reconcile_after_write(db, u["id"]) is True
    assert _all_gone(db, u) and _retained_intact(db, u)
    assert _doc(db, u) is not None             # the user document is the cascade's to remove, not the sweep's
    assert _doc(db, u)["deleting"] is True and _doc(db, u).get("deletion_done") == []     # no bookkeeping touched


def test_reconcile_leaves_other_accounts_alone(db):
    a, b = _user(db, "a@example.com"), _user(db, "b@example.com")
    _seed(db, a)
    _seed(db, b)
    _tombstone(db, a)
    ad.reconcile_after_write(db, a["id"])
    assert _all_gone(db, a) and all(v == 1 for v in _remaining(db, b).values())


def test_missing_user_is_gone_by_default_but_not_when_told_otherwise(db):
    ghost = "64b000000000000000000001"
    db.settings.insert_one({"user_id": ghost, "theme": "x"})
    assert ad.reconcile_after_write(db, ghost, missing_is_gone=False) is False    # no user doc, no tombstone: untouched
    assert db.settings.count_documents({"user_id": ghost}) == 1
    assert ad.reconcile_after_write(db, ghost) is True                           # default: a missing account is gone
    assert db.settings.count_documents({"user_id": ghost}) == 0


def test_reconcile_survives_a_failing_stage_and_still_reports_gone(db, monkeypatch):
    u = _user(db, "ann@example.com")
    _seed(db, u)
    _tombstone(db, u)
    stages = list(ad.STAGES)
    stages[0] = (stages[0][0], lambda db_, uid: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(ad, "STAGES", stages)
    assert ad.reconcile_after_write(db, u["id"]) is True      # best effort: never raises
    left = _no_account_rows(db, u)
    assert list(left) == [stages[0][0]]                        # every other stage still ran


def test_cascade_final_sweep_removes_rows_a_permitted_inflight_write_left(db, monkeypatch):
    """A write that lands AFTER the tombstone and after its own check (the crash window) is removed by the final sweep."""
    u = _user(db, "ann@example.com")
    _seed(db, u)
    token = _tombstone(db, u)
    stages = list(ad.STAGES)
    last_name, last_fn = stages[-1]
    fired = []

    def last_then_straggler(db_, uid):
        last_fn(db_, uid)
        if not fired:                      # only after the first full pass; the final sweep must then remove these
            fired.append(1)
            db_.settings.insert_one({"user_id": uid, "theme": "straggler"})
            db_.addons.insert_one({"user_id": uid, "seconds_total": 1.0})
    stages[-1] = (last_name, last_then_straggler)
    monkeypatch.setattr(ad, "STAGES", stages)
    assert ad.run_deletion(db, u["oid"], token) == "completed"
    assert fired and _doc(db, u) is None and _all_gone(db, u) and _retained_intact(db, u)


# ---------------------------------------------------------------- relay-facing endpoints
@pytest.mark.parametrize("when", WHEN)
def test_session_start_racing_the_tombstone_leaves_no_rows_and_refuses(client, db, monkeypatch, when):
    u = _user(db, "ann@example.com")
    _race(monkeypatch, db.sessions, "update_one", db, u, when)
    r = client.post("/internal/v1/sessions/start", headers=R, json={"token": u["token"], "session_id": "sess-race1"})
    assert r.status_code == 200
    j = r.json()
    if when == "after":                       # the write landed first; the compensating check caught the tombstone
        assert j["allowed"] is False and j["reason"] == "invalid_token"
    assert _no_account_rows(db, u) == {}, "no session, reservation or usage row may outlive the tombstone"
    assert db.sessions.count_documents({"owner_id": u["id"]}) == 0


@pytest.mark.parametrize("when", WHEN)
def test_usage_report_racing_the_tombstone_leaves_no_rows(client, db, monkeypatch, when):
    u = _user(db, "ann@example.com")
    assert client.post("/internal/v1/sessions/start", headers=R, json={"token": u["token"], "session_id": "sess-race2"}).json()["allowed"]
    _race(monkeypatch, db.usage_sessions, "update_one", db, u, when)
    r = client.post("/internal/v1/usage", headers=R,
                    json={"user_id": u["id"], "session_id": "sess-race2", "cumulative_seconds": 30.0})
    assert r.status_code == 200 and r.json()["allowed"] is False
    assert _no_account_rows(db, u) == {}


def test_usage_report_after_tombstone_writes_nothing_and_stops_the_session(client, db):
    u = _user(db, "ann@example.com")
    assert client.post("/internal/v1/sessions/start", headers=R, json={"token": u["token"], "session_id": "sess-dead01"}).json()["allowed"]
    _tombstone(db, u)
    ad.reconcile_after_write(db, u["id"])
    for final in (False, True):
        r = client.post("/internal/v1/usage", headers=R, json={"user_id": u["id"], "session_id": "sess-dead01",
                                                               "cumulative_seconds": 12.0, "final": final})
        assert r.status_code == 200
        assert r.json()["allowed"] is False and r.json()["reason"] == "account_unavailable"
    assert _no_account_rows(db, u) == {}


def test_active_account_unaffected_by_the_sweep(client, db):
    u = _user(db, "ann@example.com")
    s = client.post("/internal/v1/sessions/start", headers=R, json={"token": u["token"], "session_id": "sess-live01"}).json()
    assert s["allowed"] is True and s["user_id"] == u["id"]
    r = client.post("/internal/v1/usage", headers=R, json={"user_id": u["id"], "session_id": "sess-live01", "cumulative_seconds": 30.0})
    assert r.status_code == 200 and r.json()["allowed"] is True
    again = client.post("/internal/v1/sessions/start", headers=R, json={"token": u["token"], "session_id": "sess-live01"}).json()
    assert again["allowed"] is True                                  # reconnect
    assert db.sessions.count_documents({"owner_id": u["id"]}) == 1 and db.usage_sessions.count_documents({"user_id": u["id"]}) == 1


# ---------------------------------------------------------------- account routes
@pytest.mark.parametrize("when", WHEN)
def test_settings_put_racing_the_tombstone(client, db, monkeypatch, when):
    u = _user(db, "ann@example.com")
    _race(monkeypatch, db.settings, "update_one", db, u, when)
    r = client.put("/v1/me/settings", json={"theme": "dark"}, headers=u["h"]) if False else \
        client.put("/v1/settings", json={"theme": "dark"}, headers=u["h"])
    assert db.settings.count_documents({"user_id": u["id"]}) == 0
    if when == "after":
        assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_token"


def test_settings_put_for_an_active_account_still_saves(client, db):
    u = _user(db, "ann@example.com")
    r = client.put("/v1/settings", json={"theme": "dark"}, headers=u["h"])
    assert r.status_code == 200
    assert db.settings.count_documents({"user_id": u["id"]}) == 1


# ---------------------------------------------------------------- subscriptions / email tokens (library calls)
def test_get_subscription_racing_the_tombstone_leaves_no_row(db, monkeypatch):
    u = _user(db, "ann@example.com")
    real = subscriptions.create_basic

    def create_then_tombstone(db_, uid, now=None):
        out = real(db_, uid, now)
        _tombstone(db_, u)               # tombstone lands between the check and the insert becoming visible
        return out
    monkeypatch.setattr(subscriptions, "create_basic", create_then_tombstone)
    subscriptions.get_subscription(db, u["id"])
    assert db.subscriptions.count_documents({"user_id": u["id"]}) == 0


def test_get_subscription_for_a_tombstoned_account_creates_nothing(db):
    u = _user(db, "ann@example.com")
    _tombstone(db, u)
    sub = subscriptions.get_subscription(db, u["id"])
    assert sub["plan"] and db.subscriptions.count_documents({"user_id": u["id"]}) == 0


def test_get_subscription_for_an_active_account_creates_the_basic_row(db):
    u = _user(db, "ann@example.com")
    subscriptions.get_subscription(db, u["id"])
    assert db.subscriptions.count_documents({"user_id": u["id"]}) == 1


def test_get_subscription_tolerates_an_id_with_no_user_document(db):
    """missing_is_gone=False: a relay-only / test identity with no users row is not treated as deleted."""
    subscriptions.get_subscription(db, "64b000000000000000000002")
    assert db.subscriptions.count_documents({"user_id": "64b000000000000000000002"}) == 1


@pytest.mark.parametrize("when", WHEN)
def test_issue_token_racing_the_tombstone_leaves_no_token(db, monkeypatch, when):
    u = _user(db, "ann@example.com")
    _race(monkeypatch, db.email_tokens, "insert_one", db, u, when)
    email_service.issue_token(db, u["id"], "verify", "ann@example.com")
    assert db.email_tokens.count_documents({"user_id": u["id"]}) == 0


def test_issue_token_for_an_active_account_still_issues(db):
    u = _user(db, "ann@example.com")
    tok = email_service.issue_token(db, u["id"], "verify", "ann@example.com")
    assert tok and db.email_tokens.count_documents({"user_id": u["id"]}) == 1


# ---------------------------------------------------------------- admin PATCH
@pytest.mark.parametrize("when", WHEN)
def test_admin_patch_racing_the_tombstone_leaves_no_plan_or_addon(client, db, monkeypatch, when):
    boss, ann = _admin(db, "boss@example.com"), _user(db, "ann@example.com")
    _race(monkeypatch, db.subscriptions, "update_one", db, ann, when)
    r = client.patch(f"/v1/admin/users/{ann['id']}", json={"plan": "pro", "grant_addon_minutes": 5}, headers=boss["h"])
    assert db.subscriptions.count_documents({"user_id": ann["id"]}) == 0
    assert db.addons.count_documents({"user_id": ann["id"]}) == 0
    assert r.status_code == 409 and r.json()["error"]["code"] == "account_deleting"


def test_admin_patch_for_an_active_account_still_applies(client, db):
    boss, ann = _admin(db, "boss@example.com"), _user(db, "ann@example.com")
    r = client.patch(f"/v1/admin/users/{ann['id']}", json={"plan": "pro", "grant_addon_minutes": 5}, headers=boss["h"])
    assert r.status_code == 200
    assert db.subscriptions.count_documents({"user_id": ann["id"]}) == 1 and db.addons.count_documents({"user_id": ann["id"]}) == 1


# ---------------------------------------------------------------- relay unavailable during deletion
def test_deletion_completes_with_no_relay_and_nothing_waits_on_one(client, db):
    """There is no relay endpoint, ack or wait in the deletion path: with the relay down the API still finishes."""
    u = _user(db, "ann@example.com")
    _seed(db, u)
    r = client.request("DELETE", "/v1/me", json={"password": "correct-horse-1"}, headers=u["h"])
    assert r.status_code == 200 and r.json() == {"deleted": True}
    assert _doc(db, u) is None and _all_gone(db, u) and _retained_intact(db, u)


def test_a_relay_that_comes_back_late_cannot_recreate_anything_through_the_api(client, db):
    u = _user(db, "ann@example.com")
    _seed(db, u)
    assert client.request("DELETE", "/v1/me", json={"password": "correct-horse-1"}, headers=u["h"]).status_code == 200
    # the relay reconnects later with the dead account's token / id
    s = client.post("/internal/v1/sessions/start", headers=R, json={"token": u["token"], "session_id": "sess-late01"}).json()
    assert s["allowed"] is False
    for final in (False, True):
        r = client.post("/internal/v1/usage", headers=R, json={"user_id": u["id"], "session_id": "sess-late01",
                                                               "cumulative_seconds": 40.0, "final": final})
        assert r.status_code == 200 and r.json()["allowed"] is False
    assert _all_gone(db, u) and _doc(db, u) is None
    assert db.usage_sessions.count_documents({"user_id": u["id"]}) == 0 and db.sessions.count_documents({"owner_id": u["id"]}) == 0


def test_pending_true_response_shape_when_the_cascade_cannot_finish(client, db, monkeypatch):
    u = _user(db, "ann@example.com")
    _seed(db, u)
    stages = list(ad.STAGES)
    stages[3] = (stages[3][0], lambda db_, uid: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(ad, "STAGES", stages)
    r = client.request("DELETE", "/v1/me", json={"password": "correct-horse-1"}, headers=u["h"])
    assert r.status_code == 200 and r.json() == {"deleted": True, "pending": True}
    assert _doc(db, u)["deleting"] is True
    # and the half-deleted account still cannot be used or written to
    assert client.get("/v1/settings", headers=u["h"]).status_code == 401
    assert client.post("/internal/v1/sessions/start", headers=R, json={"token": u["token"], "session_id": "sess-pend01"}).json()["allowed"] is False
