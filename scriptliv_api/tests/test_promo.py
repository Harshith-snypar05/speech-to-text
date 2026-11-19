"""Inaugural offer: free, unlimited minutes until SCRIPTLIV_PROMO_UNLIMITED_UNTIL, nothing deducted, then back to the plan."""
import pytest

from app import usage
from app.config import _promo_until, get_settings, promo_active
from app.plans import PROMO_MAX_SESSION_MINUTES

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


def test_account_with_no_minutes_left_can_still_speak(db, offer):
    usage.record(db, U, "burn", BASIC_S, T0)   # spend all of Basic first (this report is itself inside the offer: not deducted)
    a = usage.authorize(db, U, T0, session_id="s1")
    assert a["allowed"] and a["remaining_seconds"] == 300 and a["session_cap_seconds"] == PROMO_MAX_SESSION_MINUTES * 60


def test_nothing_is_deducted_but_usage_is_recorded(db, offer):
    usage.authorize(db, U, T0, session_id="s1")
    r = usage.record(db, U, "s1", 600, T0 + 600, final=True)
    assert r["included"] == 0 and r["addon"] == 0 and r["promo"] == 600
    s = usage.summary(db, U, T0 + 601)
    assert s["included_used_seconds"] == 0 and s["unlimited"] is True and s["promo"]["active"]
    assert s["warnings"] == []
    row = db.usage_sessions.find_one({"session_id": "s1"})
    assert row["metered_seconds"] == 600 and row["ended_at"] is not None
    assert [x["source"] for x in db.usage_ledger.find({"session_id": "s1"})] == ["promo"]


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


def test_after_the_offer_the_plan_applies_again(db, offer):
    usage.record(db, U, "s1", 5000, T0, final=True)                       # during the offer: free
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
