import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from flush_correlate import correlate  # noqa: E402


def test_correlate_explains_unmatched_expected_with_relay_flush_record():
    diag = {7: [
        {"seq": 1, "audio_received_s": 8.1, "outcome": "final_sent", "reason": "forced_cap", "buffer_s": 8.0,
         "speech_s": 7.9, "decode_attempted": True, "text_empty": False, "exception": None},
        {"seq": 2, "audio_received_s": 11.8, "outcome": "dropped_empty_text", "reason": "silence_hang", "buffer_s": 3.7,
         "speech_s": 2.2, "decode_attempted": True, "text_empty": True, "exception": None}]}
    clip = {"id": "c1", "finals_received": 1, "utterances_expected": 2,
            "latency_match": {"unmatched_expected": [{"expected_index": 1, "start_s": 8.1, "end_s": 10.3, "forced": False}],
                              "extra_finals": []}}
    r = correlate(diag, [clip])[0]
    u = r["unmatched_explained"][0]
    assert r["conn_id"] == 7 and u["relay_outcome"] == "dropped_empty_text" and u["text_empty"] is True


def test_correlate_reports_no_flush_record():
    clip = {"id": "c1", "finals_received": 0, "utterances_expected": 1,
            "latency_match": {"unmatched_expected": [{"expected_index": 0, "start_s": 0, "end_s": 2, "forced": False}], "extra_finals": []}}
    assert correlate({}, [clip])[0]["unmatched_explained"][0]["relay_outcome"] == "no_flush_record"
