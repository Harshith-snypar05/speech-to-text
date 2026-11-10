# ScriptLiv Phase 4: benchmark reliability and missing-final diagnostics

Engine unchanged: NVIDIA Parakeet TDT 0.6B v3 q8_0. No model, decoding, VAD, silence-hang, forced-cap, buffering or product/UI change. Baseline `results/svarah_wer.json` and all Phase 3 outputs are untouched (md5 `ccb7fbcf...` before and after the rescore). No relay restart, no benchmark rerun.

## What changed

| area | file | change |
|---|---|---|
| Task 1 matching | `benchmarks/latency_match.py` (new) | Timestamp matching, one-to-one, monotonic. Explicit `unmatched_expected` and `extra_finals`. No negative latency (value becomes `None` plus a note). TTFW and final latency are separate fields. Raw timestamps kept. |
| Task 1 integration | `benchmarks/ws_bench.py` | `analyse_clip` uses `match_events`. Adds `events_raw` (unrounded `[t, is_partial, text]`), `latency_match` (pairs, unmatched, extra, counts), `final_after_flush_s`, `legacy_index_paired` (old method, comparison only). `aggregate` adds `latency_matching` totals. Applies to future runs only. |
| Task 3 WER | `benchmarks/wer_policies.py` (new) | Raw, number-normalized (Phase 3 policy C), compound-normalized (policy D). No filler removal. |
| Task 3 integration | `benchmarks/ws_bench.py` | Per clip: `wer_raw`, `wer_number_normalized`, `wer_compound_normalized`. Summary: same three plus `wer_note`. The existing `wer` fields stay raw. |
| Task 3 rescore | `benchmarks/phase4_rescore.py` (new) | Offline, reads the baseline read-only, writes new `results/svarah_phase4_rescore.json`. Asserts the baseline reproduces (S134 / D44 / I198). |
| Task 2 | `relays/core/flush_diagnostics.py` (new), `relays/core/speaker_session.py` | Env-gated flush logging (below). |
| Correlation | `benchmarks/flush_correlate.py` (new) | Joins a diagnostic JSONL with a ws_bench result: per clip, which relay flush covers each unmatched expected utterance and why no final came out. |

## Task 3: WER, three separate fields

| policy | WER | 95% CI | S / D / I | ref words |
|---|---|---|---|---|
| raw (baseline) | 23.07% | 17.9-29.5 | 134 / 44 / 198 | 1630 |
| number-normalized (C) | 17.26% | 13.7-21.7 | 119 / 47 / 115 | 1628 |
| compound-normalized (D) | 16.56% | 13.1-20.9 | 113 / 43 / 113 | 1624 |

**Normalized WER is a diagnostic. It does not represent improved recognition accuracy:** the transcripts are identical, only the scoring convention differs. The reference word count changes slightly because number runs collapse into one token. Raw WER is the baseline and is never replaced. Numeric output conversion in the product stays a separate, deferred decision.

## Task 1: timestamp matching

Rule: expected flush time F = end + 0.6 s (silence hang) or end (forced cap). A final at time f goes to the latest expected utterance with F - 0.2 s <= f, each expected utterance takes at most one final, matches are monotonic. Leftovers are reported, never paired.

Applied to the stored Svarah run (offline, finals only):
- 196 matched pairs, 5 unmatched expected utterances, 1 extra final. This equals the Phase 3 audit.
- Final minus utterance end: p50 0.911, p95 1.500, max 1.890 s. Final minus flush reference: p50 0.413, p95 1.036, max 1.563 s. No negative values (the old -3.807 s of bengali_01831 is gone: its duplicate at 8.993 s is an extra final).
- TTFW was not recomputed from the baseline: partial message times were never stored there. Future runs store them (`events_raw`).

Unmatched expected utterances (all are the LAST utterance of the clip):

| clip | expected # | span (s) | kind |
|---|---|---|---|
| assamese_03817 | 2 | 16.2-19.1 | silence-hang flush, after a forced cap |
| assamese_06152 | 1 | 8.1-10.3 | silence-hang flush, after a forced cap |
| kannada_00197 | 1 | 8.1-10.2 | silence-hang flush, after a forced cap |
| kashmiri_03111 | 1 | 8.2-10.8 | silence-hang flush, after a forced cap |
| bodo_03621 | 6 | 16.3-18.0 | silence-hang flush, no forced cap in the clip |

Known limit: expected utterances come from `simulate_flushes`, which mirrors the relay VAD, so this checks the relay against its own simulated timing, not VAD quality.

## Task 2: diagnostic logging

Enabled only when env var `STT_FLUSH_DIAG_FILE` is set (JSONL, append). Unset, it does nothing. Every write is wrapped so a logging failure cannot reach the relay. No transcript text is logged, only length and word count.

One record per `flush()` call:
- ids: `conn_id` (one per speaker connection, process-wide counter), `session_id`, `seq` (flush number in the connection), wall and monotonic timestamps
- `reason`: `silence_hang`, `forced_cap` or `disconnect`
- `audio_received_s` (same audio-seconds clock as the benchmark's expected utterances), `buffer_bytes`, `buffer_samples`, `buffer_s`, `speech_s`, `silence_s`, plus the configured min/max/hang
- `has_pending` (the `has_pending_utterance()` result)
- `decode_attempted`, `decode_s`, `text_empty`, `text_len`, `text_words`
- `final_constructed`, `final_send_called`, `send_s`
- `exception`, `early_return` (`not_pending`, `timeout`, `exception`, `empty_text`, `send_exception`)
- `outcome`: `final_sent`, `dropped_not_pending`, `dropped_timeout`, `dropped_exception`, `dropped_empty_text`, `dropped_send_exception`

Control flow in `flush()` and the main loop is unchanged: same branch order, same returns, same `generation` and `words_sent` updates, same exceptions (the send path re-raises unchanged). The added state (`conn_id`, `flush_seq`, `audio_bytes_received`) is never read by control flow. `flush` gained an optional `reason` argument used only for the log.

Tests: `relays/tests/test_flush_diagnostics.py` runs six scenarios (silence hang, forced cap, short remainder, empty text, engine exception, disconnect flush) with diagnostics off and on, and requires identical outgoing messages and engine calls. Further tests cover the record contents per outcome, no text in the log, nothing written when disabled, and an unwritable log path not breaking a session.

## Tests

| suite | result |
|---|---|
| relays (existing 69 + 13 new) | 82 passed, 1 skipped (the skip was already there) |
| benchmarks `tests/` (new): timestamp matching incl. the six Phase 3 clips, synthetic normal / missing first / missing middle / missing last / duplicate / forced-cap / negative-guard / empty, WER policies, correlation | 34 passed |
| `selftest.py` mock-relay harness after the `ws_bench` change | all PASS |
| `phase4_rescore.py` | reproduces 23.07 / 17.26 / 16.56%; baseline hash unchanged |

## Why do finals disappear? Not yet explained

What is established: the missing finals are the last expected utterance (four of five follow a forced cap; remainders are 2.2-2.6 s of expected audio, well above the 0.3 s minimum); the words are present in the offline full-clip decode of Phase 3; and the instrumented code has exactly five ways to emit nothing (list above).

What is NOT established: which of them happens. The running relay (PID 21800) still executes the old code, so no diagnostic record exists for the Svarah run. The "speech under 0.3 s dropped by `has_pending_utterance()`" path looks unlikely for four of the five clips given the span lengths, but that is an inference from simulated timing, not evidence. Empty decode, timeout and exception are equally unverified.

Further evidence is required: restart the relay with `STT_FLUSH_DIAG_FILE` set and rerun a targeted set (the six clips, a few repeats) at concurrency 1, then `flush_correlate.py`. Both need your approval.

## Recommended next approvals
1. Restart the relay with diagnostics on (no behaviour change, same config) and rerun only the six mismatch clips, repeated (a few minutes of audio). This answers where finals go.
2. Decide on a relay fix only after (1). No VAD or model change is justified by current evidence.
3. Keep numeric output conversion and filler handling deferred.
