"""Email verification, provider routing/retry, password reset. The HTTP layer of Gmail and Resend is REPLACED by a fake
(no network, no credentials), so these tests prove our request building, routing, token refresh, retry and error handling
- NOT that Gmail or Resend actually deliver. Live delivery is verified separately with real credentials (see release doc)."""
import base64
import time
from email import message_from_bytes

import httpx
import pytest

from app import email_providers as ep
from app import email_service


class Resp:
    def __init__(self, status=200, body=None):
        self.status_code, self._b = status, body if body is not None else {}

    def json(self):
        return self._b

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("x", request=None, response=None)


class Net:
    """Scripted fake for httpx.post: routes by URL, records every call."""

    def __init__(self):
        self.calls, self.script = [], {}

    def on(self, url, *responses):
        self.script[url] = list(responses)

    def post(self, url, **kw):
        self.calls.append((url, kw))
        q = self.script.get(url)
        if not q:
            raise AssertionError("unexpected call " + url)
        r = q.pop(0) if len(q) > 1 else q[0]
        if isinstance(r, Exception):
            raise r
        return r

    def to(self, url):
        return [kw for u, kw in self.calls if u == url]


@pytest.fixture
def net(monkeypatch):
    n = Net()
    monkeypatch.setattr(ep.httpx, "post", n.post)
    monkeypatch.setattr(ep.time, "sleep", lambda s: None)
    ep._gmail._access, ep._gmail._expires = None, 0.0
    return n


@pytest.fixture
def gmail(monkeypatch):
    for k, v in {"GMAIL_CLIENT_ID": "cid", "GMAIL_CLIENT_SECRET": "csecret", "GMAIL_REFRESH_TOKEN": "rtok",
                 "GMAIL_SENDER": "noreply@example.test"}.items():
        monkeypatch.setenv(k, v)


@pytest.fixture
def resend(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.setenv("RESEND_FROM", "ScriptLiv <noreply@mail.example.test>")


M = ep.Message(to="someone@gmail.com", subject="Hi", text="Body https://x/verify-email?token=abc")


def _no_dev(monkeypatch):
    monkeypatch.setenv("SCRIPTLIV_DEV_RETURN_TOKENS", "0")


# ---- provider routing -------------------------------------------------------------------------------------------

def test_routing_gmail_for_normal_and_resend_for_outlook(gmail, resend):
    assert ep.provider_for("a@gmail.com").name == "gmail"
    assert ep.provider_for("a@company.org").name == "gmail"
    for d in ("outlook.com", "Hotmail.com", "live.com", "msn.com"):
        assert ep.provider_for("a@" + d).name == "resend"


def test_outlook_never_falls_back_to_gmail_when_resend_missing(gmail):
    assert ep.provider_for("a@outlook.com") is None            # not silently sent through Gmail
    assert ep.deliver(ep.Message("a@outlook.com", "s", "t"))[2] == "no_provider"


def test_nothing_configured_is_unavailable_not_success(monkeypatch):
    for k in ("GMAIL_CLIENT_ID", "RESEND_API_KEY", "SMTP_HOST"):
        monkeypatch.delenv(k, raising=False)
    assert ep.provider_for("a@gmail.com") is None


def test_resend_domains_are_configurable(gmail, resend, monkeypatch):
    monkeypatch.setenv("EMAIL_RESEND_DOMAINS", "corp.example")
    assert ep.provider_for("a@corp.example").name == "resend"
    assert ep.provider_for("a@outlook.com").name == "gmail"


# ---- Gmail API --------------------------------------------------------------------------------------------------

def test_gmail_refreshes_token_then_sends_send_only_raw_message(gmail, net):
    net.on(ep.GMAIL_TOKEN_URL, Resp(200, {"access_token": "at1", "expires_in": 3600}))
    net.on(ep.GMAIL_SEND_URL, Resp(200, {"id": "gm-1"}))
    sent, attempts, err = ep.deliver(M)
    assert (sent.provider, sent.message_id, attempts, err) == ("gmail", "gm-1", 1, None)
    tok = net.to(ep.GMAIL_TOKEN_URL)[0]["data"]
    assert tok["grant_type"] == "refresh_token" and tok["refresh_token"] == "rtok"
    send = net.to(ep.GMAIL_SEND_URL)[0]
    assert send["headers"]["Authorization"] == "Bearer at1"
    mime = message_from_bytes(base64.urlsafe_b64decode(send["json"]["raw"]))
    assert mime["To"] == "someone@gmail.com" and mime["From"] == "noreply@example.test" and mime["Subject"] == "Hi"
    assert ep.GMAIL_SCOPE.endswith("gmail.send")                # least privilege: cannot read mail


def test_gmail_reuses_access_token_until_it_expires(gmail, net):
    net.on(ep.GMAIL_TOKEN_URL, Resp(200, {"access_token": "at1", "expires_in": 3600}))
    net.on(ep.GMAIL_SEND_URL, Resp(200, {"id": "x"}))
    ep.deliver(M)
    ep.deliver(M)
    assert len(net.to(ep.GMAIL_TOKEN_URL)) == 1
    ep._gmail._expires = time.time() - 1                         # expired
    ep.deliver(M)
    assert len(net.to(ep.GMAIL_TOKEN_URL)) == 2


def test_gmail_401_triggers_one_refresh_and_retry(gmail, net):
    net.on(ep.GMAIL_TOKEN_URL, Resp(200, {"access_token": "at1", "expires_in": 3600}), Resp(200, {"access_token": "at2", "expires_in": 3600}))
    net.on(ep.GMAIL_SEND_URL, Resp(401), Resp(200, {"id": "ok"}))
    sent, attempts, err = ep.deliver(M)
    assert sent and sent.message_id == "ok" and attempts == 1
    assert [c["headers"]["Authorization"] for c in net.to(ep.GMAIL_SEND_URL)] == ["Bearer at1", "Bearer at2"]


def test_gmail_revoked_refresh_token_is_a_permanent_error_not_retried(gmail, net):
    net.on(ep.GMAIL_TOKEN_URL, Resp(400, {"error": "invalid_grant"}))
    sent, attempts, err = ep.deliver(M)
    assert sent is None and err == "gmail_refresh_token_invalid" and attempts == 1
    assert not net.to(ep.GMAIL_SEND_URL)


def test_gmail_transient_failures_retry_then_succeed(gmail, net):
    net.on(ep.GMAIL_TOKEN_URL, Resp(200, {"access_token": "at1", "expires_in": 3600}))
    net.on(ep.GMAIL_SEND_URL, Resp(503), httpx.ConnectTimeout("t"), Resp(200, {"id": "third"}))
    sent, attempts, err = ep.deliver(M)
    assert sent and sent.message_id == "third" and attempts == 3


def test_gmail_gives_up_after_max_attempts(gmail, net):
    net.on(ep.GMAIL_TOKEN_URL, Resp(200, {"access_token": "at1", "expires_in": 3600}))
    net.on(ep.GMAIL_SEND_URL, Resp(500))
    sent, attempts, err = ep.deliver(M)
    assert sent is None and attempts == ep.MAX_ATTEMPTS and err == "gmail_http_500"


# ---- Resend -----------------------------------------------------------------------------------------------------

def test_resend_request_shape_and_message_id(resend, net):
    net.on(ep.RESEND_URL, Resp(200, {"id": "re-1"}))
    sent, attempts, err = ep.deliver(ep.Message("u@outlook.com", "Hello", "Text"))
    assert (sent.provider, sent.message_id, err) == ("resend", "re-1", None)
    c = net.to(ep.RESEND_URL)[0]
    assert c["headers"]["Authorization"] == "Bearer re_test_key"
    assert c["json"] == {"from": "ScriptLiv <noreply@mail.example.test>", "to": ["u@outlook.com"], "subject": "Hello", "text": "Text"}


def test_resend_unverified_domain_or_bad_key_is_permanent(resend, net):
    net.on(ep.RESEND_URL, Resp(403, {"message": "domain not verified"}))
    sent, attempts, err = ep.deliver(ep.Message("u@outlook.com", "s", "t"))
    assert sent is None and err == "resend_unauthorized" and attempts == 1


def test_resend_429_and_5xx_are_retried(resend, net):
    net.on(ep.RESEND_URL, Resp(429), Resp(502), Resp(200, {"id": "ok"}))
    sent, attempts, err = ep.deliver(ep.Message("u@outlook.com", "s", "t"))
    assert sent and attempts == 3


def test_resend_validation_error_not_retried(resend, net):
    net.on(ep.RESEND_URL, Resp(422, {"message": "bad"}))
    assert ep.deliver(ep.Message("u@outlook.com", "s", "t"))[1:] == (1, "resend_http_422")


# ---- tokens -----------------------------------------------------------------------------------------------------

def test_token_is_hashed_in_db_single_use_and_expires(db):
    tok = email_service.issue_token(db, "u1", "verify", "a@x.test")
    row = db.email_tokens.find_one({"user_id": "u1"})
    assert tok not in str(row) and row["token_hash"] != tok and len(tok) >= 40       # only the hash is stored
    assert email_service.consume_token(db, tok, ("verify",)) is not None
    assert email_service.consume_token(db, tok, ("verify",)) is None                  # used
    t2 = email_service.issue_token(db, "u1", "verify", "a@x.test")
    db.email_tokens.update_one({"user_id": "u1", "used": False}, {"$set": {"expires_at": time.time() - 1}})
    assert email_service.consume_token(db, t2, ("verify",)) is None                   # expired
    assert email_service.consume_token(db, "garbage", ("verify",)) is None


def test_token_kind_is_enforced(db):
    tok = email_service.issue_token(db, "u1", "reset", "a@x.test")
    assert email_service.consume_token(db, tok, ("verify", "change")) is None         # a reset link cannot verify an email
    assert email_service.consume_token(db, tok, ("reset",)) is not None


def test_tokens_are_unpredictable(db):
    toks = {email_service.issue_token(db, f"u{i}", "verify", "a@x.test") for i in range(50)}
    assert len(toks) == 50


def test_new_link_invalidates_the_previous_one(db):
    a = email_service.issue_token(db, "u1", "verify", "a@x.test")
    b = email_service.issue_token(db, "u1", "verify", "a@x.test")
    assert email_service.consume_token(db, a, ("verify",)) is None
    assert email_service.consume_token(db, b, ("verify",)) is not None


def test_ttl_index_exists(db):
    info = db.email_tokens.index_information()
    assert any(v.get("expireAfterSeconds") == 86400 for v in info.values())


def test_reset_token_lives_one_hour_verify_24(db):
    email_service.issue_token(db, "u1", "reset", "a@x.test")
    email_service.issue_token(db, "u1", "verify", "a@x.test")
    r = {x["kind"]: x["expires_at"] - x["created_at"] for x in db.email_tokens.find({})}
    assert round(r["reset"]) == 3600 and round(r["verify"]) == 86400


# ---- end-to-end through the API (fake HTTP) -----------------------------------------------------------------------

def _token_from_gmail_call(net):
    raw = net.to(ep.GMAIL_SEND_URL)[-1]["json"]["raw"]
    body = message_from_bytes(base64.urlsafe_b64decode(raw)).get_payload(decode=True).decode()
    return body.split("token=")[1].split()[0]


def test_register_sends_verification_link_that_verifies(client, gmail, net, monkeypatch, db):
    _no_dev(monkeypatch)
    net.on(ep.GMAIL_TOKEN_URL, Resp(200, {"access_token": "at", "expires_in": 3600}))
    net.on(ep.GMAIL_SEND_URL, Resp(200, {"id": "m1"}))
    r = client.post("/v1/auth/register", json={"name": "Ann", "email": "ann@gmail.com", "password": "correct-horse-1"})
    assert r.status_code == 201 and r.json()["verification"] == {"delivery": "email"}       # no token leaks to the client
    assert r.json()["user"]["email_verified"] is False
    tok = _token_from_gmail_call(net)
    assert client.post("/v1/auth/verify-email", json={"token": tok}).status_code == 200
    again = client.post("/v1/auth/verify-email", json={"token": tok})                         # single use
    assert again.status_code == 400 and again.json()["error"]["code"] == "invalid_token"
    assert db.users.find_one({"email": "ann@gmail.com"})["email_verified"] is True
    log = db.email_deliveries.find_one({})
    assert log["status"] == "sent" and log["provider"] == "gmail" and log["message_id"] == "m1" and tok not in str(log)


def test_outlook_user_gets_mail_through_resend(client, gmail, resend, net, monkeypatch, db):
    _no_dev(monkeypatch)
    net.on(ep.RESEND_URL, Resp(200, {"id": "re-9"}))
    r = client.post("/v1/auth/register", json={"name": "Olly", "email": "olly@outlook.com", "password": "correct-horse-1"})
    assert r.json()["verification"] == {"delivery": "email"}
    assert not net.to(ep.GMAIL_SEND_URL) and len(net.to(ep.RESEND_URL)) == 1
    assert db.email_deliveries.find_one({})["provider"] == "resend"


def test_delivery_failure_is_reported_honestly_and_logged(client, resend, net, monkeypatch, db):
    _no_dev(monkeypatch)
    net.on(ep.RESEND_URL, Resp(500))
    r = client.post("/v1/auth/register", json={"name": "Olly", "email": "olly@outlook.com", "password": "correct-horse-1"})
    assert r.status_code == 201 and r.json()["verification"] == {"delivery": "failed"}
    log = db.email_deliveries.find_one({})
    assert log["status"] == "failed" and log["attempts"] == ep.MAX_ATTEMPTS and log["error"] == "resend_http_500"


def test_register_gives_no_session_login_blocked_until_verified(client, gmail, net, monkeypatch):
    _no_dev(monkeypatch)
    net.on(ep.GMAIL_TOKEN_URL, Resp(200, {"access_token": "at", "expires_in": 3600}))
    net.on(ep.GMAIL_SEND_URL, Resp(200, {"id": "m"}))
    reg = client.post("/v1/auth/register", json={"name": "Ann", "email": "ann@gmail.com", "password": "correct-horse-1"})
    assert reg.status_code == 201 and "token" not in reg.json() and reg.json()["verification_required"] is True
    login = {"email": "ann@gmail.com", "password": "correct-horse-1"}
    r = client.post("/v1/auth/login", json=login)
    assert r.status_code == 403 and r.json()["error"]["code"] == "email_not_verified" and "token" not in r.text
    # wrong password still looks like any other bad login (verification state is not leaked to guessers)
    assert client.post("/v1/auth/login", json={**login, "password": "wrong-wrong-1"}).status_code == 401
    # signed-out resend: same reply for a real unverified account and an unknown one
    known = client.post("/v1/auth/resend-verification", json={"email": "ann@gmail.com"})
    unknown = client.post("/v1/auth/resend-verification", json={"email": "nobody@gmail.com"})
    assert known.status_code == unknown.status_code == 202 and known.json() == unknown.json()
    assert len(net.to(ep.GMAIL_SEND_URL)) == 2                                                  # register mail + one resend
    assert client.post("/v1/auth/verify-email", json={"token": _token_from_gmail_call(net)}).status_code == 200
    ok = client.post("/v1/auth/login", json=login)
    assert ok.status_code == 200 and ok.json()["token"] and ok.json()["user"]["email_verified"] is True
    # a verified account gets no further mail from the public resend
    client.post("/v1/auth/resend-verification", json={"email": "ann@gmail.com"})
    assert len(net.to(ep.GMAIL_SEND_URL)) == 2


# ---- forgot / reset password -----------------------------------------------------------------------------------

def test_forgot_password_does_not_reveal_whether_account_exists(client, user, gmail, net, monkeypatch):
    _no_dev(monkeypatch)
    net.on(ep.GMAIL_TOKEN_URL, Resp(200, {"access_token": "at", "expires_in": 3600}))
    net.on(ep.GMAIL_SEND_URL, Resp(200, {"id": "m"}))
    known = client.post("/v1/auth/forgot-password", json={"email": "ann@example.com"})
    unknown = client.post("/v1/auth/forgot-password", json={"email": "nobody@example.com"})
    assert known.status_code == unknown.status_code == 202 and known.json() == unknown.json()
    assert len(net.to(ep.GMAIL_SEND_URL)) == 1                                                   # mail only for the real account


def test_reset_flow_changes_password_signs_out_old_sessions_and_link_is_single_use(client, user, gmail, net, monkeypatch):
    _no_dev(monkeypatch)
    net.on(ep.GMAIL_TOKEN_URL, Resp(200, {"access_token": "at", "expires_in": 3600}))
    net.on(ep.GMAIL_SEND_URL, Resp(200, {"id": "m"}))
    client.post("/v1/auth/forgot-password", json={"email": "ann@example.com"})
    tok = _token_from_gmail_call(net)
    assert client.get("/v1/me", headers=user["h"]).status_code == 200
    weak = client.post("/v1/auth/reset-password", json={"token": tok, "new_password": "short"})
    assert weak.status_code == 422                                                              # does not burn the link
    ok = client.post("/v1/auth/reset-password", json={"token": tok, "new_password": "brand-new-pass-9"})
    assert ok.status_code == 200
    assert client.get("/v1/me", headers=user["h"]).status_code == 401                          # old session revoked
    assert client.post("/v1/auth/login", json={"email": "ann@example.com", "password": "correct-horse-1"}).status_code == 401
    assert client.post("/v1/auth/login", json={"email": "ann@example.com", "password": "brand-new-pass-9"}).status_code == 200
    again = client.post("/v1/auth/reset-password", json={"token": tok, "new_password": "another-pass-77"})
    assert again.status_code == 400 and again.json()["error"]["code"] == "invalid_token"


def test_reset_rejects_expired_and_wrong_kind_tokens(client, user, db):
    verify_tok = email_service.issue_token(db, user["id"], "verify", "ann@example.com")
    assert client.post("/v1/auth/reset-password", json={"token": verify_tok, "new_password": "brand-new-pass-9"}).status_code == 400
    t = email_service.issue_token(db, user["id"], "reset", "ann@example.com")
    db.email_tokens.update_one({"kind": "reset", "used": False}, {"$set": {"expires_at": time.time() - 5}})
    assert client.post("/v1/auth/reset-password", json={"token": t, "new_password": "brand-new-pass-9"}).status_code == 400


def test_forgot_password_is_throttled(client, user):
    codes = [client.post("/v1/auth/forgot-password", json={"email": "ann@example.com"}).status_code for _ in range(7)]
    assert codes[:5] == [202] * 5 and codes[5] == 429


def test_dev_token_never_returned_when_flag_off(client, user, gmail, net, monkeypatch):
    _no_dev(monkeypatch)
    net.on(ep.GMAIL_TOKEN_URL, Resp(200, {"access_token": "at", "expires_in": 3600}))
    net.on(ep.GMAIL_SEND_URL, Resp(200, {"id": "m"}))
    j = client.post("/v1/auth/forgot-password", json={"email": "ann@example.com"}).json()
    assert "dev_token" not in j and "token" not in str(j)
