"""Regression tests for timestamp matching (Phase 4, Task 1).
Real-data cases read results/svarah_wer.json read-only (never written)."""
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from latency_match import legacy_index_pairing, match_events  # noqa: E402

HANG = 0.6
BASELINE = HERE.parent / "results" / "svarah_wer.json"
LAT_KEYS = ("ttfw_s", "first_partial_s", "final_latency_s", "final_latency_after_hang_s", "final_after_flush_s")


def U(start, end, forced=False):
    return {"start": start, "end": end, "forced": forced}


def finals(*ts):
    return [(t, "x", False) for t in ts]


# ------------------------------------------------------------ synthetic cases
def test_normal_two_utterances_one_to_one():
    ex = [U(0.0, 2.0), U(3.0, 5.0)]
    ev = [(0.8, "a", True), (2.7, "a b", False), (3.9, "c", True), (5.7, "c d", False)]
    m = match_events(ex, ev, HANG)
    assert [(p["expected_index"], p["final_index"]) for p in m["pairs"]] == [(0, 0), (1, 1)]
    assert m["unmatched_expected"] == [] and m["extra_finals"] == []
    p0, p1 = m["pairs"]
    assert p0["ttfw_s"] == pytest.approx(0.8) and p0["final_latency_s"] == pytest.approx(0.7)
    assert p1["ttfw_s"] == pytest.approx(0.9) and p1["final_latency_s"] == pytest.approx(0.7)
    assert p0["final_latency_after_hang_s"] == pytest.approx(0.1)


def test_ttfw_and_final_latency_are_separate_fields():
    m = match_events([U(1.0, 3.0)], [(1.5, "a", True), (3.7, "a b", False)], HANG)
    p = m["pairs"][0]
    assert p["ttfw_s"] == pytest.approx(0.5) and p["final_latency_s"] == pytest.approx(0.7)
    assert p["first_message_time_s"] == 1.5 and p["final_time_s"] == 3.7  # raw timestamps preserved


def test_final_without_partial_uses_final_as_first_message():
    m = match_events([U(0.0, 2.0)], finals(2.7), HANG)
    p = m["pairs"][0]
    assert p["ttfw_s"] == pytest.approx(2.7) and p["first_partial_s"] is None


def test_missing_last_final_is_explicit_unmatched():
    ex = [U(0.0, 2.0), U(3.0, 5.0)]
    m = match_events(ex, finals(2.7), HANG)
    assert len(m["pairs"]) == 1 and m["pairs"][0]["expected_index"] == 0
    assert [u["expected_index"] for u in m["unmatched_expected"]] == [1]
    assert m["extra_finals"] == []


def test_missing_first_final_does_not_shift_later_pairs():
    ex = [U(0.0, 2.0), U(3.0, 5.0)]
    m = match_events(ex, finals(5.7), HANG)
    assert [(p["expected_index"], p["final_index"]) for p in m["pairs"]] == [(1, 0)]
    assert [u["expected_index"] for u in m["unmatched_expected"]] == [0]
    assert m["pairs"][0]["final_latency_s"] == pytest.approx(0.7)  # measured against utterance 1, not 0


def test_duplicate_final_is_extra_not_a_pair():
    ex = [U(0.0, 2.0), U(3.0, 5.0)]
    m = match_events(ex, finals(2.7, 2.9, 5.7), HANG)
    assert [(p["expected_index"], p["final_index"]) for p in m["pairs"]] == [(0, 0), (1, 2)]
    assert [e["final_index"] for e in m["extra_finals"]] == [1]
    assert m["unmatched_expected"] == []
    assert all(p["final_latency_s"] >= 0 for p in m["pairs"])


def test_forced_cap_flush_has_no_hang_and_no_hang_latency():
    ex = [U(0.0, 8.0, True), U(8.0, 10.0)]
    m = match_events(ex, finals(8.7, 10.7), HANG)
    f, s = m["pairs"]
    assert f["forced"] and f["flush_ref_s"] == 8.0 and f["final_after_flush_s"] == pytest.approx(0.7)
    assert f["final_latency_after_hang_s"] is None  # undefined for a forced flush
    assert not s["forced"] and s["flush_ref_s"] == pytest.approx(10.6)


def test_forced_cap_final_does_not_steal_next_utterance():
    ex = [U(0.0, 8.0, True), U(8.0, 10.0)]
    m = match_events(ex, finals(8.7), HANG)  # F_1 = 10.6 > 8.7
    assert [p["expected_index"] for p in m["pairs"]] == [0]
    assert [u["expected_index"] for u in m["unmatched_expected"]] == [1]


def test_final_before_any_flush_time_is_extra():
    m = match_events([U(0.0, 2.0)], finals(1.0, 2.7), HANG)
    assert [e["final_index"] for e in m["extra_finals"]] == [0]
    assert m["extra_finals"][0]["reason"] == "before_first_expected_flush"
    assert [(p["expected_index"], p["final_index"]) for p in m["pairs"]] == [(0, 1)]


def test_no_negative_latency_ever():
    ex = [U(0.0, 8.0, True), U(8.0, 9.0)]
    # forced final 0.1 s before the simulated end (inside tolerance): None plus a note, never negative
    m = match_events(ex, finals(7.9, 9.7), HANG)
    for p in m["pairs"]:
        for k in LAT_KEYS:
            assert p[k] is None or p[k] >= 0, (k, p)
    assert "final_before_utterance_end" in m["pairs"][0]["notes"]


def test_partial_before_expected_start_not_negative():
    m = match_events([U(1.0, 3.0)], [(0.9, "a", True), (3.7, "a", False)], HANG)
    p = m["pairs"][0]
    assert p["ttfw_s"] is None and "first_message_before_expected_start" in p["notes"]
    assert p["final_latency_s"] == pytest.approx(0.7)


def test_unsorted_events_handled():
    m = match_events([U(0.0, 3.0)], [(3.7, "ab", False), (0.8, "a", True)], HANG)
    assert m["pairs"][0]["ttfw_s"] == pytest.approx(0.8)


def test_empty_inputs():
    assert match_events([], [], HANG)["counts"]["matched"] == 0
    m = match_events([U(0.0, 2.0)], [], HANG)
    assert m["counts"] == {"expected": 1, "finals": 0, "matched": 0, "unmatched_expected": 1, "extra_finals": 0}


def test_missing_middle_final_keeps_neighbours_aligned():
    ex = [U(0.0, 2.0), U(3.0, 5.0), U(6.0, 8.0)]
    ev = [(0.8, "a", True), (2.7, "a", False), (6.9, "q", True), (8.7, "q", False)]
    m = match_events(ex, ev, HANG)
    assert [(p["expected_index"], p["final_index"]) for p in m["pairs"]] == [(0, 0), (2, 1)]
    assert [u["expected_index"] for u in m["unmatched_expected"]] == [1]
    assert m["pairs"][1]["ttfw_s"] == pytest.approx(0.9)
    assert m["pairs"][1]["final_latency_s"] == pytest.approx(0.7)


def test_legacy_index_pairing_goes_negative_where_timestamp_matching_does_not():
    ex = [U(0.1, 8.1, True), U(8.1, 12.8)]
    ev = finals(8.851, 8.993, 13.915)
    assert min(legacy_index_pairing(ex, ev, HANG)["final_latency_s"]) < 0  # the Phase 3 defect
    m = match_events(ex, ev, HANG)
    assert all(p["final_latency_s"] is None or p["final_latency_s"] >= 0 for p in m["pairs"])


# ------------------------------------------------------- six Phase 3 clips
SIX = {
    # id prefix: (unmatched expected indexes, extra final indexes)
    "svarah_assamese_03817": ([2], []),
    "svarah_assamese_06152": ([1], []),
    "svarah_kannada_00197": ([1], []),
    "svarah_kashmiri_03111": ([1], []),
    "svarah_bodo_03621": ([6], []),
    "svarah_bengali_01831": ([], [1]),
}


@pytest.fixture(scope="module")
def baseline():
    if not BASELINE.exists():
        pytest.skip("baseline results/svarah_wer.json not present")
    return {c["id"]: c for c in json.loads(BASELINE.read_text(encoding="utf-8"))["levels"][0]["clips"]}


@pytest.mark.parametrize("prefix", list(SIX))
def test_phase3_mismatch_clip(prefix, baseline):
    c = next(v for k, v in baseline.items() if k.startswith(prefix))
    m = match_events(c["expected_detail"], finals(*c["final_times_s"]), HANG)
    unmatched, extra = SIX[prefix]
    assert [u["expected_index"] for u in m["unmatched_expected"]] == unmatched
    assert [e["final_index"] for e in m["extra_finals"]] == extra
    assert m["counts"]["matched"] == min(c["utterances_expected"] - len(unmatched), c["finals_received"] - len(extra))
    idx = [p["expected_index"] for p in m["pairs"]]
    fidx = [p["final_index"] for p in m["pairs"]]
    assert idx == sorted(set(idx)) and fidx == sorted(set(fidx))  # monotonic, one-to-one
    for p in m["pairs"]:
        assert p["final_latency_s"] is None or p["final_latency_s"] >= 0


def test_phase3_bengali_negative_latency_removed(baseline):
    c = next(v for k, v in baseline.items() if k.startswith("svarah_bengali_01831"))
    assert min(c["final_latency_s"]) < -3.5  # stored legacy value, untouched in the baseline
    m = match_events(c["expected_detail"], finals(*c["final_times_s"]), HANG)
    assert all(p["final_latency_s"] > 0 for p in m["pairs"])


def test_phase3_all_60_clips_never_negative_and_totals_match_audit(baseline):
    total_unmatched = total_extra = 0
    for c in baseline.values():
        m = match_events(c["expected_detail"], finals(*c["final_times_s"]), HANG)
        total_unmatched += m["counts"]["unmatched_expected"]
        total_extra += m["counts"]["extra_finals"]
        for p in m["pairs"]:
            assert p["final_latency_s"] is None or p["final_latency_s"] >= 0
        if c["finals_received"] == c["utterances_expected"]:
            assert m["counts"]["matched"] == c["utterances_expected"], c["id"]
    assert (total_unmatched, total_extra) == (5, 1)  # Phase 3 audit: 5 lost finals, 1 extra
