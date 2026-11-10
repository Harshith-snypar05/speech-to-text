import mongomock
import pytest
from fastapi.testclient import TestClient

from app import db as dbmod

SECRETS = {"SCRIPTLIV_JWT_SECRET": "test-jwt-secret-not-real-0123456789abcdef", "SCRIPTLIV_RELAY_SECRET": "test-relay-secret",
           "SCRIPTLIV_DEV_RETURN_TOKENS": "1"}


@pytest.fixture(autouse=True)
def env(monkeypatch):
    for k, v in SECRETS.items():
        monkeypatch.setenv(k, v)
    for k in ("STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET", "SMTP_HOST"):
        monkeypatch.delenv(k, raising=False)


@pytest.fixture(autouse=True)
def fresh_throttle():
    from app.routers import account
    account._attempts.clear()
    yield


@pytest.fixture
def db():
    d = mongomock.MongoClient().scriptliv_test
    dbmod.set_db(d)
    yield d
    dbmod._db = None


@pytest.fixture
def client(db):
    from app.main import app
    return TestClient(app)


def _register(client, email="ann@example.com"):
    r = client.post("/v1/auth/register", json={"name": "Ann", "email": email, "password": "correct-horse-1"})
    assert r.status_code == 201, r.text
    j = r.json()
    assert "token" not in j and j["verification_required"] is True   # registering never signs in
    from app.security import make_token
    tok = make_token(j["user"]["id"], 1)   # a token for an account that is still unverified (defence-in-depth tests)
    return {"id": j["user"]["id"], "token": tok, "h": {"Authorization": "Bearer " + tok}, "verify": j["verification"]}


@pytest.fixture
def unverified_user(client):
    """Registered, email not yet verified (holds a hand-minted token; real login is refused until verified)."""
    return _register(client)


@pytest.fixture
def user(client):
    """A signed-in customer whose email has been verified through the real verification flow."""
    u = _register(client)
    assert client.post("/v1/auth/verify-email", json={"token": u["verify"]["dev_token"]}).status_code == 200
    return u
