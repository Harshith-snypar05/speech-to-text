# ScriptLiv Phase 6C: follow-up diagnostics on empty Parakeet decodes

Read-only diagnostic. No fix. Engine: production `ParakeetNativeEngine` class, Parakeet TDT 0.6B v3 q8_0, default params, imported read-only (same `parakeet_full` call and `collapse_repetition` as the relay). No relay, VAD, buffering, decoder, model or UI change. Relay PID 67396 was not touched and is still running. `svarah_wer.json` md5 `CCB7FBCF1C434DE7EAABD70BE12EF6C4` unchanged. `phase5_flush_diag.jsonl` still 87 lines. Phase 5 and Phase 6 artifacts untouched.

Outputs, all in `results/phase6c/`:
- `phase6c_results.json`: per clip, per variant: source start/end sample, leading zero samples, sample count, duration, 3 repetitions with text, raw text, segment count, empty flag, decode time.
- `audio/`: 65 WAVs, one per variant.
- Script: `benchmarks/phase6c_diag.py`.

Regression check: the exact slice (condition A) was empty in 3 of 3 reps for all five clips, matching Phase 6. The previous-final replays matched the relay's recorded `text_len` in every rep (same fidelity as Phase 6). Repetitions were identical in every one of the variants (text and empty status), so everything below is deterministic.

Dropped slices (unchanged from Phase 6): assamese_03817 256000-315200, assamese_06152 128000-174400, kannada_00197 128000-172800, kashmiri_03111 128000-182400, bodo_03621 251200-297600.

## Experiment 1: zero-padded left context (exact slice, N zero samples prepended, endpoint unchanged)

| clip | exact | +0.5 s zeros | +1 s zeros | +2 s zeros | Phase 6 real ctx 0.5 / 1 / 2 s |
|---|---|---|---|---|---|
| assamese_03817 | empty | 7 words | 7 words | 7 words | 8 / empty / 13 words |
| assamese_06152 | empty | **empty** | 7 words | 6 words | 7 / 7 / 9 words |
| kannada_00197 | empty | **4 words** | 4 words | 4 words | empty / empty / empty |
| kashmiri_03111 | empty | 9 words | **empty** | **empty** | 10 / 12 / 14 words |
| bodo_03621 | empty | 3 words | 3 words | 3 words | empty / 4 words / 6 words |

- Zeros alone turned the empty decode into text in all five clips, at at least one pad length. Kannada, which never recovered with real audio, recovers at all three pad lengths (identical text "Widely spread cool bhagials.").
- It is not monotonic either: kashmiri works at 0.5 s and is empty at 1 s and 2 s (the opposite of its real-context result); assamese_06152 is empty at 0.5 s.
- Recovered text from zero padding contains only words from the slice itself (no earlier audio is included), but is often partial or garbled (e.g. assamese_06152 "Browse and instill on your no spa." where the Phase 3 reference ends "...send Rs sixty thousand instead on Yono SBI?"). Accuracy was not scored and no human listened.

## Experiment 2: slice-start shifts (no added context, endpoint fixed, sample range = start+shift to original end)

| clip | -200 ms | -100 | -50 | exact | +50 | +100 | +200 |
|---|---|---|---|---|---|---|---|
| assamese_03817 | 8 w | empty | empty | empty | 7 w | 7 w | 5 w |
| assamese_06152 | 6 w | empty | empty | empty | empty | empty | 5 w |
| kannada_00197 | empty | empty | empty | empty | empty | 4 w | 4 w |
| kashmiri_03111 | 10 w | empty | 10 w | empty | empty | 9 w | 10 w |
| bodo_03621 | 1 w ("And") | 1 w | 1 w | empty | 1 w | 3 w | 3 w |

- Moving the cut by 50 ms flips the outcome in most clips; kashmiri goes text, empty, text, empty, empty, text across -200..+100 ms. The outcome is not a smooth function of cut position. This explains Phase 6's non-monotonic assamese_03817 result: any small change in the input can flip it.
- Shifts later than the slice start (+100/+200 ms) recover text in four of five clips; earlier shifts are inconsistent. Starting later does not require extra audio, which supports that the effect is about the input framing, not about missing earlier content.

## Experiment 3: Kannada length sweep and decoder defaults

Decoder defaults (read from `parakeet_full_default_params(GREEDY)` at runtime): strategy greedy (0), n_threads 4, offset_ms 0, duration_ms 0, no_context true, audio_ctx 0, callbacks NULL. Model log: n_audio_ctx 5000 (not a limiting factor at 2.8 s), n_mels 128, n_fft 512. No minimum-length or silence-threshold parameter is exposed in these defaults.

Sweep (end fixed at 172800; sample count shown):

| variant | start-end | samples | result |
|---|---|---|---|
| exact | 128000-172800 | 44800 | empty |
| trim left 0.5 / 1 / 1.5 / 2 s | 136000 / 144000 / 152000 / 160000 - 172800 | 36800 / 28800 / 20800 / 12800 | empty at all four |
| trim right 0.5 / 1 / 1.5 s | 128000 - 164800 / 156800 / 148800 | 36800 / 28800 / 20800 | empty at all three |
| trim right 2 s | 128000-140800 | 12800 | "Widely spread." |
| trim right 0.6 s (relay hang) | 128000-163200 | 35200 | empty |
| zeros +0.5 / 1 / 2 s | zeros + 128000-172800 | 52800 / 60800 / 76800 | 4 words |
| start +100 / +200 ms | 129600 / 131200 - 172800 | 43200 / 41600 | 4 words |
| real left ctx 3 s | 80000-172800 | 92800 | 11 words |
| real left ctx 4 s | 64000-172800 | 108800 | **empty** |
| real left ctx 6 s | 32000-172800 | 140800 | 18 words |
| real left ctx 8 s (from sample 0) | 0-172800 | 172800 | 24 words |

- No monotonic length rule: the empty/non-empty state alternates with length (real context 3 s works, 4 s empty, 6 s works). A 12800-sample slice (0.8 s) of the same audio decodes while 20800-44800 samples mostly do not.
- The 100 ms RMS profile of the slice shows speech-level energy through about 2.0 s and near-silence in the last 0.6 s (the relay hang), so there is no mostly-silent-slice explanation: this slice is loud.

## Experiment 4: overlap with the previous finals

Previous finals were re-derived by replaying the earlier `final_sent` flushes (exact boundaries from Phase 6; lengths verified against the relay record). Matching is word-level on normalized text and is an estimate: "dup" = recovered words that match the tail of the previous final.

| source of recovered text | clip | recovered words | words duplicating previous final |
|---|---|---|---|
| Phase 6 real ctx 0.5 s (B) | assamese_06152 | 7 | 2 |
| Phase 6 real ctx 2 s (D) | assamese_03817 | 13 | about 5 |
| Phase 6 real ctx 2 s (D) | assamese_06152 | 9 | about 2 |
| Phase 6 real ctx 2 s (D) | kashmiri_03111 | 14 | about 5 |
| Phase 6 real ctx 2 s (D) | bodo_03621 | 6 | 4 ("people can easily access" already sent) |
| Phase 6C real ctx 6 s | kannada_00197 | 18 | 14 |
| Phase 6C real ctx 8 s | kannada_00197 | 24 | 20 |
| zero padding, shifts (all clips) | all | 1-10 | 0-1 (only -200 ms shifts that reach back, e.g. one leading word) |

- Real left context re-decodes audio that was already finalised, so duplicated words rise with context length (up to 14 of 18 and 20 of 24 for Kannada at 6-8 s).
- Zero padding and later-start shifts do not include earlier audio, so no duplication, but they gave fragmentary text.

## Comparison with Phase 6

- Confirmed again: exact-slice emptiness, reproducible across reps.
- Changed interpretation: Phase 6 suggested real left context was the helpful factor (4 of 5). Phase 6C shows zeros do at least as well (5 of 5 at some pad, including Kannada) and that a 50 ms cut change flips results. So content of the added audio is not required to avoid the empty result, and Phase 6's "insufficient left context" explanation is not supported as stated.
- Kannada: unresolved in Phase 6, now shown to be not about the audio being loud, short or quiet. It decodes with zeros, with a +100 ms start, or with 3, 6 or 8 s of real context, and not with exact, 4 s, or most truncations.

## Confirmed findings
1. The exact slice decodes empty deterministically for all five clips (also with 3 reps).
2. The outcome is highly sensitive to small, content-free input changes: 50 ms start shifts and leading zeros each flip empty and non-empty states in most clips.
3. Real left context re-decodes already finalised words (measured duplication up to 20 of 24 words).
4. The relay's flush logic is not the cause (Phase 5 plus the replay fidelity here).
5. Decoder defaults: greedy, 4 threads, no_context, audio_ctx 0; no length parameter. Source inspection also shows the log-mel front end normalizes features per call over the input.

## Unresolved hypotheses (not tested)
- That the per-call mel normalization (mean and std computed over the input slice) is the mechanism behind the sensitivity. It fits the pattern (any change to the slice changes the feature statistics) but no experiment here isolates it; testing it needs engine instrumentation or feature dumps, which were out of scope.
- That the greedy TDT decode emitting only blank tokens for these inputs is the proximate cause. Not observed directly (token-level output is not exposed by the API used).
- Whether the zero-pad or shift recoveries are accurate. Text was not scored against references and only five slices were used.

## Is a remedy justified?
- Overlap context: not justified by this evidence. It is unreliable (kannada empty at 4 s; assamese_03817 empty at 1 s in Phase 6), and it makes the relay emit duplicate words the earlier final already contained.
- Empty-result handling: the supported conclusion is that silent drops lose recoverable speech and that the empty state is fragile, not a sign of absent speech. Options such as logging/surfacing the empty flush, or retrying an empty decode with a perturbed input (zero pad or small start shift), are candidates. A perturbation retry recovered text in 5 of 5 clips at some setting, but it is untested for harm (hallucination on real silence, partial/garbled text, latency, behaviour on slices that already decode) and would change emission behaviour. It needs a separate, approved design and validation.
- Neither is proven correct. If forced to choose, the data favours empty-result handling over overlap context.

## Remaining risks and limits
- Only five slices and one audio source (Svarah); the finding may differ for other speech.
- No human listened; recovered text quality is unscored.
- Decode times in this run were much higher than Phase 6 (median 2.5 s, max 12.1 s, versus about 0.25-0.5 s before). The machine had other Python processes running; I did not verify the cause. Text results were identical across reps, so it does not affect the findings, but the latencies here should not be used for performance conclusions.
- Overlap counts are fuzzy-match estimates on short strings.
- Phase 7B concurrency (shared worker queue, 10 s final-flush timeout) is separate and not examined here.

Stopping here. No fix implemented; waiting for approval.
