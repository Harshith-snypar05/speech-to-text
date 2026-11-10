# Relay pilot investigation (read-only; no production change; no new relay benchmark)

Evidence sources: pilot JSON `results/existing_audio_relay_pilot.json` (20 clips, concurrency 1), code reading of `relays/` and `ws_bench.py` / `audio_utils.py`, and the offline Pass D replay (`results/parakeet_raw_passes.json`, production `UtteranceBuffer` + same engine, no sockets). Labels: **EVIDENCED** (data supports), **CODE-READ** (follows from source, not runtime-tested), **UNVERIFIED** (hypothesis only).

Measurements to explain: TTFW p95 5.31 s, max 10.30 s; partial revision rate 33%; 110 finals vs 115 expected; rec05 has no pauses >= 0.6 s; rec01 very quiet.

## 1. Finals 110 vs 115 expected
- **EVIDENCED (mechanism):** In the Pass D replay, 6 clips (rec02_0052, rec03_0094, rec05_0004, rec05_0011, rec07_0007, rec07_0026) had one flush whose snapshot passed `has_pending_utterance()` but Parakeet returned **empty text**. In all 20 clips the relay's final count equals the replay's pending flushes minus its empty-text flushes. Relay code sends a final only `if text:` (`speaker_session.flush`), so an empty decode produces no final. These empty flushes are short snapshots (e.g. 0.9 s with 0.3 s speech) or fragments left after a forced cap.
- **EVIDENCED:** relay final text equals the offline decode of the same snapshots (A = D on 20/20 clips). So no finals are lost in WebSocket delivery for the text that exists.
- Caveat: bench "expected" (115) comes from `simulate_flushes`, a mirror of the buffer; the replay used the real buffer and found 116 pending flushes, so expected-vs-pending differs by a small amount in a couple of clips (rec05_0011 expected 5, replay 6). The missing 5 are explained as empty-decode flushes; the mirror's off-by-one is **UNVERIFIED** in cause.
- **CODE-READ:** a 10 s flush timeout also drops an utterance; not observed (pilot errors 0).

## 2. TTFW tail (p95 5.31 s, max 10.30 s)
Split of the 110 per-utterance TTFW values (MEASURED):
| group | n | p50 | p95 | max |
|---|---|---|---|---|
| all | 110 | 1.01 | 5.31 | 10.30 |
| clips with count match | 84 | 0.92 | 3.20 | 6.22 |
| clips with count mismatch | 26 | 1.44 | 9.19 | 10.30 |
| forced-cap utterances | 36 | 1.07 | 8.65 | 10.30 |
| non-forced | 74 | 0.92 | 4.04 | 8.14 |
| forced, matched clips | 24 | 1.10 | 3.79 | 6.22 |
| non-forced, matched clips | 60 | 0.89 | 2.29 | 5.27 |

- **EVIDENCED:** the worst values come disproportionately from count-mismatch clips (p95 9.19 vs 3.20). `ws_bench.analyse_clip` pairs finals with expected utterances **by index**. After a missing final, every later final is matched to the wrong expected utterance, so later TTFW values are shifted (a final that belongs to utterance k is timed against utterance k+1's start, or later). Part of the tail is therefore a **measurement artifact** (CODE-READ + consistent with the table). The size of the artifact is not computed. The top outliers rec03_0094 utt 6 (10.3 s), rec07_0007 utt 4 and 0 (9.46, 8.38) are in mismatch clips.
- In matched clips the max is 6.22 s (rec07_0016 utt 3, forced). Forced-cap utterances are 8 s long, and TTFW for them includes up to 8 s of audio before a final (when no partial arrives), so long TTFW on forced utterances is expected from the 8 s cap itself. Partial timing was not separately split here.
- TTFW is measured against energy-derived starts (`simulate_flushes`), the same rule the relay uses: circular for VAD, valid for relative latency.

## 3. Energy VAD segmentation (rec05, rec01)
- **EVIDENCED:** rec05 has no natural pauses >= 0.6 s (inventory); 8 of its 10 expected utterances in the pilot are forced 8 s cap flushes (simulate_flushes). Cap flushes cut mid-speech, which gives mid-sentence snapshots and fragments (Section 1, rec05_0011 and rec05_0004 each had an empty tail flush).
- rec05 noise floor is above the fixed 0.01 threshold (inventory), so silence is never detected there. Cause of the high floor (noise type): **UNVERIFIED**.
- rec01: only 21% of frames >= 0.01 (inventory). Clips p95 RMS about 0.03. Under-trigger of the energy VAD is **plausible but not measured**: no speech labels, so missed speech cannot be quantified. Two rec01 clips are `AUDIO_UNCLEAR` by the report heuristic only on low level plus disagreement.

## 4. Inference queueing and re-decoding
- **CODE-READ:** `partial_cycle` decodes the whole growing buffer every 0.5 s via `transcribe_partial`, which is the same decode as the final. The engine has one executor and a `_call_lock`, so a final decode can wait behind an in-flight partial decode. A growing 8 s buffer takes about 0.75 s to decode (RTF about 0.093); so a final may queue about 0.7 s at most behind one partial. Not measured at runtime. Queue wait was not instrumented.
- `flush()` is awaited inside the receive loop, so audio ingest pauses during a final. At concurrency 1 and RTF 0.09, the effect is bounded (**UNVERIFIED** for concurrency > 1; not tested).
- Re-decoding: each partial decodes the full buffer again, so work per utterance grows with length (quadratic in the number of partial cycles). Relay CPU mean 162% (max 404%) is consistent with this but not proof.
- Finalization latency p50 0.93 s, p95 3.21 s, max 9.74 s; after-hang p95 2.61 s (MEASURED). The 3.2 s p95 is about 4 times an 8 s buffer decode, so queueing and index-shift artifacts both plausible. Which dominates: **UNVERIFIED**.

## 5. Partial revisions (33%)
- Revision = partial word differs from the final word at the same index. Because the relay emits only `words[words_sent:]` and never retracts, early partial words on a short buffer that the later longer-context decode changes are counted. **EVIDENCED by definition** (code and metric), not a measure of recognition accuracy.
- By recording: 0.22 (rec07) to 0.48 (rec06, rec01). rec06 also has the lowest Parakeet consistency (Section 3 of the consistency report), so unstable recognition and revised partials co-occur there. Direction of causation: **UNVERIFIED**.
- Index shifts (an inserted/dropped word early on) make all later words count as revised, inflating the rate. Not separated; partial texts were not stored, so a word-level re-analysis is impossible without a new run.

## 6. WebSocket delivery
- **EVIDENCED (indirectly):** finals delivered equal replay non-empty flushes (Section 1). No delivery loss evidenced. Partial message loss: `partial_cycle` drops stale partials by generation counter (**CODE-READ**), intentionally; partials dropped this way were not counted. Tunnel/network latency was excluded (localhost).

## 7. Clip boundary effects
- Pilot clips are 24-42 s cuts at energy pauses, not word aligned. The replay shows clips can end mid-sentence (rec05_0011 ends with "Cause English is becoming"; the final fragment decoded empty). First/last-word loss from clip edges: **EVIDENCED in 1 clip**, rate unknown.
- Replay adds 1.5 s zeros after each clip (as `ws_bench` does) so the last utterance flushes by silence; a clip that ends in speech then flushes the remainder as a short snapshot (Section 1).

## 8. Benchmark methodology issues
1. Index pairing of finals to expected utterances (Section 2): shifts latencies after any count mismatch.
2. Expected boundaries come from a mirror of the VAD; TTFW, finalization and forced-flush counts are circular for VAD correctness.
3. One run, concurrency 1, one machine, one speaker mix; no repeat to estimate run-to-run variance (the relay pilot was one pass).
4. `ws_bench` stores no partial texts or per-message timestamps, which blocks partial-vs-final and queueing analysis after the fact.
5. Latency excludes mic, UI, tunnel.

## 9. Summary
| finding | status |
|---|---|
| Missing 5 finals come from empty-text decodes (no final sent when text is empty) | EVIDENCED by replay |
| Part of TTFW tail is an index-pairing artifact in mismatch clips | EVIDENCED (grouping) + CODE-READ; magnitude not computed |
| Forced 8 s cap explains long forced-utterance TTFW | EVIDENCED partly (matched clips: p95 3.79 vs 2.29) |
| rec05 flushes mostly by cap because no silence is detected | EVIDENCED (inventory + simulate_flushes) |
| rec01 under-trigger | UNVERIFIED |
| Finals queue behind partials | CODE-READ; not measured |
| WebSocket loss | not evidenced |
| 33% revision rate reflects accuracy | NOT SUPPORTED (it is a stability metric) |

## 10. Cheapest ways to verify (need approval; none run)
1. Fix the index pairing in a **copy** of the analysis and recompute TTFW (offline, from the existing JSON; no relay run).
2. Instrument a benchmark-side client to store partial texts and timestamps; one 20-clip rerun (about 11 min).
3. Time-stamped relay-side queue wait would need a production logging change: needs approval.
