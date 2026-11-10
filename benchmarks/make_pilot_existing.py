"""Pick a small stratified pilot from dataset_existing/manifest.json for a live relay run, and write
(a) a ws_bench-format manifest with EMPTY references (no WER can be computed; drafts only),
(b) an annotation sheet for human transcription. Selection is deterministic: per recording, N materialized
30 s clips at 20/50/80 % of the recording, preferring clean pause cuts. Nothing is invented."""
import csv, json, sys
from pathlib import Path
root = Path("dataset_existing")
man = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
n_per = int(sys.argv[1]) if len(sys.argv) > 1 else 3
pilot = []
for rid in sorted({c["recording_id"] for c in man["clips"]}):
    cs = [c for c in man["clips"] if c["recording_id"] == rid and c["materialized"] and c["segment_length_target_s"] == 30
          and c["duration"] >= 20]
    for q in (0.2, 0.5, 0.8)[:n_per]:
        tgt = q * max(c["end_time"] for c in cs)
        cs_q = sorted(cs, key=lambda c: (c["boundary_quality"] != "pause_cut", abs(c["start_time"] - tgt)))
        c = min(cs_q[:6], key=lambda c: abs(c["start_time"] - tgt))
        if c not in pilot:
            pilot.append(c)
(root / "pilot").mkdir(exist_ok=True)
clips = [dict(id=c["clip_id"], wav="../" + Path(c["audio_path"]).as_posix().split("dataset_existing/")[-1],
              reference="", tags=dict(recording_id=c["recording_id"], accent=c["accent"], language=c["language"],
                                      boundary_quality=c["boundary_quality"], recording_condition=c["recording_condition"]))
         for c in pilot]
(root / "pilot" / "manifest.json").write_text(json.dumps(dict(_note="EMPTY references: latency/RTF/partials only; WER undefined", clips=clips), indent=1), encoding="utf-8")
with open(root / "pilot" / "annotation_sheet.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["clip_id", "recording_id", "start_s", "end_s", "audio_path", "draft_path_UNVERIFIED", "verified_reference_path", "status"])
    for c in pilot:
        w.writerow([c["clip_id"], c["recording_id"], c["start_time"], c["end_time"], c["audio_path"],
                    f"dataset_existing/pilot/drafts/{c['clip_id']}.draft.txt", f"dataset_existing/transcripts_verified/{c['clip_id']}.txt", "needs_human_transcription"])
print(len(pilot), "pilot clips,", round(sum(c["duration"] for c in pilot) / 60, 1), "min")
