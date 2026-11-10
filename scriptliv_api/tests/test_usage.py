from app import subscriptions as subs, usage
from app.plans import ADDON_MINUTES

T0 = 1_760_000_000.0
U = "u1"


def test_basic_has_300_minutes(db):
    s = usage.summary(db, U, T0)
    assert s["included_minutes"] == 300 and s["total_remaining_seconds"] == 300 * 60


def test_idempotent_cumulative_reports(db):
    usage.record(db, U, "sess-01", 60, T0)
    usage.record(db, U, "sess-01", 60, T0)  # duplicate
    usage.record(db, U, "sess-01", 30, T0)  # stale / out of order
    assert usage.summary(db, U, T0)["included_used_seconds"] == 60


def test_reconnect_does_not_double_bill(db):
    usage.record(db, U, "sess-01", 100, T0)
    usage.record(db, U, "sess-01", 160, T0)
    assert db.usage_sessions.count_documents({}) == 1
    assert usage.summary(db, U, T0)["included_used_seconds"] == 160


def test_final_rounds_up_partial_reports_round_down(db):
    usage.record(db, U, "sess-01", 59.9, T0)
    assert usage.summary(db, U, T0)["included_used_seconds"] == 59
    usage.record(db, U, "sess-01", 60.2, T0, final=True)
    assert usage.summary(db, U, T0)["included_used_seconds"] == 61
    assert db.usage_sessions.find_one({})["ended_at"] is not None


def test_minute_level_buckets(db):
    usage.record(db, U, "sess-01", 130, T0)
    mins = {m["minute"]: m["seconds"] for m in db.usage_minutes.find({})}
    assert mins == {0: 60, 1: 60, 2: 10}


def test_concurrent_sessions_same_speaker_account(db):
    usage.record(db, U, "sess-a1", 120, T0)
    usage.record(db, U, "sess-b1", 180, T0)
    assert usage.summary(db, U, T0)["included_used_seconds"] == 300


def test_other_account_cannot_report_into_session(db):
    usage.record(db, U, "sess-01", 10, T0)
    try:
        usage.record(db, "u2", "sess-01", 20, T0)
        assert False, "should have raised"
    except usage.SessionOwnerMismatch:
        pass


def test_included_before_addon_and_separate_tracking(db):
    subs.grant_addon(db, U, T0)
    usage.record(db, U, "sess-01", 300 * 60 + 600, T0)  # 300 included + 10 min add-on
    s = usage.summary(db, U, T0)
    assert s["included_remaining_seconds"] == 0
    assert s["addon_used_seconds"] == 600
    assert s["addon_remaining_seconds"] == ADDON_MINUTES * 60 - 600
    assert usage.authorize(db, U, T0)["allowed"]


def test_exhausted_blocks_and_overshoot_tracked(db):
    usage.record(db, U, "sess-01", 300 * 60 + 5, T0)
    assert usage.authorize(db, U, T0) == {"allowed": False, "reason": "quota_exhausted", "remaining_seconds": 0}
    assert db.usage_sessions.find_one({})["unbilled_overshoot_seconds"] == 5
    assert usage.summary(db, U, T0)["warnings"][-1]["level"] == 100


def test_addon_expires_at_period_end_and_included_resets(db):
    sub = subs.get_subscription(db, U, T0)
    subs.grant_addon(db, U, T0)
    usage.record(db, U, "sess-01", 300 * 60 + 60, T0)
    later = sub["period_end"] + 1
    s = usage.summary(db, U, later)
    assert s["addons"] == [] and s["included_used_seconds"] == 0  # add-on gone, included reset, no rollover
    assert s["total_remaining_seconds"] == 300 * 60


def test_warning_thresholds(db):
    usage.record(db, U, "sess-01", int(300 * 60 * 0.81), T0)
    assert [w["level"] for w in usage.summary(db, U, T0)["warnings"]] == [80]


def test_personal_limit_blocks_new_sessions(db):
    db.settings.insert_one({"user_id": U, "personal_limit_minutes": 10})
    usage.record(db, U, "sess-01", 600, T0)
    assert usage.authorize(db, U, T0)["reason"] == "personal_limit"


def test_pro_has_2500_and_cancel_keeps_access_until_period_end(db):
    subs.activate_pro(db, U, T0)
    assert usage.summary(db, U, T0)["included_minutes"] == 2500
    sub = subs.cancel(db, U, T0)
    assert sub["cancel_at_period_end"] and usage.summary(db, U, T0 + 86400)["plan"] == "pro"
    assert usage.summary(db, U, sub["period_end"] + 1)["plan"] == "basic"


def test_session_grant_is_capped_and_reconnect_carries_on(db):
    g = usage.authorize(db, U, T0, session_id="sess-g1")
    assert g["allowed"] and g["remaining_seconds"] == usage.GRANT_WINDOW and g["base_seconds"] == 0
    usage.record(db, U, "sess-g1", 100, T0)
    g2 = usage.authorize(db, U, T0 + 1, session_id="sess-g1")  # reconnect: same session id
    assert g2["base_seconds"] == 100 and g2["remaining_seconds"] == usage.GRANT_WINDOW
    usage.record(db, U, "sess-g1", 130, T0 + 2)  # relay continues from base 100
    assert usage.summary(db, U, T0 + 2)["included_used_seconds"] == 130  # no loss, no double count


def test_concurrent_sessions_cannot_hold_more_than_is_left(db):
    usage.record(db, U, "sess-old", 300 * 60 - 400, T0)  # 400 s left
    a = usage.authorize(db, U, T0, session_id="sess-a")
    b = usage.authorize(db, U, T0, session_id="sess-b")
    c = usage.authorize(db, U, T0, session_id="sess-c")
    assert a["remaining_seconds"] == 300
    assert b["remaining_seconds"] == 100  # 400 - 300 held by sess-a
    assert not c["allowed"] and c["reason"] == "allowance_reserved"


def test_stale_session_releases_its_reservation(db):
    usage.record(db, U, "sess-old", 300 * 60 - 400, T0)
    usage.authorize(db, U, T0, session_id="sess-a")
    b = usage.authorize(db, U, T0 + usage.SESSION_STALE + 1, session_id="sess-b")  # sess-a stopped reporting
    assert b["remaining_seconds"] == 300 and b["allowed"]


def test_overshoot_is_never_charged_beyond_allowance_and_is_recorded(db):
    s = {"user_id": U, "personal_limit_minutes": 1}
    db.settings.insert_one(s)
    usage.authorize(db, U, T0, session_id="sess-p")
    usage.record(db, U, "sess-p", 60.1, T0 + 61, final=True)  # final report rounds 60.1 s up to 61 s
    row = db.usage_sessions.find_one({"session_id": "sess-p"})
    assert row["metered_seconds"] == 61 and row["included_seconds"] == 60 and row["unbilled_overshoot_seconds"] == 1
    assert usage.summary(db, U, T0 + 61)["included_used_seconds"] == 60  # ledger never above the personal limit
    assert db.usage_ledger.find_one({"source": "unbilled_overshoot"})["seconds"] == 1


def test_parallel_reports_never_overspend_plan(db):
    import threading
    usage.record(db, U, "sess-old", 300 * 60 - 100, T0)  # 100 s left
    def go(i):
        usage.record(db, U, f"sess-t{i}", 60, T0 + 1)
    th = [threading.Thread(target=go, args=(i,)) for i in range(5)]
    [t.start() for t in th]; [t.join() for t in th]
    s = usage.summary(db, U, T0 + 1)
    assert s["included_used_seconds"] == 300 * 60  # exactly the plan, not above
    assert sum(r["unbilled_overshoot_seconds"] for r in db.usage_sessions.find({})) == 5 * 60 - 100


def test_float_noise_in_final_report_is_not_billed_as_an_extra_second(db):
    """400 chunks of 0.1 s sum to 40.00000000000x; the final report must bill 40 s, not 41."""
    usage.authorize(db, U, T0, session_id="sess-f")
    usage.record(db, U, "sess-f", sum([0.1] * 400), T0 + 1, final=True)
    assert usage.summary(db, U, T0 + 1)["included_used_seconds"] == 40
