from app import usage

R = {"X-Relay-Secret": "test-relay-secret"}


def test_register_login_me_and_no_secrets_leak(client, user):
    r = client.get("/v1/me", headers=user["h"])
    assert r.status_code == 200 and "pwhash" not in r.text and "pwv" not in r.text
    assert client.post("/v1/auth/register", json={"name": "A", "email": "ANN@example.com", "password": "correct-horse-1"}).status_code == 409
    assert client.post("/v1/auth/login", json={"email": "ann@example.com", "password": "nope"}).status_code == 401
    assert client.post("/v1/auth/login", json={"email": "ann@example.com", "password": "correct-horse-1"}).status_code == 200


def test_requires_auth(client):
    for p in ("/v1/me", "/v1/usage", "/v1/sessions", "/v1/settings", "/v1/subscription"):
        assert client.get(p).status_code == 401


def test_weak_password_rejected(client):
    assert client.post("/v1/auth/register", json={"name": "A", "email": "b@example.com", "password": "short"}).status_code == 422


def test_email_verification_flow(client, unverified_user):
    user = unverified_user
    assert client.get("/v1/me", headers=user["h"]).json()["user"]["email_verified"] is False
    tok = user["verify"]["dev_token"]
    assert client.post("/v1/auth/verify-email", json={"token": tok}).status_code == 200
    assert client.get("/v1/me", headers=user["h"]).json()["user"]["email_verified"] is True
    assert client.post("/v1/auth/verify-email", json={"token": tok}).status_code == 400  # single use


def test_email_change_needs_password_then_verification(client, user):
    assert client.post("/v1/me/email", headers=user["h"], json={"new_email": "new@example.com", "password": "bad"}).status_code == 403
    r = client.post("/v1/me/email", headers=user["h"], json={"new_email": "new@example.com", "password": "correct-horse-1"})
    assert r.status_code == 200
    assert client.get("/v1/me", headers=user["h"]).json()["user"]["email"] == "ann@example.com"  # unchanged until verified
    client.post("/v1/auth/verify-email", json={"token": r.json()["dev_token"]})
    assert client.get("/v1/me", headers=user["h"]).json()["user"]["email"] == "new@example.com"


def test_email_change_unavailable_without_delivery(client, user, monkeypatch):
    monkeypatch.delenv("SCRIPTLIV_DEV_RETURN_TOKENS")
    r = client.post("/v1/me/email", headers=user["h"], json={"new_email": "n@example.com", "password": "correct-horse-1"})
    assert r.status_code == 503 and r.json()["error"]["code"] == "email_not_configured"


def test_password_change_invalidates_old_tokens(client, user):
    r = client.post("/v1/me/password", headers=user["h"], json={"current_password": "correct-horse-1", "new_password": "another-pass-2"})
    assert r.status_code == 200
    assert client.get("/v1/me", headers=user["h"]).status_code == 401
    assert client.get("/v1/me", headers={"Authorization": "Bearer " + r.json()["token"]}).status_code == 200


def test_settings_roundtrip_and_validation(client, user):
    assert client.get("/v1/settings", headers=user["h"]).json()["settings"]["theme"] == "system"
    r = client.put("/v1/settings", headers=user["h"], json={"theme": "dark", "prevent_auto_lock": False, "personal_limit_minutes": 120})
    s = r.json()["settings"]
    assert s["theme"] == "dark" and s["prevent_auto_lock"] is False and s["personal_limit_minutes"] == 120
    assert client.put("/v1/settings", headers=user["h"], json={"theme": "neon"}).status_code == 422
    assert client.put("/v1/settings", headers=user["h"], json={"language": "xx"}).status_code == 422


def test_payments_never_simulated(client, user):
    assert client.get("/v1/plans").json()["purchasing_available"] is False
    r = client.post("/v1/billing/checkout", headers=user["h"], json={"kind": "pro"})
    assert r.status_code == 503 and r.json()["error"]["code"] == "payments_not_configured"
    assert client.post("/v1/billing/webhook", content=b"{}", headers={"Stripe-Signature": "t=1,v1=bad"}).status_code == 400
    assert client.get("/v1/subscription", headers=user["h"]).json()["subscription"]["plan"] == "basic"


def test_cancel_basic_is_conflict(client, user):
    assert client.post("/v1/subscription/cancel", headers=user["h"]).status_code == 409


def test_internal_requires_relay_secret(client, user):
    assert client.post("/internal/v1/usage", json={"user_id": user["id"], "session_id": "sess-01", "cumulative_seconds": 5}).status_code == 403
    assert client.post("/internal/v1/usage", headers={"X-Relay-Secret": "wrong"}, json={}).status_code == 403


def test_relay_flow_meters_speaker_only_and_viewer_free(client, user):
    r = client.post("/internal/v1/sessions/start", headers=R, json={"token": user["token"], "session_id": "sess-01"}).json()
    assert r["allowed"] and r["user_id"] == user["id"]
    u = client.post("/internal/v1/usage", headers=R, json={"user_id": user["id"], "session_id": "sess-01", "cumulative_seconds": 90}).json()
    assert u["applied"]["applied_seconds"] == 90
    client.post("/internal/v1/usage", headers=R, json={"user_id": user["id"], "session_id": "sess-01", "cumulative_seconds": 90.4, "final": True})
    s = client.get("/v1/usage", headers=user["h"]).json()
    assert s["included_used_seconds"] == 91
    assert client.get("/v1/usage/sessions", headers=user["h"]).json()["sessions"][0]["metered_seconds"] == 91
    assert len(client.get("/v1/usage/sessions/sess-01/minutes", headers=user["h"]).json()["minutes"]) == 2
    assert client.get("/v1/sessions", headers=user["h"]).json()["sessions"][0]["ended_at"] is not None


def test_relay_start_rejects_bad_token_taken_session_and_exhausted(client, user, db):
    assert client.post("/internal/v1/sessions/start", headers=R, json={"token": "junk", "session_id": "sess-01"}).json()["reason"] == "invalid_token"
    client.post("/internal/v1/sessions/start", headers=R, json={"token": user["token"], "session_id": "sess-01"})
    b = client.post("/v1/auth/register", json={"name": "Bo", "email": "bo@example.com", "password": "correct-horse-1"}).json()
    client.post("/v1/auth/verify-email", json={"token": b["verification"]["dev_token"]})
    b["token"] = client.post("/v1/auth/login", json={"email": "bo@example.com", "password": "correct-horse-1"}).json()["token"]
    assert client.post("/internal/v1/sessions/start", headers=R, json={"token": b["token"], "session_id": "sess-01"}).json()["reason"] == "session_taken"
    usage.record(db, user["id"], "sess-99", 300 * 60)
    r = client.post("/internal/v1/sessions/start", headers=R, json={"token": user["token"], "session_id": "sess-02"}).json()
    assert r["allowed"] is False and r["reason"] == "quota_exhausted"


def test_share_link_public_view_and_revoke(client, user, db):
    client.post("/internal/v1/sessions/start", headers=R, json={"token": user["token"], "session_id": "sess-01"})
    db.transcript_events.insert_many([{"session_id": "sess-01", "seq": 2, "text": "world"}, {"session_id": "sess-01", "seq": 1, "text": "hello"}])
    assert client.get("/v1/shared/nope").status_code == 404
    sh = client.post("/v1/sessions/sess-01/share", headers=user["h"]).json()
    tok = sh["share_url"].rsplit("/", 1)[1]
    pub = client.get(f"/v1/shared/{tok}")  # no auth header
    assert pub.status_code == 200 and pub.json()["transcript"] == ["hello", "world"]
    assert pub.json()["app_links"]["deep_link"] == f"scriptliv://s/{tok}"
    assert user["id"] not in pub.text
    client.delete("/v1/sessions/sess-01/share", headers=user["h"])
    assert client.get(f"/v1/shared/{tok}").status_code == 404


def test_cannot_touch_other_users_sessions(client, user):
    client.post("/internal/v1/sessions/start", headers=R, json={"token": user["token"], "session_id": "sess-01"})
    b = client.post("/v1/auth/register", json={"name": "Bo", "email": "bo@example.com", "password": "correct-horse-1"}).json()
    client.post("/v1/auth/verify-email", json={"token": b["verification"]["dev_token"]})
    h = {"Authorization": "Bearer " + client.post("/v1/auth/login", json={"email": "bo@example.com", "password": "correct-horse-1"}).json()["token"]}
    assert client.get("/v1/sessions/sess-01", headers=h).status_code == 404
    assert client.post("/v1/sessions/sess-01/share", headers=h).status_code == 404
    assert client.delete("/v1/sessions/sess-01", headers=h).status_code == 404
    assert client.get("/v1/sessions", headers=h).json()["sessions"] == []


def test_delete_session_keeps_usage_history(client, user):
    client.post("/internal/v1/sessions/start", headers=R, json={"token": user["token"], "session_id": "sess-01"})
    client.post("/internal/v1/usage", headers=R, json={"user_id": user["id"], "session_id": "sess-01", "cumulative_seconds": 60})
    assert client.delete("/v1/sessions/sess-01", headers=user["h"]).status_code == 204
    assert client.get("/v1/usage", headers=user["h"]).json()["included_used_seconds"] == 60


# --- verified email is required for transcription, share links and purchases (unverified may still sign in and read) ---

def test_unverified_can_sign_in_view_profile_and_request_another_email(client, unverified_user):
    h = unverified_user["h"]
    assert client.get("/v1/me", headers=h).status_code == 200
    assert client.get("/v1/subscription", headers=h).status_code == 200
    assert client.get("/v1/usage", headers=h).status_code == 200
    assert client.post("/v1/me/email/resend", headers=h).status_code == 200


def test_unverified_blocked_from_transcription_sharing_and_purchase(client, unverified_user, db):
    u = unverified_user
    r = client.post("/internal/v1/sessions/start", headers=R, json={"token": u["token"], "session_id": "sess-01"}).json()
    assert r["allowed"] is False and r["reason"] == "email_not_verified"
    assert db.sessions.count_documents({}) == 0 and db.usage_sessions.count_documents({}) == 0   # nothing created or reserved
    db.sessions.insert_one({"session_id": "sess-02", "owner_id": u["id"], "created_at": 1, "started_at": 1, "ended_at": None})
    s = client.post("/v1/sessions/sess-02/share", headers=u["h"])
    assert s.status_code == 403 and s.json()["error"]["code"] == "email_not_verified"
    c = client.post("/v1/billing/checkout", headers=u["h"], json={"kind": "pro"})
    assert c.status_code == 403 and c.json()["error"]["code"] == "email_not_verified"


def test_verifying_unblocks_transcription(client, unverified_user):
    u = unverified_user
    client.post("/v1/auth/verify-email", json={"token": u["verify"]["dev_token"]})
    r = client.post("/internal/v1/sessions/start", headers=R, json={"token": u["token"], "session_id": "sess-01"}).json()
    assert r["allowed"] is True
