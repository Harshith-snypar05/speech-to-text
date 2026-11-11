"""Strict recording limit: balance == maximum duration, no grace, no free extension, auditable ledger."""
from app import subscriptions as subs, usage
from app.plans import PRO

T0 = 1_760_000_000.0
U = "u1"
BASIC_S = 300 * 60


def _use(db, seconds):
    """Spend `seconds` of the Basic allowance directly (no reservation involved)."""
    usage.record(db, U, "sess-burn", seconds, T0)
    db.usage_sessions.update_one({"session_id": "sess-burn"}, {"$set": {"ended_at": T0}})


def _ledger(db, session_id):
    rows = list(db.usage_ledger.find({"session_id": session_id}))
    return sum(r["seconds"] for r in rows if r["source"] in ("included", "addon")), \
        sum(r["seconds"] for r in rows if r["source"] == "unbilled_overshoot")


def test_authorize_tells_the_relay_exactly_what_is_left(db):
    _use(db, BASIC_S - 40)
    a = usage.authorize(db, U, T0, session_id="sess-a")
    assert a["allowed"] and a["remaining_seconds"] == 40 and a["base_seconds"] == 0


def test_boundary_second_before_zero_then_zero(db):
    _use(db, BASIC_S - 40)
    usage.authorize(db, U, T0, session_id="sess-a")
    # one second before the balance reaches zero: still allowed, 1 s left
    r = usage.record(db, U, "sess-a", 39, T0 + 39)
    assert r["included"] == 39
    mid = usage.authorize(db, U, T0 + 39, session_id="sess-a", midsession=True)
    assert mid["allowed"] and mid["remaining_seconds"] == 1
    # the exact second the balance hits zero: all 40 s billed, nothing beyond
    r = usage.record(db, U, "sess-a", 40, T0 + 40, final=True)
    assert r["included"] == 1 and r["unbilled_overshoot"] == 0
    assert usage.summary(db, U, T0 + 40)["included_used_seconds"] == BASIC_S
    assert not usage.authorize(db, U, T0 + 41, session_id="sess-z")["allowed"]
    assert usage.authorize(db, U, T0 + 41, session_id="sess-z")["reason"] == "quota_exhausted"


def test_report_past_the_grant_is_not_billed_but_recorded_separately(db):
    _use(db, BASIC_S - 40)
    usage.authorize(db, U, T0, session_id="sess-a")           # grant = 40
    r = usage.record(db, U, "sess-a", 47, T0 + 47, final=True)  # 7 s got through after the stop
    assert r["included"] == 40 and r["unbilled_overshoot"] == 7
    billed, over = _ledger(db, "sess-a")
    assert billed == 40 and over == 7
    row = db.usage_sessions.find_one({"session_id": "sess-a"})
    assert row["unbilled_overshoot_seconds"] == 7
    assert usage.summary(db, U, T0 + 47)["included_used_seconds"] == BASIC_S   # never above the allowance


def test_grant_is_not_extended_by_reports_that_run_ahead(db):
    _use(db, BASIC_S - 100)
    usage.authorize(db, U, T0, session_id="sess-a")
    usage.record(db, U, "sess-a", 60, T0 + 60)
    mid = usage.authorize(db, U, T0 + 60, session_id="sess-a", midsession=True)
    assert mid["base_seconds"] == 60 and mid["remaining_seconds"] == 40   # 100 total, never more
    usage.record(db, U, "sess-a", 130, T0 + 130)
    billed, over = _ledger(db, "sess-a")
    assert billed == 100 and over == 30


def test_cumulative_and_closing_report_do_not_double_bill(db):
    usage.authorize(db, U, T0, session_id="sess-a")
    for cum in (10, 20, 20, 30, 15):                       # periodic, duplicate, stale
        usage.record(db, U, "sess-a", cum, T0)
    usage.record(db, U, "sess-a", 30.0, T0, final=True)    # closing report repeats the last total
    usage.record(db, U, "sess-a", 30.0, T0, final=True)    # retried closing report
    billed, over = _ledger(db, "sess-a")
    assert billed == 30 and over == 0
    assert usage.summary(db, U, T0)["included_used_seconds"] == 30
    assert db.usage_ledger.count_documents({"session_id": "sess-a"}) == 3   # 10 + 10 + 10, no duplicate rows


def test_late_periodic_report_does_not_reopen_an_ended_session(db):
    usage.authorize(db, U, T0, session_id="sess-a")
    usage.record(db, U, "sess-a", 30, T0, final=True)
    assert db.usage_sessions.find_one({"session_id": "sess-a"})["ended_at"] is not None
    late = usage.authorize(db, U, T0 + 1, session_id="sess-a", midsession=True)
    assert not late["allowed"] and late["reason"] == "session_ended"
    assert db.usage_sessions.find_one({"session_id": "sess-a"})["ended_at"] is not None


def test_reconnect_is_one_reservation_and_carries_on(db):
    _use(db, BASIC_S - 100)
    usage.authorize(db, U, T0, session_id="sess-a")
    usage.record(db, U, "sess-a", 30, T0 + 30, final=True)           # connection dropped
    again = usage.authorize(db, U, T0 + 35, session_id="sess-a")      # same session id reconnects
    assert again["allowed"] and again["base_seconds"] == 30 and again["remaining_seconds"] == 70
    assert db.usage_sessions.count_documents({"session_id": "sess-a"}) == 1
    # a second session sees only what the first one does not hold
    other = usage.authorize(db, U, T0 + 36, session_id="sess-b")
    assert not other["allowed"] and other["reason"] == "allowance_reserved"


def test_denied_reconnect_does_not_reopen_or_reserve(db):
    _use(db, BASIC_S)
    usage.authorize(db, U, T0, session_id="sess-a")
    db.usage_sessions.update_one({"session_id": "sess-a"}, {"$set": {"ended_at": T0}})
    d = usage.authorize(db, U, T0 + 1, session_id="sess-a")
    assert not d["allowed"]
    assert db.usage_sessions.find_one({"session_id": "sess-a"})["ended_at"] == T0


def test_reservation_released_on_end_and_on_stale(db):
    _use(db, BASIC_S - 100)
    usage.authorize(db, U, T0, session_id="sess-a")
    assert usage.authorize(db, U, T0 + 1, session_id="sess-b")["reason"] == "allowance_reserved"
    usage.record(db, U, "sess-a", 20, T0 + 2, final=True)             # normal end releases the rest
    assert usage.authorize(db, U, T0 + 3, session_id="sess-b")["remaining_seconds"] == 80
    # session b crashes (no more reports): after SESSION_STALE its hold is gone
    assert usage.authorize(db, U, T0 + 4, session_id="sess-c")["reason"] == "allowance_reserved"
    c = usage.authorize(db, U, T0 + 4 + usage.SESSION_STALE + 1, session_id="sess-c")
    assert c["allowed"] and c["remaining_seconds"] == 80


def test_restricted_account_gets_free_allowance_only_and_payment_required(db):
    subs.activate_pro(db, U, T0, provider="stripe", customer_id="cus_1", subscription_id="sub_1")
    subs.grant_addon(db, U, T0, payment_id="p1")
    assert usage.summary(db, U, T0)["total_remaining_seconds"] > BASIC_S
    sub = db.subscriptions.find_one({"user_id": U})
    db.subscriptions.update_one({"_id": sub["_id"]}, {"$set": {"status": "restricted"}})
    s = usage.summary(db, U, T0)
    assert s["restricted"] and s["total_remaining_seconds"] == BASIC_S and s["addon_remaining_seconds"] == 0
    assert s["plan"] == PRO                                           # history/billing stay: the plan is still shown
    db.subscriptions.update_one({"_id": sub["_id"]}, {"$set": {"included_used_seconds": BASIC_S}})
    d = usage.authorize(db, U, T0, session_id="sess-x")
    assert not d["allowed"] and d["reason"] == "payment_required"


def test_free_session_is_capped_at_30_minutes(db):
    a = usage.authorize(db, U, T0, session_id="sess-cap")
    assert a["allowed"] and a["session_cap_seconds"] == 1800
    assert a["remaining_seconds"] == 300          # the normal grant window, well inside the cap
    usage.record(db, U, "sess-cap", 1700, T0 + 1700)
    mid = usage.authorize(db, U, T0 + 1700, session_id="sess-cap", midsession=True)
    assert mid["allowed"] and mid["base_seconds"] == 1700 and mid["remaining_seconds"] == 100   # trimmed to the cap, not 300
    usage.record(db, U, "sess-cap", 1800, T0 + 1800)
    end = usage.authorize(db, U, T0 + 1800, session_id="sess-cap", midsession=True)
    assert not end["allowed"] and end["reason"] == "session_limit"


def test_free_cap_applies_to_a_reconnect_of_the_same_session_and_not_to_a_new_one(db):
    usage.authorize(db, U, T0, session_id="sess-cap")
    usage.record(db, U, "sess-cap", 1800, T0 + 1800)
    again = usage.authorize(db, U, T0 + 1801, session_id="sess-cap")
    assert not again["allowed"] and again["reason"] == "session_limit"
    fresh = usage.authorize(db, U, T0 + 1802, session_id="sess-new")
    assert fresh["allowed"] and fresh["remaining_seconds"] == 300


def test_pro_has_no_session_cap(db):
    subs.activate_pro(db, U, T0)
    a = usage.authorize(db, U, T0, session_id="sess-pro")
    assert a["allowed"] and "session_cap_seconds" not in a
    usage.record(db, U, "sess-pro", 4000, T0 + 4000)
    assert usage.authorize(db, U, T0 + 4000, session_id="sess-pro", midsession=True)["allowed"]
