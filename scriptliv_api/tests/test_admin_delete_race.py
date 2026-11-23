"""Two administrators deleting themselves at the same moment must never leave zero enabled administrators.

Strategy under test (app.account_deletion + app.routers.account.delete_account): publish a claim on the account first,
re-read the account and check for another usable administrator second (claimed, tombstoned and disabled accounts do not count),
then tombstone with a conditional update that needs the claim to still be valid. No transactions, no waiting lock, no retry loop.
"""
import threading
import time

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

from app import account_deletion
from app.security import hash_password, make_token

PW = "correct-horse-1"
PWHASH = hash_password(PW)   # hashed once for the module; every fixture user shares it


def _admin(db, email, **extra):
    doc = {"name": "Admin", "email": email, "email_verified": True, "pwhash": PWHASH, "pwv": 1, "created_at": time.time(),
           "disabled": False, "is_admin": True, **extra}
    oid = db.users.insert_one(doc).inserted_id
    return {"oid": oid, "id": str(oid), "h": {"Authorization": "Bearer " + make_token(str(oid), 1)}}


def _delete(client, who):
    return client.request("DELETE", "/v1/me", json={"password": PW}, headers=who["h"])


def _exists(db, who):
    return db.users.find_one({"_id": who["oid"]}) is not None


def _enabled_admins(db, *who):
    return [w for w in who if (u := db.users.find_one({"_id": w["oid"]})) and not u.get("disabled") and u.get("is_admin")]


def _run_concurrently(db, a, b, wrapper=None):
    """Fire both self-deletions from separate threads (separate clients) released at the same instant."""
    from app.main import app
    out, gate = {}, threading.Barrier(2, timeout=20)

    def go(name, who):
        c = TestClient(app)
        gate.wait()
        out[name] = _delete(c, who)

    ts = [threading.Thread(target=go, args=("a", a)), threading.Thread(target=go, args=("b", b))]
    [t.start() for t in ts]
    [t.join(60) for t in ts]
    assert set(out) == {"a", "b"}, "a request thread did not finish"
    return out


def _code(r):
    return r.json()["error"]["code"] if r.status_code != 200 else None


@pytest.fixture(autouse=True)
def no_env_admins(monkeypatch):
    monkeypatch.setenv("SCRIPTLIV_ADMIN_EMAILS", "")


# ---- the race ----------------------------------------------------------------------------------------------------------
def test_both_claim_before_either_checks_never_removes_both_admins(client, db, monkeypatch):
    """Worst interleaving for check-then-delete: both requests finish their 'is there another admin?' check before either
    one deletes anything. The unguarded code let both succeed (each saw the other). Now the claims are published before the
    checks, so at least one check sees the other's claim and refuses. The refused request releases its claim, but by then the
    other's check is already done: never both 200."""
    a, b = _admin(db, "a@example.com"), _admin(db, "b@example.com")
    real, gate = account_deletion.other_admin_exists, threading.Barrier(2, timeout=20)

    def checked_together(*args, **kw):
        ok = real(*args, **kw)
        gate.wait()                      # both checks are complete before either request is allowed to continue
        return ok

    monkeypatch.setattr(account_deletion, "other_admin_exists", checked_together)
    out = _run_concurrently(db, a, b)
    codes = sorted(r.status_code for r in out.values())
    assert codes in ([200, 409], [409, 409]), codes
    assert any(r.status_code == 409 and _code(r) == "last_admin" for r in out.values())
    survivors = _enabled_admins(db, a, b)
    assert len(survivors) >= 1
    assert len(survivors) == codes.count(409)          # DB state matches the responses
    for w in survivors:                  # refused requests release their claims
        assert "delete_claim_token" not in db.users.find_one({"_id": w["oid"]})


def test_one_admin_deleting_while_the_other_is_mid_deletion_leaves_one_admin(client, db, monkeypatch):
    """B has claimed but not yet checked when A runs to completion. A sees B's claim and is refused; B then proceeds."""
    a, b = _admin(db, "a@example.com"), _admin(db, "b@example.com")
    real, state = account_deletion.other_admin_exists, {"n": 0}
    lock, b_holding, release_b = threading.Lock(), threading.Event(), threading.Event()
    res = {}

    def staged(*args, **kw):
        with lock:
            state["n"] += 1
            first = state["n"] == 1
        if first:
            b_holding.set()              # B: claim published, check not yet run
            assert release_b.wait(20)
        return real(*args, **kw)

    monkeypatch.setattr(account_deletion, "other_admin_exists", staged)
    from app.main import app
    tb = threading.Thread(target=lambda: res.__setitem__("b", _delete(TestClient(app), b)))
    tb.start()
    assert b_holding.wait(20)
    res["a"] = _delete(TestClient(app), a)        # runs completely while B is parked
    assert res["a"].status_code == 409 and _code(res["a"]) == "last_admin"
    release_b.set()
    tb.join(30)
    assert res["b"].status_code == 200
    assert _exists(db, a) and not _exists(db, b)
    assert len(_enabled_admins(db, a, b)) == 1


@pytest.mark.parametrize("round_", range(12))
def test_simultaneous_self_deletion_never_leaves_zero_admins(client, db, round_):
    """Unforced timing, repeated: whatever the interleaving, at least one of the two accounts survives."""
    a, b = _admin(db, f"a{round_}@example.com"), _admin(db, f"b{round_}@example.com")
    out = _run_concurrently(db, a, b)
    codes = sorted(r.status_code for r in out.values())
    assert codes in ([200, 409], [409, 409]), codes
    assert len(_enabled_admins(db, a, b)) >= 1
    assert all(_code(r) == "last_admin" for r in out.values() if r.status_code != 200)


# ---- claim semantics ---------------------------------------------------------------------------------------------------
def test_claimed_admin_is_not_counted_as_another_admin(client, db):
    me, other = _admin(db, "me@example.com"), _admin(db, "other@example.com")
    db.users.update_one({"_id": other["oid"]}, {"$set": {"delete_claim_token": "t", "delete_claim_until": time.time() + 30}})
    r = _delete(client, me)
    assert r.status_code == 409 and _code(r) == "last_admin"
    assert _exists(db, me)


def test_expired_claim_neither_counts_nor_blocks(client, db):
    me, other = _admin(db, "me@example.com"), _admin(db, "other@example.com")
    stale = {"delete_claim_token": "old", "delete_claim_until": time.time() - 5}     # e.g. a crashed request
    db.users.update_one({"_id": other["oid"]}, {"$set": stale})
    db.users.update_one({"_id": me["oid"]}, {"$set": stale})
    assert _delete(client, me).status_code == 200            # own stale claim is replaced; the stale claim on `other` is ignored
    assert not _exists(db, me) and _exists(db, other)


def test_second_deletion_of_same_account_in_flight_is_refused(client, db):
    me, other = _admin(db, "me@example.com"), _admin(db, "other@example.com")
    db.users.update_one({"_id": me["oid"]}, {"$set": {"delete_claim_token": "inflight", "delete_claim_until": time.time() + 30}})
    r = _delete(client, me)
    assert r.status_code == 409 and _code(r) == "delete_in_progress"
    assert _exists(db, me) and db.users.find_one({"_id": me["oid"]})["delete_claim_token"] == "inflight"   # not stolen


def test_claim_is_released_when_deletion_is_refused_for_another_reason(client, db):
    me, other = _admin(db, "me@example.com"), _admin(db, "other@example.com")
    db.subscriptions.insert_one({"user_id": me["id"], "plan": "pro", "status": "active", "cancel_at_period_end": False})
    r = _delete(client, me)
    assert r.status_code == 409 and _code(r) == "active_subscription"
    assert "delete_claim_token" not in db.users.find_one({"_id": me["oid"]})
    assert "delete_claim_until" not in db.users.find_one({"_id": me["oid"]})


def test_wrong_password_never_claims(client, db):
    me, other = _admin(db, "me@example.com"), _admin(db, "other@example.com")
    r = client.request("DELETE", "/v1/me", json={"password": "wrong-password-1"}, headers=me["h"])
    assert r.status_code == 403
    assert "delete_claim_token" not in db.users.find_one({"_id": me["oid"]})


def test_expired_claim_at_tombstone_point_aborts_instead_of_deleting(client, db, monkeypatch):
    """If the request stalls past its claim, the conditional tombstone refuses: the account stays ACTIVE, nothing was deleted,
    the claim is cleared."""
    me, other = _admin(db, "me@example.com"), _admin(db, "other@example.com")
    real = account_deletion.other_admin_exists

    def then_expire(*args, **kw):
        ok = real(*args, **kw)
        db.users.update_one({"_id": me["oid"]}, {"$set": {"delete_claim_until": 0}})     # claim lapses after the check
        return ok

    monkeypatch.setattr(account_deletion, "other_admin_exists", then_expire)
    r = _delete(client, me)
    assert r.status_code == 409 and _code(r) == "delete_conflict"
    u = db.users.find_one({"_id": me["oid"]})
    assert u is not None and "delete_claim_token" not in u and not u.get("deleting")


def test_ordinary_user_deletion_claims_and_completes(client, db):
    """Claims are for every account now, not only administrators; the claim never outlives the request."""
    ann = _admin(db, "ann@example.com", is_admin=False)
    _admin(db, "keeper@example.com")
    assert _delete(client, ann).status_code == 200
    assert not _exists(db, ann)


def test_claim_fields_never_reach_the_api_response(client, db):
    me, other = _admin(db, "me@example.com"), _admin(db, "other@example.com")
    db.users.update_one({"_id": other["oid"]}, {"$set": {"delete_claim_token": "secret-token", "delete_claim_until": time.time() + 30}})
    assert "secret-token" not in client.get("/v1/me", headers=other["h"]).text
    assert "secret-token" not in client.get("/v1/admin/users", headers=me["h"]).text
