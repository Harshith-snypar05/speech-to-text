"""Administrator accounts and the caller's own account cannot be disabled or demoted through the general access endpoint;
the final administrator cannot delete their own account. Authorization is enforced by the API, not by the web page."""
import pytest
from bson import ObjectId

from .conftest import _register

PW = "correct-horse-1"


def _verified(client, email):
    u = _register(client, email)
    assert client.post("/v1/auth/verify-email", json={"token": u["verify"]["dev_token"]}).status_code == 200
    return u


def _set_admin(db, uid, value=True):
    db.users.update_one({"_id": ObjectId(uid)}, {"$set": {"is_admin": value}})


@pytest.fixture
def world(client, db, monkeypatch):
    """boss = env-listed admin (default caller), dba = database-flag admin, ann = ordinary user."""
    monkeypatch.setenv("SCRIPTLIV_ADMIN_EMAILS", "boss@example.com")
    w = {"boss": _verified(client, "boss@example.com"), "dba": _verified(client, "dba@example.com"), "ann": _verified(client, "ann@example.com")}
    _set_admin(db, w["dba"]["id"])
    w["patch"] = lambda target, body, who="boss": client.patch(f"/v1/admin/users/{w[target]['id']}", json=body, headers=w[who]["h"])
    w["row"] = lambda email, who="boss": next(u for u in client.get("/v1/admin/users", headers=w[who]["h"]).json()["users"] if u["email"] == email)
    return w


def _assert_protected(r):
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "protected_account"


# ---- environment-listed administrator ----------------------------------------------------------------------------------
def test_env_admin_cannot_be_disabled_by_another_admin(client, world, db):
    _assert_protected(world["patch"]("boss", {"disabled": True}, who="dba"))
    assert not db.users.find_one({"_id": ObjectId(world["boss"]["id"])}).get("disabled")


def test_env_admin_cannot_be_demoted_by_another_admin(client, world, db):
    _assert_protected(world["patch"]("boss", {"is_admin": False}, who="dba"))
    assert client.get("/v1/admin/analytics", headers=world["boss"]["h"]).status_code == 200


# ---- database administrator --------------------------------------------------------------------------------------------
def test_db_admin_cannot_be_disabled(client, world, db):
    _assert_protected(world["patch"]("dba", {"disabled": True}))
    assert not db.users.find_one({"_id": ObjectId(world["dba"]["id"])}).get("disabled")


def test_db_admin_cannot_be_demoted(client, world, db):
    _assert_protected(world["patch"]("dba", {"is_admin": False}))
    assert db.users.find_one({"_id": ObjectId(world["dba"]["id"])})["is_admin"] is True


def test_rejected_request_writes_nothing_even_with_other_changes(client, world, db):
    before = db.subscriptions.find_one({"user_id": world["dba"]["id"]})
    _assert_protected(world["patch"]("dba", {"is_admin": False, "email_verified": True, "grant_addon_minutes": 5, "plan": "pro"}))
    assert db.addons.count_documents({"user_id": world["dba"]["id"]}) == 0
    assert db.subscriptions.find_one({"user_id": world["dba"]["id"]}) == before        # plan untouched too


# ---- the caller --------------------------------------------------------------------------------------------------------
def test_caller_cannot_disable_self(client, world, db):
    _assert_protected(world["patch"]("boss", {"disabled": True}))
    assert client.get("/v1/me", headers=world["boss"]["h"]).status_code == 200


def test_caller_cannot_demote_self(client, world, db):
    _assert_protected(world["patch"]("boss", {"is_admin": False}))
    assert db.users.find_one({"_id": ObjectId(world["boss"]["id"])}).get("is_admin") is not False


def test_database_admin_caller_cannot_disable_or_demote_self(client, world):
    _assert_protected(world["patch"]("dba", {"disabled": True}, who="dba"))
    _assert_protected(world["patch"]("dba", {"is_admin": False}, who="dba"))


# ---- ordinary users stay manageable, harmless changes to protected accounts stay possible ------------------------------
def test_normal_user_remains_manageable(client, world, db):
    assert world["patch"]("ann", {"disabled": True}).status_code == 200
    assert db.users.find_one({"_id": ObjectId(world["ann"]["id"])})["disabled"] is True
    assert world["patch"]("ann", {"disabled": False}).status_code == 200
    r = world["patch"]("ann", {"is_admin": True, "email_verified": True, "plan": "pro", "grant_addon_minutes": 10})
    assert r.status_code == 200 and r.json()["is_admin"] is True and r.json()["plan"] == "pro"
    assert db.addons.count_documents({"user_id": world["ann"]["id"]}) == 1


def test_promoted_user_becomes_protected(client, world):
    assert world["patch"]("ann", {"is_admin": True}).status_code == 200
    _assert_protected(world["patch"]("ann", {"is_admin": False}))
    _assert_protected(world["patch"]("ann", {"disabled": True}))


def test_noop_and_non_destructive_changes_on_protected_accounts_are_allowed(client, world):
    assert world["patch"]("dba", {"is_admin": True, "disabled": False}).status_code == 200
    assert world["patch"]("boss", {"email_verified": True, "grant_addon_minutes": 1}).status_code == 200


# ---- the `protected` property ------------------------------------------------------------------------------------------
def test_protected_property_in_user_list(client, world):
    assert world["row"]("boss@example.com")["protected"] is True      # env admin and caller
    assert world["row"]("dba@example.com")["protected"] is True       # database admin
    assert world["row"]("ann@example.com")["protected"] is False      # ordinary user


def test_protected_follows_admin_status(client, world, db):
    _set_admin(db, world["ann"]["id"])
    assert world["row"]("ann@example.com")["protected"] is True
    _set_admin(db, world["ann"]["id"], False)
    assert world["row"]("ann@example.com")["protected"] is False


def test_protected_property_in_patch_response(client, world):
    assert world["patch"]("ann", {"email_verified": True}).json()["protected"] is False
    assert world["patch"]("dba", {"email_verified": True}).json()["protected"] is True
    assert world["patch"]("ann", {"is_admin": True}).json()["protected"] is True


def test_protected_does_not_depend_on_env_when_db_flag_set(client, world, monkeypatch):
    monkeypatch.delenv("SCRIPTLIV_ADMIN_EMAILS")
    assert world["row"]("dba@example.com", who="dba")["protected"] is True


# ---- authorization is enforced by the API ------------------------------------------------------------------------------
def test_non_admin_gets_403_on_every_admin_endpoint(client, world):
    h = world["ann"]["h"]
    assert client.get("/v1/admin/analytics", headers=h).status_code == 403
    assert client.get("/v1/admin/users", headers=h).status_code == 403
    assert client.get("/v1/admin/sessions", headers=h).status_code == 403
    assert client.patch(f"/v1/admin/users/{world['ann']['id']}", json={"is_admin": True}, headers=h).status_code == 403   # no self-promotion
    assert client.patch(f"/v1/admin/users/{world['dba']['id']}", json={"disabled": True}, headers=h).status_code == 403
    assert client.delete("/v1/admin/sessions/anything", headers=h).status_code == 403


def test_unauthenticated_gets_401_on_admin_patch(client, world):
    assert client.patch(f"/v1/admin/users/{world['ann']['id']}", json={"disabled": True}).status_code == 401


def test_missing_env_config_fails_closed_but_db_admin_protection_holds(client, world, monkeypatch):
    monkeypatch.setenv("SCRIPTLIV_ADMIN_EMAILS", "")
    assert client.get("/v1/admin/users", headers=world["ann"]["h"]).status_code == 403
    _assert_protected(world["patch"]("dba", {"is_admin": False}, who="dba"))


def test_invalid_env_config_fails_closed(client, db, monkeypatch):
    monkeypatch.setenv("SCRIPTLIV_ADMIN_EMAILS", "not-an-email, @x.com ,a@@b.com")
    u = _verified(client, "boss@example.com")
    assert client.get("/v1/admin/users", headers=u["h"]).status_code == 403
    assert client.patch(f"/v1/admin/users/{u['id']}", json={"is_admin": True}, headers=u["h"]).status_code == 403
    assert not db.users.find_one({"_id": ObjectId(u["id"])}).get("is_admin")


# ---- the last administrator cannot be removed through any path ---------------------------------------------------------
def test_last_admin_cannot_be_demoted_or_disabled_by_anyone(client, db, monkeypatch):
    monkeypatch.setenv("SCRIPTLIV_ADMIN_EMAILS", "")
    only = _verified(client, "only@example.com")
    _set_admin(db, only["id"])
    for body in ({"is_admin": False}, {"disabled": True}):
        _assert_protected(client.patch(f"/v1/admin/users/{only['id']}", json=body, headers=only["h"]))


def test_last_admin_cannot_delete_own_account(client, db, monkeypatch):
    monkeypatch.setenv("SCRIPTLIV_ADMIN_EMAILS", "")
    only = _verified(client, "only@example.com")
    _set_admin(db, only["id"])
    r = client.request("DELETE", "/v1/me", json={"password": PW}, headers=only["h"])
    assert r.status_code == 409 and r.json()["error"]["code"] == "last_admin"
    assert db.users.find_one({"_id": ObjectId(only["id"])}) is not None


def test_admin_can_delete_own_account_when_another_admin_exists(client, world, db):
    r = client.request("DELETE", "/v1/me", json={"password": PW}, headers=world["dba"]["h"])
    assert r.status_code == 200
    assert db.users.find_one({"_id": ObjectId(world["dba"]["id"])}) is None


def test_disabled_admin_does_not_count_as_another_admin(client, world, db, monkeypatch):
    monkeypatch.setenv("SCRIPTLIV_ADMIN_EMAILS", "")
    db.users.update_one({"_id": ObjectId(world["boss"]["id"])}, {"$set": {"is_admin": False}})
    db.users.update_one({"_id": ObjectId(world["dba"]["id"])}, {"$set": {"disabled": True}})     # simulated direct DB state
    _set_admin(db, world["ann"]["id"])
    r = client.request("DELETE", "/v1/me", json={"password": PW}, headers=world["ann"]["h"])
    assert r.status_code == 409 and r.json()["error"]["code"] == "last_admin"


def test_ordinary_user_can_still_delete_account(client, world, db):
    assert client.request("DELETE", "/v1/me", json={"password": PW}, headers=world["ann"]["h"]).status_code == 200
