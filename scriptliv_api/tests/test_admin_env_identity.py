"""Environment-listed administrators: protected identity vs usable-admin status, and email normalization.

Users are inserted directly (precomputed password hash) so the account state is exactly what each test describes, e.g. an
env-listed admin who has never made a request and therefore has no persisted is_admin flag.
"""
import time

import pytest
from bson import ObjectId

from app.security import hash_password, make_token

from .conftest import _register

PW = "correct-horse-1"
PWHASH = hash_password(PW)


def _user(db, email, **extra):
    doc = {"name": "U", "email": email, "email_verified": True, "pwhash": PWHASH, "pwv": 1, "created_at": time.time(), "disabled": False, **extra}
    oid = db.users.insert_one(doc).inserted_id
    return {"oid": oid, "id": str(oid), "email": email, "h": {"Authorization": "Bearer " + make_token(str(oid), 1)}}


def _doc(db, u):
    return db.users.find_one({"_id": u["oid"]})


def _patch(client, target, body, who):
    return client.patch(f"/v1/admin/users/{target['id']}", json=body, headers=who["h"])


def _row(client, email, who):
    return next(r for r in client.get("/v1/admin/users", headers=who["h"]).json()["users"] if r["email"] == email)


def _delete(client, who):
    return client.request("DELETE", "/v1/me", json={"password": PW}, headers=who["h"])


def _protected(r):
    assert r.status_code == 403 and r.json()["error"]["code"] == "protected_account", r.text


@pytest.fixture(autouse=True)
def boss_is_env_admin(env, monkeypatch):
    monkeypatch.setenv("SCRIPTLIV_ADMIN_EMAILS", "boss@example.com")


# ---- env admin who has never made a request ----------------------------------------------------------------------------
def test_env_admin_who_never_made_a_request_is_protected_and_listed_as_admin(client, db):
    dba = _user(db, "dba@example.com", is_admin=True)
    boss = _user(db, "boss@example.com")                      # env-listed, never authenticated: no is_admin in the DB
    assert "is_admin" not in _doc(db, boss)
    row = _row(client, "boss@example.com", dba)
    assert row["is_admin"] is True and row["protected"] is True
    _protected(_patch(client, boss, {"disabled": True}, dba))
    _protected(_patch(client, boss, {"is_admin": False}, dba))
    d = _doc(db, boss)
    assert not d.get("disabled") and "is_admin" not in d, "rejected requests and listing must not write to the account"


def test_env_admin_never_seen_still_counts_as_another_admin_for_self_delete(client, db):
    dba = _user(db, "dba@example.com", is_admin=True)
    boss = _user(db, "boss@example.com")
    assert "is_admin" not in _doc(db, boss)
    assert _delete(client, dba).status_code == 200
    assert _doc(db, dba) is None and _doc(db, boss) is not None


def test_env_admin_who_never_made_a_request_can_use_admin_api_and_is_then_persisted(client, db):
    boss = _user(db, "boss@example.com")
    assert client.get("/v1/admin/users", headers=boss["h"]).status_code == 200
    assert _doc(db, boss)["is_admin"] is True                # existing behaviour of current_user, unchanged


# ---- env admin targeted by another admin -------------------------------------------------------------------------------
def test_env_admin_is_protected_from_a_db_admin(client, db):
    dba, boss = _user(db, "dba@example.com", is_admin=True), _user(db, "boss@example.com", is_admin=True)
    _protected(_patch(client, boss, {"disabled": True}, dba))
    _protected(_patch(client, boss, {"is_admin": False}, dba))
    assert _row(client, "boss@example.com", dba)["protected"] is True
    assert client.get("/v1/admin/analytics", headers=boss["h"]).status_code == 200


# ---- env admin counted correctly in the last-admin guard ---------------------------------------------------------------
def test_sole_db_admin_with_only_a_disabled_env_admin_is_the_last_admin(client, db):
    dba = _user(db, "dba@example.com", is_admin=True)
    _user(db, "boss@example.com", disabled=True)               # listed, but not usable
    r = _delete(client, dba)
    assert r.status_code == 409 and r.json()["error"]["code"] == "last_admin"
    assert _doc(db, dba) is not None


def test_env_admin_self_delete_blocked_when_no_other_usable_admin(client, db):
    boss = _user(db, "boss@example.com")
    _user(db, "dba@example.com", is_admin=True, disabled=True)
    r = _delete(client, boss)
    assert r.status_code == 409 and r.json()["error"]["code"] == "last_admin"
    assert _doc(db, boss) is not None


def test_env_admin_self_delete_allowed_when_a_db_admin_is_usable(client, db):
    boss, dba = _user(db, "boss@example.com"), _user(db, "dba@example.com", is_admin=True)
    assert _delete(client, boss).status_code == 200
    assert _doc(db, boss) is None and _doc(db, dba) is not None


# ---- email case and whitespace -----------------------------------------------------------------------------------------
def test_env_list_matching_ignores_case_and_surrounding_whitespace(client, db, monkeypatch):
    monkeypatch.setenv("SCRIPTLIV_ADMIN_EMAILS", "  Boss@Example.COM ,, other@example.com ")
    boss, dba = _user(db, "boss@example.com"), _user(db, "dba@example.com", is_admin=True)
    assert _row(client, "boss@example.com", dba)["protected"] is True
    _protected(_patch(client, boss, {"disabled": True}, dba))
    assert client.get("/v1/admin/users", headers=boss["h"]).status_code == 200


def test_registration_lowercases_mixed_case_email_so_env_match_holds(client, db):
    u = _register(client, "BoSs@Example.Com")
    stored = db.users.find_one({"_id": ObjectId(u["id"])})
    assert stored["email"] == "boss@example.com"
    assert client.get("/v1/admin/analytics", headers=u["h"]).status_code == 200


def test_mixed_case_login_reaches_the_same_env_admin_account(client, db):
    u = _register(client, "boss@example.com")
    assert client.post("/v1/auth/verify-email", json={"token": u["verify"]["dev_token"]}).status_code == 200
    r = client.post("/v1/auth/login", json={"email": "BOSS@EXAMPLE.COM", "password": PW})
    assert r.status_code == 200, r.text
    assert client.get("/v1/admin/analytics", headers={"Authorization": "Bearer " + r.json()["token"]}).status_code == 200


def test_mixed_case_stored_email_is_still_a_protected_admin_but_does_not_count_as_another_admin(client, db):
    """Legacy row stored as 'Boss@Example.com' (the API never writes this): protected, and the guard errs on the safe side."""
    dba = _user(db, "dba@example.com", is_admin=True)
    legacy = _user(db, "Boss@Example.com")
    assert _row(client, "Boss@Example.com", dba)["protected"] is True
    _protected(_patch(client, legacy, {"disabled": True}, dba))
    r = _delete(client, dba)                                   # conservative: refuses rather than risk zero admins
    assert r.status_code == 409 and r.json()["error"]["code"] == "last_admin"


# ---- disabled env-listed account: protected identity vs usable admin ---------------------------------------------------
def test_disabled_env_admin_stays_protected_but_can_be_re_enabled(client, db):
    dba = _user(db, "dba@example.com", is_admin=True)
    boss = _user(db, "boss@example.com", disabled=True)
    row = _row(client, "boss@example.com", dba)
    assert row["protected"] is True and row["is_admin"] is True and row["disabled"] is True
    _protected(_patch(client, boss, {"is_admin": False}, dba))
    r = _patch(client, boss, {"disabled": False}, dba)
    assert r.status_code == 200 and r.json()["disabled"] is False
    assert _doc(db, boss)["disabled"] is False


def test_disabled_env_admin_cannot_authenticate_or_use_admin_api(client, db):
    boss = _user(db, "boss@example.com", disabled=True)
    assert client.get("/v1/admin/users", headers=boss["h"]).status_code == 401
    assert client.get("/v1/me", headers=boss["h"]).status_code == 401
    assert "is_admin" not in _doc(db, boss)                    # never reached the auto-persist


def test_disabling_is_still_refused_for_an_enabled_env_admin(client, db):
    dba, boss = _user(db, "dba@example.com", is_admin=True), _user(db, "boss@example.com")
    _protected(_patch(client, boss, {"disabled": True}, dba))
    assert not _doc(db, boss).get("disabled")
