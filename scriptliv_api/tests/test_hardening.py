import pytest

from app import config, throttle
from app.db import get_db


def _good():
    s = config.Settings()
    s.mongodb_uri = "mongodb+srv://u:p@h/db"
    s.jwt_secret = "j" * 40
    s.relay_secret = "r" * 24
    s.app_base_url = "https://scriptliv.com"
    s.cors_origins = ["https://scriptliv.com"]
    s.dev_return_tokens = False
    s.cashfree_live = False
    return s


def test_production_accepts_a_proper_config():
    assert config.production_problems(_good(), env={}) == []


@pytest.mark.parametrize("attr,value,needle", [
    ("mongodb_uri", "", "MONGODB_URI"),
    ("jwt_secret", "short", "JWT_SECRET"),
    ("relay_secret", "x", "RELAY_SECRET"),
    ("app_base_url", "http://localhost:3100", "APP_URL"),
    ("cors_origins", ["http://localhost:3100"], "CORS"),
    ("cors_origins", [], "CORS"),
    ("dev_return_tokens", True, "DEV_RETURN_TOKENS"),
])
def test_production_rejects_unsafe_settings(attr, value, needle):
    s = _good()
    setattr(s, attr, value)
    assert any(needle in p for p in config.production_problems(s, env={}))


def test_production_rejects_docs_and_test_keys_in_live_mode():
    assert any("ENABLE_DOCS" in p for p in config.production_problems(_good(), env={"SCRIPTLIV_ENABLE_DOCS": "1"}))
    s = _good()
    s.cashfree_live, s.cashfree_app_id = True, "TEST123"
    assert any("test key" in p for p in config.production_problems(s, env={}))


def test_healthz_reports_database_state(client, monkeypatch):
    assert client.get("/healthz").json() == {"ok": True}

    class Dead:
        def command(self, *_):
            raise RuntimeError("down")
    monkeypatch.setattr("app.main.get_db", lambda: Dead())
    r = client.get("/healthz")
    assert r.status_code == 503 and r.json()["ok"] is False


def test_throttle_is_stored_in_the_database_and_blocks(db):
    for _ in range(3):
        throttle.hit("k:test", limit=3)
    assert db.throttle.count_documents({"key": "k:test"}) == 3
    with pytest.raises(Exception) as e:
        throttle.hit("k:test", limit=3)
    assert getattr(e.value, "status_code", None) == 429
    throttle.forget("k:test")
    throttle.hit("k:test", limit=3)


def test_login_is_limited_per_ip_even_with_different_emails(client):
    codes = [client.post("/v1/auth/login", json={"email": f"u{i}@example.com", "password": "nope-nope-1"}).status_code
             for i in range(32)]
    assert codes[0] == 401 and codes[-1] == 429


def test_forwarded_header_is_ignored_unless_proxy_is_trusted(client, monkeypatch):
    def burn(ip, n=31):
        return [client.post("/v1/auth/login", json={"email": f"v{ip}{i}@example.com", "password": "nope-nope-1"},
                            headers={"X-Forwarded-For": ip}).status_code for i in range(n)]
    assert 429 in burn("1.1.1.1")           # untrusted: the header does not give a new bucket
    assert 429 in burn("2.2.2.2")
    monkeypatch.setenv("SCRIPTLIV_TRUST_PROXY", "1")
    assert 429 not in burn("3.3.3.3", 30)       # trusted: each forwarded address has its own bucket
