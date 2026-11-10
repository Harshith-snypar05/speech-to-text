"""Compare Parakeet-only passes. Machine-vs-machine CONSISTENCY only. No reference, no WER, no 'verified' labels.

Passes: A = original relay draft (streaming path), B = offline full-clip rerun, C = overlapping-window merge,
D = offline replay of the relay flush rule (extra). token_agreement(X,Y) = 2*M/(|X|+|Y|) where M = tokens in
difflib matching blocks of the wer.normalize() token lists. It measures how similar two machine outputs are.
It is NOT accuracy: two runs can agree and both be wrong.
"""
import csv
import json
import re
import shutil
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

import numpy as np

from wer import normalize

OUTD = Path("dataset_existing/transcripts_parakeet")
OUTD.mkdir(parents=True, exist_ok=True)
AGREE_THR = 0.90          # a-priori heuristic, not validated
LOWLEVEL_P95 = 0.05       # clip p95 frame RMS under this = quiet clip (same cutoff as Svarah audit)
raw = json.load(open("results/parakeet_raw_passes.json", encoding="utf-8"))
pilot = {c["id"]: c for c in json.load(open("results/existing_audio_relay_pilot.json", encoding="utf-8"))["levels"][0]["clips"]}
main = {c["clip_id"]: c for c in json.load(open("dataset_existing/manifest.json", encoding="utf-8"))["clips"]}
inv = {f["recording_id"]: f for f in json.load(open("results/existing_audio_inventory.json", encoding="utf-8"))["files"]}
HDR = "[UNVERIFIED DRAFT"


def tok(s):
    return normalize(s)


def agree(x, y):
    if not x and not y:
        return 1.0
    sm = SequenceMatcher(None, x, y, autojunk=False)
    return 2 * sum(b.size for b in sm.get_matching_blocks()) / (len(x) + len(y))


def ops(x, y):
    sm = SequenceMatcher(None, x, y, autojunk=False)
    return [dict(op=t, a=x[i1:i2], b=y[j1:j2], a_pos=i1, b_pos=j1) for t, i1, i2, j1, j2 in sm.get_opcodes() if t != "equal"]


def adj_repeats(t):
    return Counter(f"{t[i]} {t[i+1]}" for i in range(len(t) - 1) if t[i] == t[i + 1])


NUMW = set("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty thirty forty fifty sixty seventy eighty ninety hundred thousand million".split())

rows, per_clip, change_pairs, rec_agg = [], [], Counter(), {}
for r in raw["clips"]:
    cid, rid = r["id"], r["id"].split("_")[0]
    p = pilot[cid]
    draft = (Path("dataset_existing/pilot/drafts") / f"{cid}.draft.txt").read_text(encoding="utf-8")
    A_raw = "\n".join(l for l in draft.splitlines() if not l.startswith(HDR)).strip()
    if A_raw != p["hypothesis"].strip():
        A_raw = A_raw  # draft file is the preserved original; relay JSON should equal it
    st = dict(clip_id=cid, recording_id=rid, issues=[], label_note="MACHINE_GENERATED_UNVERIFIED; agreement is not accuracy")
    if r.get("error"):
        st.update(status="NOT_EVALUATED", issues=[f"inference error: {r['error']}"])
        (OUTD / f"{cid}_status.json").write_text(json.dumps(st, indent=1), encoding="utf-8")
        continue
    B_raw, B2_raw, C_raw, D_raw = r["B"], r["B2"], r["C"], r["D"]
    A, B, B2, C, D = (tok(s) for s in (A_raw, B_raw, B2_raw, C_raw, D_raw))
    ag = dict(AB=agree(A, B), AC=agree(A, C), BC=agree(B, C), AD=agree(A, D), BD=agree(B, D), B_B2=agree(B, B2))
    opsd = dict(AB=ops(A, B), AC=ops(A, C), BC=ops(B, C))
    for o in opsd["AB"] + opsd["BC"] + opsd["AC"]:
        if o["op"] == "replace" and len(o["a"]) == 1 and len(o["b"]) == 1:
            change_pairs[tuple(sorted((o["a"][0], o["b"][0])))] += 1
    # 3-way token support, B as pivot
    def aligned(x, y):
        m = set()
        for b in SequenceMatcher(None, x, y, autojunk=False).get_matching_blocks():
            m.update(range(b.b, b.b + b.size))
        return m
    inA, inC = aligned(A, B), aligned(C, B)
    three = dict(in_all_three=sum(1 for i in range(len(B)) if i in inA and i in inC),
                 B_and_A_only=sum(1 for i in range(len(B)) if i in inA and i not in inC),
                 B_and_C_only=sum(1 for i in range(len(B)) if i not in inA and i in inC),
                 B_only=sum(1 for i in range(len(B)) if i not in inA and i not in inC),
                 tokens_B=len(B), tokens_A=len(A), tokens_C=len(C), tokens_D=len(D))
    # missing / repeated suspicions
    miss = []
    for pair, (xn, yn) in dict(A_vs_B=("A", "B"), C_vs_B=("C", "B")).items():
        X = dict(A=A, B=B, C=C)[xn]
        for o in ops(X, B):
            if o["op"] == "insert":
                miss.append(f"{xn} lacks vs B: {' '.join(o['b'])}")
            elif o["op"] == "delete":
                miss.append(f"B lacks vs {xn}: {' '.join(o['a'])}")
    reps = {}
    for name, t in dict(A=A, B=B, C=C, D=D).items():
        rc = adj_repeats(t)
        others = [adj_repeats(x) for k, x in dict(A=A, B=B, C=C, D=D).items() if k != name]
        reps[name] = {k: v for k, v in rc.items() if all(o.get(k, 0) < v for o in others)}  # repeat unique to this pass
    reps_any = {k: sorted(v) for k, v in {n: adj_repeats(t) for n, t in dict(A=A, B=B, C=C, D=D).items()}.items() if v}
    # boundaries
    bi = []
    for n in (3,):
        for name, t in dict(A=A, C=C, D=D).items():
            if B[:n] != t[:n]:
                bi.append(f"start differs B vs {name}: {' '.join(B[:n])} | {' '.join(t[:n])}")
            if B[-n:] != t[-n:]:
                bi.append(f"end differs B vs {name}: {' '.join(B[-n:])} | {' '.join(t[-n:])}")
    weak = [m for m in r["C_merge"] if m.get("weak_join")]
    if weak:
        bi.append(f"{len(weak)} weak window join(s) in C (<2 overlap tokens aligned)")
    if len(B) and (len(B) - len(C)) / len(B) > 0.15:
        bi.append(f"C shorter than B by {100*(len(B)-len(C))/len(B):.0f}% ({len(C)} vs {len(B)} tokens)")
    if len(B) and (len(B) - len(A)) / len(B) > 0.15:
        bi.append(f"A shorter than B by {100*(len(B)-len(A))/len(B):.0f}% ({len(A)} vs {len(B)} tokens)")
    # numbers / punctuation / case
    numtok = {n: sorted(x for x in t if re.search(r"\d", x)) for n, t in dict(A=A, B=B, C=C).items()}
    numword = {n: sum(1 for x in t if x in NUMW) for n, t in dict(A=A, B=B, C=C).items()}
    punct = {n: len(re.findall(r"[.,;:!?]", s)) for n, s in dict(A=A_raw, B=B_raw, C=C_raw).items()}
    nd = dict(digit_tokens=numtok, number_words=numword, punctuation_marks=punct,
              num_digit_mismatch=len({tuple(v) for v in numtok.values()}) > 1,
              raw_differs_but_normalised_equal=dict(AB=(A == B and A_raw.strip() != B_raw.strip()),
                                                    BC=(B == C and B_raw.strip() != C_raw.strip())))
    # audio quality
    mc = main.get(cid, {})
    f = inv[rid]
    aq = f"clip p95 RMS {mc.get('seg_rms_p95')}, voiced(>=0.01) {mc.get('seg_voiced_frac_fixed_0p01')}; recording floor {f['rms_p10_floor']}, est SNR {f['est_snr_db']} dB"
    quiet = (mc.get("seg_rms_p95") or 1) < LOWLEVEL_P95
    # relay vs replay flush count
    rep_flush = [x for x in r["D_flushes"] if x["pending"]]
    empties = [x for x in rep_flush if x.get("empty")]
    relay_vs_replay = dict(relay_finals=p["finals_received"], replay_pending_flushes=len(rep_flush),
                           replay_empty_text_flushes=len(empties), bench_expected=p["utterances_expected"])
    # status
    mn = min(ag["AB"], ag["AC"], ag["BC"])
    boundary_flag = any(s.startswith(("start differs", "end differs", "C shorter", "A shorter")) for s in bi)
    if mn < AGREE_THR:
        status = "AUDIO_UNCLEAR" if quiet else ("BOUNDARY_SUSPECTED" if boundary_flag and mn >= 0.8 else "PARAKEET_REVIEW_REQUIRED")
    else:
        status = "BOUNDARY_SUSPECTED" if boundary_flag else "PARAKEET_CONSISTENT"
    st.update(status=status, min_pairwise_token_agreement=round(mn, 4), pairwise={k: round(v, 4) for k, v in ag.items()},
              threshold=AGREE_THR, issues=bi + miss[:10], audio_quality_notes=aq, quiet_clip=quiet,
              determinism_B_vs_B2_identical=(B_raw == B2_raw))
    cmp_ = dict(clip_id=cid, definition="token_agreement = 2*M/(|X|+|Y|), M=matching tokens (difflib) on wer.normalize() tokens; machine-vs-machine only, NOT accuracy/WER",
                pairwise_token_agreement={k: round(v, 4) for k, v in ag.items()}, three_way_support_B_pivot=three,
                diff_ops={k: v for k, v in opsd.items()}, numbers_punctuation_case=nd, repeated_adjacent_tokens_any=reps_any,
                repeated_unique_to_one_pass=reps, suspected_missing=miss, boundary_issues=bi,
                pass_D_relay_flush_replay=dict(summary=relay_vs_replay, flushes=r["D_flushes"]))
    (OUTD / f"{cid}.txt").write_text(A_raw + "\n", encoding="utf-8")
    (OUTD / f"{cid}_rerun.txt").write_text(B_raw + "\n", encoding="utf-8")
    (OUTD / f"{cid}_segmented.json").write_text(json.dumps(dict(
        clip_id=cid, method=f"windows {raw['meta']['win_s']} s, hop {raw['meta']['hop_s']} s ({raw['meta']['win_s']-raw['meta']['hop_s']} s overlap), same engine; merged by text alignment (heuristic)",
        windows=r["C_windows"], merge_info=r["C_merge"], merged_transcript=C_raw), indent=1, ensure_ascii=False), encoding="utf-8")
    (OUTD / f"{cid}_comparison.json").write_text(json.dumps(cmp_, indent=1, ensure_ascii=False), encoding="utf-8")
    (OUTD / f"{cid}_status.json").write_text(json.dumps(st, indent=1, ensure_ascii=False), encoding="utf-8")
    ndis = sum(len(v) for v in opsd.values())
    rows.append(dict(
        recording_id=rid, clip_id=cid, source_audio=f"dataset_existing/clips/L30/{cid}.wav",
        original_draft=A_raw, rerun_transcript=B_raw, segmented_transcript=C_raw,
        agreement_percentage=round(100 * mn, 1), agree_AB_pct=round(100 * ag["AB"], 1), agree_AC_pct=round(100 * ag["AC"], 1),
        agree_BC_pct=round(100 * ag["BC"], 1), agree_relay_vs_replay_AD_pct=round(100 * ag["AD"], 1),
        disagreement_count=ndis, suspected_missing_words=" | ".join(miss[:8]),
        suspected_repeated_words=json.dumps(reps_any, ensure_ascii=False) if reps_any else "",
        boundary_issues=" | ".join(bi), audio_quality_notes=aq, status=status))
    per_clip.append(dict(clip_id=cid, recording_id=rid, status=status, pairwise={k: round(v, 4) for k, v in ag.items()}, ndis=ndis,
                         relay_vs_replay=relay_vs_replay, tokens=three,
                         partial_revision_rate=round(p["partial_words_revised"] / p["partial_words"], 3) if p["partial_words"] else None,
                         B_equals_B2=(B_raw == B2_raw)))
    a = rec_agg.setdefault(rid, dict(AB=[], AC=[], BC=[], AD=[]))
    for k in ("AB", "AC", "BC", "AD"):
        a[k].append(ag[k])

fields = ["recording_id", "clip_id", "source_audio", "original_draft", "rerun_transcript", "segmented_transcript", "agreement_percentage",
          "agree_AB_pct", "agree_AC_pct", "agree_BC_pct", "agree_relay_vs_replay_AD_pct", "disagreement_count", "suspected_missing_words",
          "suspected_repeated_words", "boundary_issues", "audio_quality_notes", "status"]
with open("dataset_existing/parakeet_verification_report.csv", "w", newline="", encoding="utf-8-sig") as fh:
    w = csv.DictWriter(fh, fieldnames=fields)
    w.writeheader()
    w.writerows(rows)

def m(v):
    return round(float(np.mean(v)), 4) if v else None
allv = {k: [x["pairwise"][k] for x in per_clip] for k in ("AB", "AC", "BC", "AD", "BD", "B_B2")}
summ = dict(
    scope="Parakeet-only consistency. No reference exists; no WER/S/D/I computed; agreement is not accuracy.",
    engine=raw["meta"], clips=len(raw["clips"]), evaluated=len(per_clip),
    status_counts=dict(Counter(x["status"] for x in per_clip)),
    mean_pairwise_token_agreement={k: m(v) for k, v in allv.items()},
    min_pairwise_token_agreement={k: round(float(min(v)), 4) for k, v in allv.items() if v},
    determinism_B_equals_B2_clips=sum(1 for x in per_clip if x["B_equals_B2"]),
    by_recording={k: {kk: m(vv) for kk, vv in v.items()} for k, v in sorted(rec_agg.items())},
    most_frequent_single_word_changes=[dict(pair=list(k), count=v) for k, v in change_pairs.most_common(25)],
    relay_vs_replay=[dict(clip_id=x["clip_id"], **x["relay_vs_replay"]) for x in per_clip],
    per_clip=per_clip,
    thresholds=dict(agree_thr=AGREE_THR, lowlevel_p95_rms=LOWLEVEL_P95, note="a-priori heuristics, not validated"),
    cannot_calculate=["WER", "substitutions/deletions/insertions vs ground truth", "accuracy", "speaker metrics", "VAD recall/false activation"],
)
Path("results/PARAKEET_ONLY_TRANSCRIPT_CONSISTENCY.json").write_text(json.dumps(summ, indent=1, ensure_ascii=False), encoding="utf-8")
print(json.dumps({k: summ[k] for k in ("status_counts", "mean_pairwise_token_agreement", "min_pairwise_token_agreement", "determinism_B_equals_B2_clips", "by_recording")}, indent=1))
print(summ["most_frequent_single_word_changes"][:12])
for x in per_clip:
    print(x["clip_id"], x["status"], {k: round(v, 3) for k, v in x["pairwise"].items()}, x["ndis"], x["relay_vs_replay"])
