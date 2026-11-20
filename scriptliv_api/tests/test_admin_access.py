"""Admin authorization is driven by SCRIPTLIV_ADMIN_EMAILS and fails closed; admin user search treats input literally."""
import pytest

from app.deps import admin_emails, is_admin_email

from .conftest import _register


def _verified(client, email):
    u = _register(client, email)
    assert client.post("/v1/auth/verify-email", json={"token": u["verify"]["dev_token"]}).status_code == 200
    return u


@pytest.mark.parametrize("raw", ["", "   ", ",,,", "not-an-email", "@x.com", "a@", "a@@b.com", "a b@c.com"])
def test_missing_or_invalid_config_grants_nothing(monkeypatch, raw):
    monkeypatch.setenv("SCRIPTLIV_ADMIN_EMAILS", raw)
    assert admin_emails() == frozenset()
    assert not is_admin_email("a@b.com") and not is_admin_email("") and not is_admin_email(None)


def test_unset_config_grants_nothing(monkeypatch):
    monkeypatch.delenv("SCRIPTLIV_ADMIN_EMAILS", raising=False)
    assert admin_emails() == frozenset()


def test_parsing_is_case_and_space_tolerant_and_skips_bad_entries(monkeypatch):
    monkeypatch.setenv("SCRIPTLIV_ADMIN_EMAILS", " Boss@Example.com , junk,, other@example.com ")
    assert admin_emails() == frozenset({"boss@example.com", "other@example.com"})
    assert is_admin_email("BOSS@example.com")
    assert not is_admin_email("junk")


def test_configured_email_is_admin_and_others_are_not(client, monkeypatch):
    monkeypatch.setenv("SCRIPTLIV_ADMIN_EMAILS", "boss@example.com")
    boss = _verified(client, "boss@example.com")
    ann = _verified(client, "ann@example.com")
    assert client.get("/v1/admin/analytics", headers=boss["h"]).status_code == 200
    assert client.get("/v1/admin/analytics", headers=ann["h"]).status_code == 403
    assert client.get("/v1/me", headers=boss["h"]).json()["user"]["is_admin"] is True
    assert client.get("/v1/me", headers=ann["h"]).json()["user"]["is_admin"] is False


def test_empty_config_does_not_make_anyone_admin(client, monkeypatch):
    monkeypatch.setenv("SCRIPTLIV_ADMIN_EMAILS", "")
    u = _verified(client, "boss@example.com")
    assert client.get("/v1/admin/analytics", headers=u["h"]).status_code == 403
    assert client.get("/v1/admin/users", headers=u["h"]).status_code == 403


def test_admin_requires_auth(client):
    assert client.get("/v1/admin/users").status_code == 401


def test_db_flag_admin_survives_config_removal(client, db, monkeypatch):
    """An admin already persisted in the database keeps access if the env var is later unset (current behaviour kept)."""
    monkeypatch.setenv("SCRIPTLIV_ADMIN_EMAILS", "boss@example.com")
    boss = _verified(client, "boss@example.com")
    assert client.get("/v1/admin/analytics", headers=boss["h"]).status_code == 200   # persists is_admin
    monkeypatch.delenv("SCRIPTLIV_ADMIN_EMAILS")
    assert client.get("/v1/admin/analytics", headers=boss["h"]).status_code == 200


@pytest.mark.parametrize("q", [".*", "(", "[a-", "a+++++++++++++++++++++b(", "\\", "^$", "(a+)+$", "x" * 500])
def test_admin_search_treats_input_literally(client, monkeypatch, q):
    monkeypatch.setenv("SCRIPTLIV_ADMIN_EMAILS", "boss@example.com")
    boss = _verified(client, "boss@example.com")
    _verified(client, "ann@example.com")
    r = client.get("/v1/admin/users", params={"q": q}, headers=boss["h"])
    assert r.status_code == 200, r.text
    assert r.json()["count"] == 0          # metacharacters match nothing instead of everything / erroring


def test_admin_search_still_finds_by_email_and_name(client, monkeypatch):
    monkeypatch.setenv("SCRIPTLIV_ADMIN_EMAILS", "boss@example.com")
    boss = _verified(client, "boss@example.com")
    _verified(client, "ann@example.com")
    r = client.get("/v1/admin/users", params={"q": "ANN@example.com"}, headers=boss["h"])
    assert [u["email"] for u in r.json()["users"]] == ["ann@example.com"]
    assert client.get("/v1/admin/users", params={"q": "ann@"}, headers=boss["h"]).json()["count"] == 1
