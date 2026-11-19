"""Inaugural offer: free until SCRIPTLIV_PROMO_UNLIMITED_UNTIL, PROMO_ALLOWANCE_MINUTES per account, plan minutes untouched, then back to the plan."""
import pytest

from app import usage
from app.config import _promo_until, get_settings, promo_active
from app.plans import PROMO_ALLOWANCE_MINUTES, PROMO_ALLOWANCE_SECONDS, PROMO_MAX_SESSION_MINUTES

T0 = 1_760_000_000.0          # 2025-10-09
U = "u1"
BASIC_S = 300 * 60


@pytest.fixture
def offer(monkeypatch):
    monkeypatch.setenv("SCRIPTLIV_PROMO_UNLIMITED_UNTIL", "2026-11-26")


def test_off_by_default():
    assert get_settings().promo_unlimited_until == 0 and not promo_active(T0)


def test_date_parsing_is_forgiving():
    assert _promo_until("") == 0 and _promo_until("not a date") == 0
    assert _promo_until("2026-11-26") > _promo_until("2026-11-26T00:00:00+00:00")   # a bare date runs through that day
    assert _promo_until("2026-11-26T10:00:00+05:30") == _promo_until("2026-11-26T04:30:00+00:00")


def test_plan_minutes_do_not_matter_during_offer(db, offer):
    usage.record(db, U, "burn", BASIC_S, T0)   # even an account with no plan minutes left gets the offer allowance
    a = usage.authorize(db, U, T0, session_id="s1")
    assert a["allowed"] and a["session_cap_seconds"] == PROMO_MAX_SESSION_MINUTES * 60
    assert a["remaining_seconds"] == 300       # one grant window


def test_allowance_is_taken_from_offer_not_plan(db, offer):
    usage.authorize(db, U, T0, session_id="s1")
    r = usage.record(db, U, "s1", 300, T0 + 300)
    usage.authorize(db, U, T0 + 300, session_id="s1", midsession=True)   # a usage report extends the grant
    r2 = usage.record(db, U, "s1", 600, T0 + 600, final=True)
    assert r["promo"] == 300 and r2["promo"] == 300
    assert r["included"] == 0 and r["addon"] == 0 and r2["included"] == 0
    s = usage.summary(db, U, T0 + 601)
    assert s["unlimited"] is False and s["promo"]["active"]
    assert s["promo"]["allowance_minutes"] == PROMO_ALLOWANCE_MINUTES and s["promo"]["used_seconds"] == 600
    assert s["promo"]["remaining_seconds"] == PROMO_ALLOWANCE_SECONDS - 600
    assert s["total_remaining_seconds"] == PROMO_ALLOWANCE_SECONDS - 600
    assert s["included_minutes"] == PROMO_ALLOWANCE_MINUTES and s["included_remaining_seconds"] == PROMO_ALLOWANCE_SECONDS - 600
    row = db.usage_sessions.find_one({"session_id": "s1"})
    assert row["metered_seconds"] == 600 and row["ended_at"] is not None and row["included_seconds"] == 0
    assert [x["source"] for x in db.usage_ledger.find({"session_id": "s1"})] == ["promo", "promo"]
    assert usage.remaining(db, U, T0 + 601)["included_remaining"] == BASIC_S   # plan untouched


def test_allowance_runs_out(db, offer):
    db.usage_ledger.insert_one({"user_id": U, "session_id": "old", "seconds": PROMO_ALLOWANCE_SECONDS - 100, "source": "promo", "ts": T0})
    a = usage.authorize(db, U, T0, session_id="s1")
    assert a["allowed"] and a["remaining_seconds"] == 100
    r = usage.record(db, U, "s1", 130, T0 + 130, final=True)     # 30 s past the allowance: recorded, not charged
    assert r["promo"] == 100 and r["unbilled_overshoot"] == 30
    assert usage.promo_used_seconds(db, U) == PROMO_ALLOWANCE_SECONDS
    b = usage.authorize(db, U, T0 + 200, session_id="s2")
    assert not b["allowed"] and b["reason"] == "quota_exhausted"
    s = usage.summary(db, U, T0 + 200)
    assert s["promo"]["remaining_seconds"] == 0 and s["warnings"][-1]["level"] == 100


def test_allowance_is_per_user(db, offer):
    usage.record(db, U, "s1", 900, T0, final=True)
    assert usage.promo_used_seconds(db, "u2") == 0
    assert usage.authorize(db, "u2", T0, session_id="s2")["allowed"]


def test_repeated_report_does_not_double_count(db, offer):
    usage.record(db, U, "s1", 300, T0)
    usage.record(db, U, "s1", 300, T0)
    usage.record(db, U, "s1", 400, T0 + 100, final=True)
    assert sum(x["seconds"] for x in db.usage_ledger.find({"session_id": "s1"})) == 400


def test_session_cap_still_applies(db, offer):
    cap = PROMO_MAX_SESSION_MINUTES * 60
    usage.authorize(db, U, T0, session_id="s1")
    usage.record(db, U, "s1", cap, T0 + cap)
    mid = usage.authorize(db, U, T0 + cap, session_id="s1", midsession=True)
    assert not mid["allowed"] and mid["reason"] == "session_limit"


def test_personal_limit_still_applies(db, offer):
    db.settings.insert_one({"user_id": U, "personal_limit_minutes": 10})
    a = usage.authorize(db, U, T0, session_id="s1")
    assert a["allowed"] and a["remaining_seconds"] <= 600
    usage.record(db, U, "s1", 300, T0 + 300, final=True)
    usage.authorize(db, U, T0 + 301, session_id="s3")
    usage.record(db, U, "s3", 200, T0 + 500, final=True)
    assert usage.remaining(db, U, T0 + 501)["promo_used"] == 500
    assert usage._personal_room(db, U, usage.remaining(db, U, T0 + 501)) == 100   # offer minutes count toward the limit


def test_after_the_offer_the_plan_applies_again(db, offer):
    usage.record(db, U, "s1", 5000, T0, final=True)                       # during the offer: from the offer allowance
    after = 1_800_000_000.0                                              # 2027-01, past 2026-11-26
    assert not promo_active(after)
    s = usage.summary(db, U, after)
    assert s["unlimited"] is False and s["included_used_seconds"] == 0 and s["total_remaining_seconds"] == BASIC_S
    usage.record(db, U, "s2", 60, after, final=True)
    assert usage.summary(db, U, after)["included_used_seconds"] == 60


def test_plans_and_checkout_paused_during_offer(client, monkeypatch):
    monkeypatch.setenv("SCRIPTLIV_PROMO_UNLIMITED_UNTIL", "2999-01-01")
    body = client.get("/v1/plans").json()
    assert body["promo_active"] is True
    assert body["purchasing_available"] is False


def test_plans_normal_without_offer(client):
    body = client.get("/v1/plans").json()
    assert body["promo_active"] is False
