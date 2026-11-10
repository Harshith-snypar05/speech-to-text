"""Writes the markdown deliverables from results/SVARAH_INSERTION_ANALYSIS.json (no ASR, no baseline writes)."""
import json
from collections import Counter
from pathlib import Path

d = json.load(open("results/SVARAH_INSERTION_ANALYSIS.json", encoding="utf-8"))
P = d["per_clip"]; N = d["normalization_comparison"]; cats = d["insertion_categories"]
L = d["latency_matching"]; AU = d["latency_audit"]


def sid(i): return i.replace("svarah_", "")[:24]
def pct(a, b): return f"{100*a/b:.1f}%"
def esc(t): return t.replace("|", "\\|").replace("\n", " ")


ranked = sorted(P, key=lambda c: (-c["A"]["ins"], -c["A"]["errors"]))
tot_ins = sum(c["A"]["ins"] for c in P)
top5 = sum(c["A"]["ins"] for c in ranked[:5]); top10 = sum(c["A"]["ins"] for c in ranked[:10])
nz = sum(1 for c in P if c["A"]["ins"] > 0)
sub = Counter()
for c in P:
    for i in c["insertion_detail"]:
        k = i["category"]
        if k.startswith("1"):
            k += ":resolved_by_C" if "equals the reference" in i["evidence"] else ":value_mismatch"
        if k.startswith("7"):
            for s in ("number_without_numeric_reference", "symbol_verbalisation", "lexical_model_stable", "lexical_unexplained"):
                if s in i["evidence"]:
                    k += ":" + s
        sub[k] += 1
fill_in_ref = sum(1 for c in P for i in c["insertion_detail"] if i["category"].startswith("2") and "contains it: True" in i["evidence"])
mism = [c for c in P if c["finals"] != c["expected"]]
dele_all = sum(c["A"]["dele"] for c in P); dele_mm = sum(c["A"]["dele"] for c in mism)
off = N["offline_fullclip_policy_A"]; A = N["A"]
num_n = cats.get("1_numeric_representation", 0)

# ---------------- insertion analysis
o = ["# Svarah insertion analysis (Phase 3)", "",
     "Scope: error analysis of the existing Svarah run (`results/svarah_wer.json`, unchanged baseline: 1,630 reference words, S 134 / D 44 / I 198, WER 23.07% [17.9-29.5]). No benchmark rerun, no production change, no fix implemented. Reference = Svarah's own transcripts (independent of Parakeet). Machine evidence only: **no human listened to any audio** (I cannot play audio). Audio-path evidence is limited to an offline full-clip decode by the same Parakeet engine (`svarah_offline_decode.py`, `results/svarah_offline_fullclip.json`; no VAD, no relay).", "",
     "## 1. Where insertions sit",
     f"- {tot_ins} insertions in {nz} of 60 clips. Top 5 clips hold {top5} ({pct(top5,tot_ins)}); top 10 hold {top10} ({pct(top10,tot_ins)}). A few clips drive the aggregate.",
     "- Alignment: token-level Levenshtein on `wer.normalize` tokens. Per-token classification reproduces the baseline S/D/I exactly (asserted per clip).", "",
     "## 2. Classification of the 198 inserted tokens (rule-based; evidence stored per token in the JSON)", "",
     "| # | category | count | share | evidence rule |", "|---|---|---|---|---|"]
rules = {
    "1_numeric_representation": "token is a digit/number word AND (hypothesis group equals reference after policy C = resolved) OR (reference clip has a numeric token but values differ = value_mismatch)",
    "2_filler_disfluency": "token in {uh um umm hmm er ...}",
    "3_repeated_word_or_phrase": "identical adjacent token or bigram in hypothesis (number tokens go to 1)",
    "4_compound_hyphenation": "token merges with neighbour into a word present in reference (policy D)",
    "5_genuine_additional_words": "NOT ASSIGNABLE without human listening. Zero tokens assigned. Candidates are in 7 (lexical_*).",
    "6_possible_vad_segmentation": "token within 2 tokens of a relay final boundary AND absent from the offline full-clip decode",
    "7_other": "remainder; subtype in JSON"}
for k in ["1_numeric_representation", "2_filler_disfluency", "3_repeated_word_or_phrase", "4_compound_hyphenation", "5_genuine_additional_words", "6_possible_vad_segmentation", "7_other"]:
    n_ = cats.get(k, 0)
    o.append(f"| {k[0]} | {k[2:]} | {n_} | {pct(n_,tot_ins)} | {rules[k]} |")
o += ["", "Subtypes (inserted tokens):", ""]
for k, v in sorted(sub.items()):
    o.append(f"- `{k}`: {v}")
o += ["",
      f"Fillers: {cats.get('2_filler_disfluency',0)} inserted filler tokens; {fill_in_ref} also occur somewhere in the same clip's reference. The reference omits most of them. Whether the speaker said them is unverified. The offline full-clip decode also emits fillers in the clips checked (e.g. hindi_03150: relay `uh uh uh s uh uh`, offline `uh s uh`), so fillers are model output, with some extra repeats on the relay path.", "",
      "## 3. What explains the largest share",
      f"Numeric representation: {num_n} of {tot_ins} ({pct(num_n,tot_ins)}). References write phone/UAN/PRAN/UPI numbers as digit strings; Parakeet writes spoken digit words, one token per digit. {sub.get('1_numeric_representation:resolved_by_C',0)} of these are pure formatting (group equals reference after policy C). {sub.get('1_numeric_representation:value_mismatch',0)} sit in groups whose digits still differ from the reference after C: digit-word expansion mixed with a digit error (extra, dropped or changed digit); not separable per token without listening. Examples: punjabi_00253 hyp digits `2886144536785` vs ref `288614536785` (extra 4); sindhi_04981 UAN hyp `29546922497` vs ref `295546922497`.", "",
      "## 4. Ranked clips by insertion count (top 15 full text; all 60 in the JSON)", "",
      "| rank | clip | ref words | S | D | I | total | reference | Parakeet transcript |", "|---|---|---|---|---|---|---|---|---|"]
for r, c in enumerate(ranked[:15], 1):
    o.append(f"| {r} | {sid(c['id'])} | {c['ref_words']} | {c['A']['sub']} | {c['A']['dele']} | {c['A']['ins']} | {c['A']['errors']} | {esc(c['reference'])} | {esc(c['hypothesis'])} |")
o += ["", "Remaining 45 clips (text cut to 110 chars; full text in JSON `per_clip`):", "",
      "| rank | clip | ref words | S | D | I | total | reference | Parakeet transcript |", "|---|---|---|---|---|---|---|---|---|"]
for r, c in enumerate(ranked[15:], 16):
    o.append(f"| {r} | {sid(c['id'])} | {c['ref_words']} | {c['A']['sub']} | {c['A']['dele']} | {c['A']['ins']} | {c['A']['errors']} | {esc(c['reference'][:110])} | {esc(c['hypothesis'][:110])} |")
o += ["", "## 5. Audio inspection: done and not done",
      "- Not done: listening. Categories needing human judgement (genuine extra speech vs reference omission, whether a filler was spoken) are not assigned.",
      "- Done: offline full-clip decode, same engine, whole clip, no VAD. Used as segmentation evidence for category 6. Audio statistics per clip are in the JSON.",
      f"- Offline full-clip under baseline normalisation: S {off['sub']} / D {off['dele']} / I {off['ins']}, WER {100*off['wer']:.2f}% [{100*off['ci95'][0]:.1f}-{100*off['ci95'][1]:.1f}]. Relay path: S {A['sub']} / D {A['dele']} / I {A['ins']}. So the relay path (VAD segmentation) adds {A['ins']-off['ins']} insertions and {A['dele']-off['dele']} deletions versus whole-clip decode, and the model alone already produces {off['ins']} insertions. One run, 60 clips.", "",
      "## 6. Limitations",
      "- 60 clips, one speaker each; many first-language groups have 1-4 clips; no group-level claim.",
      "- Categories are heuristics; `7_other` is the honest remainder, not a claim of hallucination. Category 5 is empty by design.",
      "- Offline decode is the same engine: agreement with it shows model stability, not correctness.",
      "- Reference conventions (digits, `Rs.`, `bi-weekly`) differ from model output; a mismatch is not automatically a model error.",
      "- Maithili_04468 hypothesis contains Cyrillic tokens (`Фо ван`); `normalize` strips them, so they do not appear as errors under any policy here.", ""]
Path("results/SVARAH_INSERTION_ANALYSIS.md").write_text("\n".join(o), encoding="utf-8")


# ---------------- normalization
def row(k, name):
    v = N[k]
    return f"| {k} | {name} | {v['ref_words']} | {v['sub']} | {v['dele']} | {v['ins']} | {v['errors']} | {100*v['wer']:.2f}% | {100*v['ci95'][0]:.1f}-{100*v['ci95'][1]:.1f} |"


n = ["# Svarah WER normalization comparison (Phase 3)", "",
     "Policies are applied to **copies** of reference and hypothesis tokens inside the analysis script. Original references, transcripts and `results/svarah_wer.json` are unchanged. Micro-averaged corpus WER with the same bootstrap method as `wer.corpus_wer` (60 clips). Normalized WER is a **diagnostic of formatting vs content**, not an accuracy improvement, and must not be quoted as the system's WER.", "",
     "## Policies (explicit; code in `svarah_error_analysis.py`)",
     "- **A** baseline raw: `wer.normalize` (lowercase, curly apostrophe to `'`, hyphen to space, strip chars outside `[a-z0-9' ]`, no number handling).",
     "- **B** case + punctuation: identical to A by construction (A already lowercases and strips punctuation). Same numbers.",
     "- **C** number format, both sides: `1,000` to `1000`; `3.5` to `3 point 5`; `%` to `percent`; runs of 2+ single digits or digit words become one digit string; runs of number words (units, teens, tens, hundred, thousand, lakh, crore, million; `and` only between number words) become an integer string.",
     "- **D** compound: C plus symmetric join of adjacent tokens `x y` to `xy` when `xy` (length 4+, not digits) occurs as a token on the other side (data-driven; touches only pairs where the other side holds the joined form).",
     "- **E** supplementary, not requested, non-standard: D plus removal of filler tokens {uh um umm uhh uhm hmm hm mm mmm ah er erm eh huh} on both sides.", "",
     "## Results", "",
     "| policy | name | ref words | S | D | I | errors | WER | CI95 (%) |", "|---|---|---|---|---|---|---|---|---|",
     row("A", "raw baseline"), row("B", "case+punctuation"), row("C", "number format"), row("D", "compound"),
     row("E", "D + filler removal (suppl.)"), row("offline_fullclip_policy_A", "offline full-clip, policy A (suppl., no VAD)"), "",
     "Reference word counts differ across C/D/E because number groups and joins change token counts on both sides.", "",
     "## What changed",
     f"- A to C: {A['errors']-N['C']['errors']} fewer errors ({A['errors']} to {N['C']['errors']}); insertions {A['ins']} to {N['C']['ins']}. Digit-word expansion vs digit-string references: formatting-related.",
     f"- C to D: {N['C']['errors']-N['D']['errors']} fewer errors (compound/hyphenation: small).",
     f"- Formatting-related total (A to D): {A['errors']-N['D']['errors']} of {A['errors']} errors ({pct(A['errors']-N['D']['errors'],A['errors'])}). Treat as approximate: a digit string that still differs after C collapses to 1 substitution, so real digit errors are partly hidden rather than removed.",
     f"- D to E: {N['D']['errors']-N['E']['errors']} fewer errors from dropping fillers (insertions {N['D']['ins']} to {N['E']['ins']}). Convention-dependent: references omit most `uh`/`um`; whether they were spoken is unverified. Not counted as formatting in the headline.",
     f"- Residual under D: {N['D']['errors']} errors ({pct(N['D']['errors'],A['errors'])} of baseline). These are not explained by the formatting policies. They contain real recognition differences but also unnormalised reference conventions (`Rs.`/rupees, names, spellings). This is **not** a measured genuine-error count.",
     "- CIs overlap heavily across policies; differences between C, D and E are suggestive, not tested.", "",
     "## Formatting vs genuine (summary)", "",
     "| kind | evidence | errors |", "|---|---|---|",
     f"| formatting (number) | A to C | {A['errors']-N['C']['errors']} |",
     f"| formatting (compound) | C to D | {N['C']['errors']-N['D']['errors']} |",
     f"| disfluency convention (uncertain) | D to E | {N['D']['errors']-N['E']['errors']} |",
     f"| not explained by these policies | residual after E | {N['E']['errors']} |", "",
     "## Limitations",
     "- C can hide digit errors by converting many token errors into one substitution.",
     "- D uses the other side to decide joins, so it can only lower errors: optimistic.",
     "- Names and entities (Vahida/Wahida, Ghanim, bagyals) and non-Latin output are not normalised.", ""]
Path("results/SVARAH_WER_NORMALIZATION_COMPARISON.md").write_text("\n".join(n), encoding="utf-8")


# ---------------- latency
def D(v): return f"n={v['n']}, p50 {v['p50']}, p95 {v['p95']}, max {v['max']}, mean {v['mean']}"


t = ["# Svarah latency matching audit (Phase 3)", "",
     "Source: `final_times_s`, `expected_detail`, `ttfw_s`, `final_latency_s` in `results/svarah_wer.json` (unchanged). `ws_bench.py` not modified; matching is a separate offline recomputation.", "",
     "## Problem", "`ws_bench.analyse_clip` pairs finals with expected utterances by position. When final count differs, later pairs shift or vanish. Expected utterances come from `simulate_flushes`, a mirror of the VAD, so VAD timing is circular.", "",
     "## Proposed timestamp matching (implemented offline in `svarah_error_analysis.py`)",
     "Expected flush time `F_k = end_k + 0.6 s` (hang) for non-forced utterances, `end_k` for forced. A final at time `f` goes to the expected utterance with the largest `F_k <= f + 0.2 s`, one-to-one and monotonic. A second final in the same window is `extra`; an expected utterance with no final is `unmatched`. TTFW is recomputed only when the group's first-message time (`ttfw_s[i] + start_i`) is stored (index below expected count), not before expected start, and not after the final (+0.01 s). Unmatched events get no latency.", "",
     "## The six count-mismatch clips", "",
     "| clip | expected | received | missing final(s) | extra final(s) | index pairing = timestamp pairing |", "|---|---|---|---|---|---|"]
for a in AU:
    if a["mismatch"]:
        miss = "; ".join(f"exp#{u['expected_index']} {u['start']:.1f}-{u['end']:.1f}s" for u in a["unmatched_expected"]) or "-"
        ext = "; ".join(f"final#{u['final_index']} at {u['time']:.3f}s" for u in a["extra_finals"]) or "-"
        t.append(f"| {sid(a['id'])} | {a['expected']} | {a['finals']} | {miss} | {ext} | {a['index_pairing_equals_timestamp_pairing']} |")
t += ["", "Pattern (evidence: `expected_detail`, final times, offline decode):",
      "- 5 clips lose the **last expected utterance** (assamese_03817, assamese_06152, kannada_00197, kashmiri_03111 after forced 8 s caps; bodo_03621 a short tail). The missing words are present in the offline full-clip decode and absent from the relay text. Why no final was sent is not instrumented. The relay sends a final only when decoded text is non-empty, which is consistent with this but **unverified** here.",
      "- bengali_01831 has 1 **extra** final: two finals 0.142 s apart (8.851 s, 8.993 s) after the forced cap at 8.1 s, then 13.915 s. Index pairing gave its second group a final latency of -3.807 s (impossible), an artefact.", "",
      "- Did index pairing shift latencies? In the 5 missing-final clips every received final was paired with its own expected utterance (old pair = timestamp pair), so **no shift**; the lost utterance simply has no entry. Only bengali_01831 shifted (final#1 was paired with expected#1). The `index pairing = timestamp pairing` column is False for all six because the counts differ, not because values moved.",
      f"- Deletions: these six clips hold {dele_mm} of {dele_all} baseline deletions ({pct(dele_mm,dele_all)}) with 10% of the clips. Offline full-clip decode has D {off['dele']} against relay D {A['dele']}.", "",
      "## Latency distributions (seconds)",
      f"- Old (index-paired) TTFW: {D(L['old_all']['ttfw'])}",
      f"- Corrected TTFW: {D(L['corrected_all']['ttfw'])}",
      f"- Old final latency (final minus utterance end): {D(L['old_all']['final_latency'])}",
      f"- Corrected final minus utterance end: {D(L['corrected_all']['final_after_end'])}",
      f"- Corrected final minus expected flush time (end + hang if not forced), i.e. relay processing after the VAD fires: {D(L['corrected_all']['final_after_flush'])}",
      f"- Mismatch clips only, old TTFW: {D(L['mismatch_clips_old']['ttfw'])}; corrected: {D(L['mismatch_clips_corrected']['ttfw'])}",
      f"- Mismatch clips only, old final latency: {D(L['mismatch_clips_old']['final_latency'])}; corrected after-flush: {D(L['mismatch_clips_corrected']['final_after_flush'])}", "",
      "Effect: 6 of 60 clips mismatch and hold 13 of 196 events, so the aggregate barely moves (TTFW p50 0.891 to 0.889, p95 2.172 to 2.174). The correction matters per clip: one impossible negative latency removed, 5 unmatched expected utterances and 1 extra final now reported. The TTFW max 7.585 s is a group where no partial arrived before the final, in a **matched** clip (bengali_00427), unrelated to pairing.", "",
      "Clips where index pairing differs from timestamp pairing: " + ", ".join(sid(x) for x in L["clips_where_index_and_timestamp_pairing_differ"]) + ".", "",
      "## Limits",
      "- Clock is audio-position seconds (real-time replay). `F_k` uses the 0.6 s hang and the 8 s cap from the relay config.",
      "- A match is defensible only when one final falls in an expected flush window; no latency is computed for unmatched events.",
      "- Expected utterances still come from the VAD mirror: this fixes pairing, it does not validate segmentation.",
      "- Partial texts/times were not stored: partial-level latency is not recomputable. 6 clips, 6 anomalous events: small sample.", ""]
Path("results/SVARAH_LATENCY_MATCHING_AUDIT.md").write_text("\n".join(t), encoding="utf-8")
print("ok", dele_mm, dele_all, top5, top10, nz, dict(sub))
