"""Phase 4, Task 3: raw / number-normalized / compound-normalized WER fields."""
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import ws_bench  # noqa: E402
from wer import wer  # noqa: E402
from wer_policies import DISCLAIMER, policy_wer  # noqa: E402

BASELINE = HERE.parent / "results" / "svarah_wer.json"


def test_raw_policy_equals_baseline_wer():
    ref, hyp = "call 9876 now please", "call nine eight seven six now please"
    assert policy_wer(ref, hyp)["raw"] == wer(ref, hyp)


def test_number_policy_removes_digit_word_formatting_difference():
    s = policy_wer("my number is 98765", "my number is nine eight seven six five")
    assert s["raw"]["errors"] > 0 and s["number"]["errors"] == 0


def test_number_words_to_integer_and_separators():
    assert policy_wer("pay 1,000 rupees", "pay one thousand rupees")["number"]["errors"] == 0
    assert policy_wer("grew 3.5 percent", "grew three point five percent")["number"]["errors"] == 0


def test_number_policy_does_not_hide_a_different_number():
    assert policy_wer("call 9876", "call nine eight seven five")["number"]["errors"] > 0


def test_compound_policy_is_separate_and_only_joins_when_other_side_has_it():
    s = policy_wer("the passbook is here", "the pass book is here")
    assert s["number"]["errors"] > 0 and s["compound"]["errors"] == 0
    assert policy_wer("the pass book", "the cat sat")["compound"]["errors"] == policy_wer("the pass book", "the cat sat")["number"]["errors"]


def test_fillers_are_not_removed():
    s = policy_wer("i went home", "uh i went home")
    assert s["raw"]["ins"] == s["number"]["ins"] == s["compound"]["ins"] == 1


def test_disclaimer_states_diagnostic_not_accuracy():
    assert "does not represent improved recognition accuracy" in DISCLAIMER


def test_analyse_clip_keeps_raw_wer_and_adds_separate_fields():
    clip = {"id": "c", "reference": "call 9876 now", "tags": {}}
    ev = [(0.5, "call", True), (2.0, "call nine eight seven six now", False)]
    r = ws_bench.analyse_clip(clip, ev, [{"start": 0.0, "end": 1.5, "forced": False}], 0.6)
    assert r["errors"] == r["wer_raw"]["errors"] > 0  # legacy top-level fields stay raw
    assert r["wer_number_normalized"]["errors"] == 0
    assert "wer_compound_normalized" in r and r["events_raw"][0][0] == 0.5
    s = ws_bench.aggregate([r], 0.6)
    assert s["wer"]["wer"] == s["wer_raw"]["wer"] > s["wer_number_normalized"]["wer"] == 0
    assert "does not represent improved recognition accuracy" in s["wer_note"]


@pytest.mark.skipif(not BASELINE.exists(), reason="baseline absent")
def test_baseline_reference_numbers():
    lvl = json.loads(BASELINE.read_text(encoding="utf-8"))["levels"][0]
    rows = {"raw": [], "number": [], "compound": []}
    for c in lvl["clips"]:
        s = policy_wer(c["reference"], c["hypothesis"])
        for k in rows:
            rows[k].append(s[k])
    pct = {k: 100 * sum(r["errors"] for r in v) / sum(r["ref_words"] for r in v) for k, v in rows.items()}
    assert round(pct["raw"], 2) == 23.07 and round(pct["number"], 2) == 17.26 and round(pct["compound"], 2) == 16.56
    assert round(100 * lvl["summary"]["wer"]["wer"], 2) == 23.07  # stored baseline unchanged
