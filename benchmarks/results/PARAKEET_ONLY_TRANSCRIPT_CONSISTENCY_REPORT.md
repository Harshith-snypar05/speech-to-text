# Parakeet-only transcript consistency report (20 pilot clips)

Engine for every pass: production `ParakeetNativeEngine`, `ggml-parakeet-tdt-0.6b-v3-q8_0.bin`, default parameters, CPU, loaded once. No other ASR, no model/parameter change, no production file modified. All transcripts below are **MACHINE_GENERATED_UNVERIFIED**. No human or ground-truth verification exists. `HUMAN_VERIFIED` / `GROUND_TRUTH_VERIFIED` are not used anywhere.

Labels: **MEASURED** = computed from runs. **CONSISTENCY** = machine-vs-machine similarity, not correctness. **POTENTIAL ISSUE** = suspicion needing human audio check. **UNVERIFIED** = assumption. **CANNOT CALCULATE** = needs ground truth.

## 1. Passes
| pass | what | script |
|---|---|---|
| A | original relay draft (streaming path; utterance-split by production VAD). Preserved unchanged in `dataset_existing/pilot/drafts/`. | from earlier pilot |
| B | full-clip offline `transcribe_final()` (independent re-transcription, native path) | `parakeet_consistency.py` |
| B2 | identical call repeated (determinism check, not independent evidence) | same |
| C | 8 s windows, 6 s hop (2 s overlap), each transcribed, merged by text alignment (heuristic) | same |
| D | offline replay of production `UtteranceBuffer` (production config) with `transcribe_final()` on each flush. Extra pass used for Task 5. | same |

Comparison: `analyze_consistency.py`. Raw: `results/parakeet_raw_passes.json`.

## 2. Definition of "agreement" (not accuracy)
`token_agreement(X,Y) = 2*M / (|X|+|Y|)`, M = tokens in difflib matching blocks, on `wer.normalize()` tokens (lowercase, punctuation stripped, no number mapping). Symmetric: neither side is a reference. It is **not accuracy, not WER**: two runs can agree and both be wrong, and the same wrong word repeated counts as agreement. "diff ops" in the JSON are alignment operations, not substitutions/deletions/insertions against truth. Column `agreement_percentage` in the CSV is the minimum of A-B, A-C, B-C.

## 3. Results (CONSISTENCY, MEASURED, 20 clips, 0 inference failures)
| pair | mean | min |
|---|---|---|
| A vs B (relay draft vs full-clip rerun) | 0.922 | 0.681 |
| B vs C (full clip vs segmented) | 0.909 | 0.500 |
| A vs C | 0.888 | 0.487 |
| B vs B2 (identical repeat) | 1.000 | 1.000 |
| A vs D (relay draft vs offline replay of its flushes) | 1.000 | 1.000 |
| B vs D | 0.922 | 0.681 |

Per recording mean A-B / B-C: rec01 .911/.950, rec02 .926/.931, rec03 .963/.916, rec04 .976/.961, rec05 .940/.929, **rec06 .797/.726**, rec07 .947/.954 (`PARAKEET_ONLY_TRANSCRIPT_CONSISTENCY.json` has all).

Key observations:
1. **The model is deterministic**: B2 equals B on 20/20 clips. A rerun adds no independent evidence. "Independent re-transcription" with the same model and same input is the same output.
2. **Relay output equals offline decode of the same flush snapshots**: A equals D on 20/20 clips (empty-text flushes contribute nothing). So differences A-B come from how the audio is split (VAD flush segmentation), not from streaming, WebSocket or partial handling. This is strong, MEASURED evidence for that scope. Partial decodes are not covered (partial texts were never stored).
3. Splitting changes text: splitting a clip into utterances (A) or windows (C) changes words versus decoding the whole clip (B). Agreement is lower for C (windowing at fixed 8 s ignoring speech) than A.
4. rec06 is the outlier (conversational, multilingual-sounding names, accented). Lowest clip rec06_L30_0015: A-B 0.68, B-C 0.50. See section 7.

## 4. Status counts (a-priori heuristics, NOT validated)
Rules: min(A-B, A-C, B-C) < 0.90 and quiet clip (clip p95 RMS < 0.05) -> `AUDIO_UNCLEAR`; < 0.90 otherwise -> `BOUNDARY_SUSPECTED` if first/last 3 words differ or a >15% length shortfall and min >= 0.80, else `PARAKEET_REVIEW_REQUIRED`; >= 0.90 -> `BOUNDARY_SUSPECTED` if first/last 3 words of B differ from A/C/D or a weak window join exists, else `PARAKEET_CONSISTENT`. `NOT_EVALUATED` on error (none).

| status | clips |
|---|---|
| PARAKEET_CONSISTENT | 6 (rec03_0024, rec03_0094, rec04_0092, rec06_0023, rec07_0016, rec07_0026) |
| BOUNDARY_SUSPECTED | 10 |
| AUDIO_UNCLEAR | 2 (rec01_0048, rec01_0077) |
| PARAKEET_REVIEW_REQUIRED | 2 (rec06_0006, rec06_0015) |
| NOT_EVALUATED | 0 |

Caveats: the thresholds (0.90, RMS 0.05, 3-word boundary) were fixed before the run but are arbitrary. `BOUNDARY_SUSPECTED` is loose: A and D are utterance-split by design, so their first/last words naturally differ from B; treat it as "check the edges", not as a confirmed loss. `AUDIO_UNCLEAR` is assigned from low level + disagreement only; no audibility was assessed. `PARAKEET_CONSISTENT` means only that the passes agreed at >= 0.90. It does not mean correct.

## 5. Words that change, numbers, punctuation (MEASURED counts, POTENTIAL ISSUES)
- Frequently changing single-word pairs (each only 2 occurrences, so no stable pattern): issues/reshores, fast/first, use/used, to/two, unex/unix, fok/folk, 0/zero, 1/one, an/the, lame/live, enough/not, arya/hola. Full list in the JSON (`most_frequent_single_word_changes`).
- Technical terms: Unix spelled `unex`/`unix`/`unix unix`, `fok/folk`, `reshores/issues`. Terminology is not consistent across passes. Whether any is right: CANNOT CALCULATE.
- Numbers: 2 clips differ in digit/number-word form (rec04_0024: A has two number words, B and C have digits `0`,`1`; rec01_0077: digit tokens differ by one). Digit-vs-word forms ("0" vs "zero", "1" vs "one") count as disagreement under `wer.normalize` (no number mapping), which lowers agreement without any actual misrecognition.
- Punctuation: marks differ between passes on most clips (e.g. rec05_0011 A 16, B 26, C 22; rec02_0052 A 11, B 15, C 17). Normalised tokens ignore punctuation, so this does not affect agreement but affects any raw-text scoring and sentence boundaries.
- Case-only/punctuation-only differences are flagged per clip (`raw_differs_but_normalised_equal`).

## 6. Repeated words (POTENTIAL ISSUES; repetition may be real speech)
10 clips contain adjacent repeats. Repeats present in all passes (`these these`, `this this`, `no no`, `sorry sorry`, `big big`) are likely genuine speech or stable model behaviour. Repeats in only one pass are more suspect: `unix unix`, `so so` (A and D only, rec03_0024), `on on` (A, D, rec07_0007), `good good` and `they they` (C only, likely window overlap duplicates), `idaho idaho` (C only). Window-merge duplicates are a known weakness of pass C's alignment heuristic. Not confirmed by listening.

## 7. Segmentation boundaries and loss (POTENTIAL ISSUES)
- C vs B: 13 weak window joins (<2 overlap tokens aligned) across 10 clips; 2 windows returned empty text (rec01_0019, rec06_0015). C is shorter than B by >15% on rec06_0015 (28 vs 48 tokens).
- rec06_0015 detail: the 6-14 s window returned empty text (window 1); windows 2-4 begin mid-phrase ("So beautiful just like..."). B text for the same region: "Pooja? Okay. But your sandy looks so beautiful..." (names differ: Pooja/Puja, Sandip/Sandeep/Sandy). So C lost the "Pooja ... coconut tree ... Papa ka" content. Reasonable reading: a window cut inside speech made the model return nothing or fragments. This is a model behaviour on short context plus my merge heuristic; cause beyond that is UNVERIFIED.
- rec05_0011: B ends with "...Cause English is becoming"; A and D end at "...other languages." The last words were not in any final. In the replay the last flush (39.2 s, 0.9 s snapshot, 0.3 s speech) returned empty text, so those words were either cut by the clip end or too short to decode alone. Clip-boundary effect on the 30 s cut (clip ends mid-sentence) is the evidenced explanation. The rest of the 102 vs 120 gap (18 tokens) was not located; per-word diff in `_comparison.json`. Needs listening.
- Empty-text flushes (replay): rec02_0052, rec03_0094, rec05_0004, rec05_0011, rec07_0007, rec07_0026: 6 clips, 1 each. Each matches a clip where relay finals < pending flushes (section 8 of `RELAY_PILOT_INVESTIGATION.md`).

## 8. Partial vs final (MEASURED from pilot JSON; partial texts not stored)
Partial words 1,116 across 20 clips. Revision rate 0.331 (partial word differs from the final word at the same index), prefix-stable rate 0.302. Because only incremental words after `words_sent` are emitted and never retracted, the relay UI shows words that the final transcript later changes. This is a stability measure, not an accuracy measure. A partial-vs-final word comparison cannot be done from stored data (texts not recorded). Pass D shows finals equal the offline decode, so the partial/final gap is the whole-buffer partial decode on a shorter buffer versus the final decode on the complete snapshot. Direction of correctness: CANNOT CALCULATE.

## 9. Measured vs not
| class | content |
|---|---|
| MEASURED | all values in sections 3, 4, 5 counts, 7 counts, 8 |
| CONSISTENCY | agreement tables; determinism; A = D |
| POTENTIAL ISSUES | clips in `BOUNDARY_SUSPECTED`, `AUDIO_UNCLEAR`, `PARAKEET_REVIEW_REQUIRED`; terminology variants; unique repeats; empty windows/flushes |
| UNVERIFIED | every transcript's correctness; thresholds; whether quiet means unclear; merge-heuristic losses |
| CANNOT CALCULATE | WER, substitutions/deletions/insertions vs truth, accuracy, per-speaker metrics, VAD recall/false activation, per-word correctness |

WER is **not computable** yet: zero verified references exist (pilot manifest `reference` is empty). Using Parakeet output as a reference for another Parakeet output was not done and would be invalid.

## 10. Files
`dataset_existing/transcripts_parakeet/` (100 files: `<id>.txt` primary = original relay draft text, `<id>_rerun.txt`, `<id>_segmented.json`, `<id>_comparison.json`, `<id>_status.json`); `dataset_existing/parakeet_verification_report.csv`; `results/PARAKEET_ONLY_TRANSCRIPT_CONSISTENCY.json`; `results/parakeet_raw_passes.json`. The `<id>.txt` primary file holds the original draft text with the UNVERIFIED header stripped; the original draft files are untouched.
