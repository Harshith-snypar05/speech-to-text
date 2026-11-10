# ScriptLiv Phase 5: targeted missing-final diagnosis

Diagnostic run only. No fix implemented. Engine, decoding, VAD threshold (0.01), silence hang (0.6 s), min utterance (0.3 s), forced cap (8.0 s), buffering and final emission all unchanged (defaults; no STT_* variable set except `STT_FLUSH_DIAG_FILE`). Concurrency 1. Phase 3 and Phase 4 outputs untouched (`svarah_wer.json` md5 `CCB7FBCF1C434DE7EAABD70BE12EF6C4`, same as before).

## What was done
- Stopped old relay PID 21800 (old code). Started new relay PID 67396 from `relays\`, `STT_FLUSH_DIAG_FILE=benchmarks\results\phase5_flush_diag.jsonl`. Model loaded, listening on 8768.
- Six-clip manifest (subset copy of the Svarah manifest, absolute wav paths): `results/phase5_manifest.json`.
- Three `ws_bench` runs, concurrency 1, warmup 1: `phase5_run1..3.json`.
- `flush_correlate.py` per run (skip-conns 1, 8, 15 for the warmup connections): `phase5_correlation_run1..3.json`.
- Relay stdout/stderr: `phase5_relay_stdout.log`, `phase5_relay_stderr.log`.
- The relay was NOT restored to the old process. The new relay (diagnostics on, same behaviour) is still running.

## Result: all five missing finals are `dropped_empty_text`
The flush was attempted, a pending utterance existed, Parakeet decoded (0.25-0.31 s) and returned an empty string. No timeout, no exception, no unsent final. The result is identical in all 3 runs.

| clip | expected # | relay flush | reason (actual record) | buffer_s | speech_s | decode_s | text_len | outcome |
|---|---|---|---|---|---|---|---|---|
| assamese_03817 | 2 | seq 3 @ 19.7 s | silence_hang | 3.7 | 2.3 | 0.31 | 0 | dropped_empty_text |
| assamese_06152 | 1 | seq 2 @ 10.9 s | silence_hang | 2.9 | 1.9 | 0.25 | 0 | dropped_empty_text |
| kannada_00197 | 1 | seq 2 @ 10.8 s | silence_hang | 2.8 | 1.8 | 0.24 | 0 | dropped_empty_text |
| kashmiri_03111 | 1 | seq 2 @ 11.4 s | silence_hang | 3.4 | 2.1 | 0.29 | 0 | dropped_empty_text |
| bodo_03621 | 6 | seq 7 @ 18.6 s | silence_hang | 2.9 | 0.4 | 0.25 | 0 | dropped_empty_text |

Answers to the five questions, per missing final:
1. Flush never attempted (no pending utterance): NO. `has_pending=true` for all five.
2. Decoded but empty text: YES, all five.
3. Timeout or exception: NO. `exception=null`, no timeout outcome in any of 87 records.
4. Final constructed but not sent: NO. `final_constructed=false`, `final_send_called=false` (the empty-text branch returns before construction).
5. Final sent but unmatched by the benchmark: NO. Nothing was sent.

Silence-hang vs forced-cap, from actual records: the flush that produced nothing was a `silence_hang` flush in all five. Four of the five clips had an earlier `forced_cap` flush (at 8.0 s, and 16.0 s for assamese_03817) which DID produce a final. The remainder after the cap is the part that decodes empty. bodo_03621 has no forced cap: its seventh flush is a normal silence-hang flush with only 0.4 s of speech.

Every other flush with a pending utterance returned text (`final_sent`). The only other drops are the trailing `disconnect` flushes with `dropped_not_pending` (buffer holds only trailing silence, 0.9-1.3 s, speech 0.0 s): expected and harmless.

Warmup connections (conn 1, 8, 15) also show one `dropped_empty_text` each; they are excluded from the clip table.

## Bengali extra final (bengali_01831)
Relay sent 3 finals, simulation expected 2. Record: conn 4 seq 2, `silence_hang` at 8.9 s, buffer 0.9 s, speech 0.3 s (right at the 0.3 s minimum), decode 0.09 s, text length 5, `final_sent`. So the extra final is a real relay flush of a 0.3 s remainder after the forced cap that the simulation judged below the minimum. It is a simulation-versus-relay boundary difference (0.3 s threshold), not a duplicated emission. Same in all 3 runs.

## Evidence quality
- 3 of 3 runs identical in outcomes, reasons, buffer and speech seconds, so the behaviour is deterministic at this config.
- Correlation by `conn_id` order with warmup skipped. Per-clip flush counts match expected flush counts, so the mapping is consistent.
- No transcript text logged (privacy by design); only `text_len` is.

## What is established and what is not
Established: the finals vanish inside `flush()` at the empty-text branch after a successful decode. The relay's own timing, pending check and send path are not the cause.

NOT established: why Parakeet returns an empty string for those buffers. Facts available: buffers hold 1.8-2.3 s of VAD-detected speech (0.4 s for bodo); the same words are present in the Phase 3 offline full-clip decode; decode is fast (not a time budget issue). Unverified hypotheses, none tested here: the engine returns empty for a buffer that begins right after a forced-cap cut (mid-word start, no left context); the decode uses a fresh state so short or context-less buffers fall under a blank-token threshold; for bodo the 0.4 s of speech may be genuine non-speech. Distinguishing these needs a separate read-only experiment (for example, decode the exact buffer slices offline), which is not part of this approval.

## Recommended next approvals (no fix made)
1. Read-only offline replay: cut each of the five dropped buffers from the wav (start = flush audio position minus buffer_s) and decode with the same engine, with and without extra left context. Shows whether emptiness is an engine property of the slice or of relay buffer state.
2. Only after that, choose a narrow fix. Candidates would be about the dropped remainder (not VAD or model), for example logging/emitting instead of silently dropping, or retaining overlap context across a forced cap. Each changes final-emission or buffering behaviour and needs explicit approval.
3. Decide separately whether to leave the diagnostic relay running or restart without `STT_FLUSH_DIAG_FILE`.
