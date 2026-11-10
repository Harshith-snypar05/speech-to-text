# ScriptLiv Phase 7 — Regression Test Report

Engine unchanged: **NVIDIA Parakeet TDT 0.6B v3 q8_0** via the existing whisper.cpp fork
(`ParakeetNativeEngine`, ctypes). No relay, VAD, buffering, model-config, scheduling or
UI production file was modified to create or pass these tests. New outputs live only in
`benchmarks/results/phase7/`.

## 1. Results

| suite | command | before Phase 7 | after Phase 7 | delta |
|---|---|---|---|---|
| relays | `cd speech-to-text/relays && python -m pytest -q` | 82 passed, 1 skipped | **106 passed, 1 skipped** | +24 new |
| benchmarks | `cd speech-to-text/benchmarks && python -m pytest tests -q` | 34 passed | **34 passed** | none (untouched) |

- The 1 skip is pre-existing and unrelated: `test_engines.py::test_parakeet_engine_real_transcription`
  (the subprocess `parakeet-cli` fallback binary is not built on this machine).
- The full relays suite was run **twice** back to back: `106 passed, 1 skipped` both times,
  no flakes (an earlier flake in one of my own tests was found and fixed — see §4.1).
- Historical artifacts re-verified unchanged: `svarah_wer.json` md5 `ccb7fbcf1c434de7eaabd70be12ef6c4`,
  `svarah_phase4_rescore.json` md5 `455eb7788707b52778c864fab7dd784e`,
  `phase5_flush_diag.jsonl` md5 `cc78e3cd1f5494bd7fb2e07affe147f7` (87 lines, still owned by the Phase 5 relay).

## 2. Required-case coverage

Mocks (FakeEngine / FakeWebSocket) are used **only** for plumbing tests. Every ASR-side
regression runs the real model against real audio.

| # | Required case | Test | Audio / model | Status |
|---|---|---|---|---|
| 1 | Empty Parakeet decode | `test_phase7_asr.py::test_empty_decode_without_context_is_still_empty[5 cases]` | real model + the 5 Phase 6 `*_dropped_A.wav` buffers | pass (all 5 decode to `""`) |
| 2 | Empty decode with pending utterance | `test_phase7_asr.py::test_empty_decode_with_pending_utterance_sends_no_final[5 cases]` | real model, streamed into a real session loop | pass — decode attempted, **no final sent**, `dropped_empty_text` recorded |
| 2b | Empty decode with pending session recovers | `test_phase7_regressions.py::test_empty_decode_with_pending_utterance_drops_final_but_session_recovers` | FakeEngine | pass — next utterance still transcribed, no crash |
| 3 | Normal non-empty final | `test_phase7_asr.py::test_normal_non_empty_final_direct` / `..._through_session` | real model + `whisper.cpp/samples/jfk.wav` | pass — non-empty, JFK content present, every decode yields exactly one final |
| 3b | Normal non-empty final (plumbing) | `test_phase7_regressions.py::test_normal_non_empty_final_is_sent_exactly_once` | FakeEngine | pass |
| 4 | Silence-hang flush | `test_phase7_regressions.py::test_silence_hang_flush_reports_reason_silence_hang` | FakeEngine + diagnostics | pass — `reason=silence_hang`, `outcome=final_sent` |
| 5 | Forced-cap flush | `test_phase7_regressions.py::test_forced_cap_flush_reports_reason_forced_cap` | FakeEngine + diagnostics | pass — `reason=forced_cap`; also exercised for real in the ASR empty-decode tests |
| 6 | Trailing disconnect flush | `test_phase7_regressions.py::test_trailing_disconnect_flush_after_a_clean_end_is_not_pending` | FakeEngine + diagnostics | pass — trailing silence alone → `dropped_not_pending`, no decode, one final total |
| 7 | Previous-context overlap | `test_phase7_regressions.py::test_consecutive_utterances_do_not_share_audio` | FakeEngine + marker-valued PCM | pass — **asserts the overlap does NOT exist yet** (guard for a future approved change) |
| 8 | Duplicate-word prevention | `test_phase7_regressions.py::test_consecutive_finals_do_not_duplicate_or_merge_words` | FakeEngine | pass — 3 utterances → 3 independent, in-order finals, no cross-absorption |
| 9 | Partial-to-final reconciliation | `test_phase7_regressions.py::test_partial_accumulator_resets_across_a_final` | FakeEngine (partials) | pass — post-final partial restarts from empty; finalized words never leak back |
| 10 | Consecutive utterance ordering | `test_phase7_regressions.py::test_consecutive_utterance_finals_keep_wire_order` | FakeEngine + diagnostics | pass — wire order == utterance order == diagnostics `seq` 1,2,3 |
| 11 | Multiple concurrent speakers | `test_phase7_regressions.py::test_two_concurrent_speakers_get_only_their_own_finals` | FakeEngine, one shared engine + registry | pass — each socket receives only its own finals, no cross-talk |
| 12 | Diagnostics enabled vs disabled | `test_phase7_regressions.py::test_diagnostics_on_off_identical_with_partials` (partials path) and pre-existing `test_flush_diagnostics.py` (finals path) | FakeEngine | pass — identical wire messages and engine calls with `STT_FLUSH_DIAG_FILE` on/off |

Additional real-model concurrency coverage already existed and still passes:
`test_engines.py::test_parakeet_native_engine_survives_concurrent_partial_and_final_calls`
(concurrent partial+final against one loaded model).

## 3. What the real-model tests proved (measured, not assumed)

1. **All five Phase 5 missing-final buffers still decode to empty text with no left context**
   (`assamese_03817`, `assamese_06152`, `kannada_00197`, `kashmiri_03111`, `bodo_03621`), 2.8–3.7 s each.
   Phase 6's reproduction is therefore still valid on today's build.
2. **The relay drops them without sending a final** — `outcome=dropped_empty_text`,
   `decode_attempted=true`, `final_constructed=false`, `final_send_called=false`, while the
   connection is still open. The Phase 5 defect is present and unchanged; it is now pinned.
3. **Sub-buffers of those same slices are NOT empty.** Cutting a slice at one of its internal
   pauses makes Parakeet return real words (measured: e.g. a 1.3 s sub-buffer → 5-character
   final, a 2.1 s sub-buffer → 26-character final, while the full 3.7 s buffer → `""`).
   So emptiness is a property of *this exact segmentation*, not of the clip — consistent with
   Phase 6's "left context changes the result for 4 of 5" finding.
4. **Normal speech loses nothing end to end.** JFK (11 s) through a real session: every decode
   produced exactly one non-empty final, `final_calls == final_sent` records, buffer empty at
   disconnect (`dropped_not_pending`).
5. **Decode timing on this CPU-only build**: 1.3 s audio → 0.117 s, 2.1 s → 0.182 s,
   2.2 s → 0.191 s, 6.2 s → 0.965 s (RTF ≈ 0.13–0.16; see `phase7_results.json`/diag for the corpus-wide figure).

## 4. Test-infrastructure findings (these are findings, not code defects)

### 4.1 Flaky parity test — `engine.partial_calls` length is timing-dependent
The first version of `test_diagnostics_on_off_identical_with_partials` compared the engine's
raw partial-call list between the diagnostics-on and -off runs. The number of 50 ms partial
cycles that fire during an utterance varies run to run (2 vs 3), so the lists differ even
though the **wire output is deterministic** (the relay sends each new partial word once).
Fixed by comparing wire messages + final calls exactly and only requiring `partial_calls > 0`.
*Takeaway: partial-call counts are wall-clock dependent and must never be asserted exactly.*

### 4.2 A final flushed after the client disconnects can never be delivered
`flush()` awaits `send()`, but once the remote is gone `send()` raises `ConnectionClosed`,
which the disconnect path logs and swallows. Measured directly: JFK in a real session
decoded 3 utterances, but the 3rd was flushed *after* the harness called `disconnect()`, so
only 2 finals reached the wire — `final_calls (3) != finals (2)`. Any test that asserts
"every decode yields a final" must stream a silence tail so the last utterance flushes
while the socket is still open (which is what a real client does).
*Production relevance: low — a peer that has closed the TCP connection cannot receive the
text anyway. Documented rather than changed.*

### 4.3 `asyncio.Lock` binds to the event loop that first contends on it
`ParakeetNativeEngine` creates one `asyncio.Lock` at construction. `asyncio.Lock` only
touches the loop when an acquire actually has to wait, so the binding happened sporadically —
seen as `dropped_exception: "Lock ... is bound to a different event loop"` in 2 of 5 ASR
session tests, i.e. exactly the tests where a partial cycle and a flush overlapped.
**This cannot happen in production** (one relay process, one event loop for its whole life).
The fix is test-side: each test gets a fresh unbound lock while the 668 MB model is still
loaded once per module (`test_phase7_asr.py::engine` fixture, documented in place).

### 4.4 Buffering config changes which audio the model sees
The first attempt at the empty-decode session test used the standard test buffer
(hang 0.3 s) and the slice was split at its internal pauses; the sub-buffers decoded to
non-empty text and real finals were sent — the defect disappeared from view. The passing
test therefore pins `silence_hang=30` + `max_utterance=len(pcm)` so the model receives the
**exact bytes** the direct test decodes. Any future empty-decode test must control
segmentation or it will silently test the wrong thing.

## 5. Limits of this report

- Mock-based tests prove orchestration, not recognition quality; recognition quality is
  covered only for JFK and the 5 empty-decode slices (§3) and, corpus-wide, by
  `phase7_results.json` (separate document).
- The 5 fixtures are used purely as English-speech regression buffers. No native-language
  investigation was performed, per scope.
- No test asserts a *fix* for the empty-decode defect: every assertion here pins current
  behaviour so that an approved change flips them visibly.
