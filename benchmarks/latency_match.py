"""Timestamp-based matching of expected utterances to received final events
(Phase 4, Task 1). Pure functions, no I/O, no ASR.

Why: the old `ws_bench.analyse_clip` paired the i-th received final with the
i-th expected utterance. When a final is missing or duplicated, every later
pair shifts (Phase 3 found 6 of 60 clips affected, one with an impossible
-3.807 s latency).

Rules
  * Expected utterance k has a reference flush time
        F_k = end_k + hang_s   (silence-hang flush)
        F_k = end_k            (forced-cap flush: no hang wait)
  * A final at time f is a candidate for expected k when F_k - tol <= f.
    It is assigned to the LATEST such k (a final cannot answer an utterance
    whose flush time is still in its future).
  * One-to-one and monotonic: finals are processed in time order, each
    expected utterance takes at most one final, a later final never takes an
    earlier expected utterance than a previous match.
  * A final whose expected utterance is already taken, or that precedes the
    first flush time, is reported in `extra_finals`.
  * An expected utterance with no final is reported in `unmatched_expected`.
  * Raw timestamps are never modified or rounded away: pairs carry them as
    given. Derived latencies are rounded to 3 decimals only for display.
  * Latencies are never negative. A value that would be negative (clock
    jitter beyond tolerance, or a first message before speech start) is
    reported as None with a note, not clamped.
  * TTFW (first message of the utterance minus speech start) and final
    latency (final minus utterance end) are separate fields.

Known limit: expected utterances come from `simulate_flushes`, a mirror of the
relay VAD, so this checks the relay against its own simulated timing. It
cannot say whether the VAD split is good.
"""
from __future__ import annotations

DEFAULT_TOL_S = 0.2


def flush_ref(u: dict, hang_s: float) -> float:
    return u["end"] + (0.0 if u.get("forced") else hang_s)


def _r(v):
    return None if v is None else round(v, 3)


def match_events(expected: list[dict], events: list, hang_s: float, tol: float = DEFAULT_TOL_S) -> dict:
    """expected: [{start, end, forced?}] in audio seconds.
    events: [(t_s, text, is_partial)] received messages, same clock.
    Returns dict with pairs, unmatched_expected, extra_finals, counts."""
    ev = sorted(events, key=lambda e: e[0])
    finals = [(i, e[0]) for i, e in enumerate([x for x in ev if not x[2]])]
    final_times = [t for _, t in finals]
    F = [flush_ref(u, hang_s) for u in expected]

    taken: dict[int, int] = {}
    assigned: list[tuple[int, int]] = []  # (expected_index, final_index)
    extra: list[dict] = []
    last_k = -1
    for fi, f in finals:
        ks = [k for k in range(len(expected)) if F[k] - tol <= f]
        if not ks:
            extra.append({"final_index": fi, "time_s": f, "reason": "before_first_expected_flush"})
            continue
        k = ks[-1]
        if k in taken:
            extra.append({"final_index": fi, "time_s": f,
                          "reason": f"expected_{k}_already_matched_to_final_{taken[k]}"})
            continue
        if k < last_k:  # cannot happen for time-ordered finals; kept as a guard
            extra.append({"final_index": fi, "time_s": f, "reason": "non_monotonic"})
            continue
        taken[k] = fi
        last_k = k
        assigned.append((k, fi))

    # message window of final fi: (time of previous final event, time of fi]
    msgs = ev
    pairs = []
    for k, fi in assigned:
        u, f = expected[k], final_times[fi]
        prev_f = final_times[fi - 1] if fi > 0 else float("-inf")
        window = [e for e in msgs if prev_f < e[0] <= f]
        first_msg = window[0][0] if window else None
        partials = [e[0] for e in window if e[2]]
        first_partial = partials[0] if partials else None
        notes = []

        ttfw = None if first_msg is None else first_msg - u["start"]
        if ttfw is not None and ttfw < 0:
            notes.append("first_message_before_expected_start")
            ttfw = None
        fpl = None if first_partial is None else first_partial - u["start"]
        if fpl is not None and fpl < 0:
            notes.append("first_partial_before_expected_start")
            fpl = None
        fin_end = f - u["end"]
        if fin_end < 0:
            notes.append("final_before_utterance_end")
            fin_end = None
        fin_flush = f - F[k]
        if fin_flush < 0:
            notes.append("final_before_flush_reference_within_tolerance")
            fin_flush = None
        # Forced flushes carry no hang wait, so "after hang" is undefined for them.
        after_hang = None if (fin_end is None or u.get("forced")) else fin_end - hang_s
        if after_hang is not None and after_hang < 0:
            notes.append("final_inside_hang_tolerance")
            after_hang = None
        pairs.append({
            "expected_index": k, "final_index": fi, "forced": bool(u.get("forced")),
            "expected_start_s": u["start"], "expected_end_s": u["end"], "flush_ref_s": F[k],
            "final_time_s": f, "first_message_time_s": first_msg, "first_partial_time_s": first_partial,
            "ttfw_s": _r(ttfw), "first_partial_s": _r(fpl),
            "final_latency_s": _r(fin_end), "final_latency_after_hang_s": _r(after_hang),
            "final_after_flush_s": _r(fin_flush), "notes": notes,
        })

    unmatched = [{"expected_index": k, "start_s": expected[k]["start"], "end_s": expected[k]["end"],
                  "forced": bool(expected[k].get("forced")), "flush_ref_s": F[k]}
                 for k in range(len(expected)) if k not in taken]
    return {
        "pairs": pairs, "unmatched_expected": unmatched, "extra_finals": extra,
        "counts": {"expected": len(expected), "finals": len(finals), "matched": len(pairs),
                   "unmatched_expected": len(unmatched), "extra_finals": len(extra)},
        "params": {"hang_s": hang_s, "tol_s": tol},
    }


def legacy_index_pairing(expected: list[dict], events: list, hang_s: float) -> dict:
    """The pre-Phase-4 index pairing, kept only to show the difference. Not for reporting."""
    ev = sorted(events, key=lambda e: e[0])
    groups, cur = [], []
    for e in ev:
        if e[2]:
            cur.append(e)
        else:
            groups.append((cur, e))
            cur = []
    ttfw, fin = [], []
    for i, (partials, f) in enumerate(groups):
        if i < len(expected):
            first = partials[0] if partials else f
            ttfw.append(first[0] - expected[i]["start"])
            fin.append(f[0] - expected[i]["end"])
    return {"ttfw_s": ttfw, "final_latency_s": fin}
