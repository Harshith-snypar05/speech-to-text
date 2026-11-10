"""Post-process the relay pilot: UNVERIFIED draft transcripts + observation-only aggregates. No WER (no references)."""
import json
from pathlib import Path

import numpy as np

d = json.load(open("results/existing_audio_relay_pilot.json", encoding="utf-8"))
lv = d["levels"][0]
clips = lv["clips"]
dr = Path("dataset_existing/pilot/drafts")
dr.mkdir(parents=True, exist_ok=True)
HDR = "[UNVERIFIED DRAFT - Parakeet TDT 0.6B v3 relay output. NOT ground truth. Do not score against.]\n"
for c in clips:
    (dr / f"{c['id']}.draft.txt").write_text(HDR + c["hypothesis"] + "\n", encoding="utf-8")


def pct(a, q):
    return round(float(np.percentile(a, q)), 3) if len(a) else None


per = {}
for c in clips:
    r = c["tags"]["recording_id"]
    p = per.setdefault(r, dict(clips=0, ttfw=[], fin=[], exp=0, rec=0, forced=0, pw=0, rev=0, words=0, mismatch=0))
    p["clips"] += 1
    p["ttfw"] += c.get("ttfw_s", [])
    p["fin"] += c.get("final_latency_s", [])
    p["exp"] += c["utterances_expected"]
    p["rec"] += c["finals_received"]
    p["forced"] += sum(1 for e in c["expected_detail"] if e.get("forced"))
    p["pw"] += c["partial_words"]
    p["rev"] += c["partial_words_revised"]
    p["words"] += len(c["hypothesis"].split())
    p["mismatch"] += int(c["utterances_expected"] != c["finals_received"])
out = {}
for r, p in sorted(per.items()):
    out[r] = dict(clips=p["clips"], utterances_expected=p["exp"], finals_received=p["rec"], forced_cap_flushes_expected=p["forced"],
                  clips_expected_ne_received=p["mismatch"], hyp_words=p["words"], ttfw_p50=pct(p["ttfw"], 50), ttfw_p95=pct(p["ttfw"], 95),
                  final_p50=pct(p["fin"], 50), final_p95=pct(p["fin"], 95),
                  partial_revision_rate=round(p["rev"] / p["pw"], 3) if p["pw"] else None)
    print(r, out[r])
json.dump(out, open("results/existing_audio_pilot_by_recording.json", "w"), indent=1)
tot_audio = sum(c.get("duration_s", 30) for c in clips)
print("clips", len(clips), "wall_s", lv["wall_s"], "relay", lv["resources"]["relay_cpu"], lv["resources"]["relay_rss_mb"])
print("expected utt", sum(p["exp"] for p in per.values()), "received", sum(p["rec"] for p in per.values()))
print("drafts written", len(clips))
