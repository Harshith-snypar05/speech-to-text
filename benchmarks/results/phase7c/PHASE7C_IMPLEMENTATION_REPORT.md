# Phase 7C implementation report: inference scheduling and finalization reliability

Engine: Parakeet TDT 0.6B v3 q8_0 only. Model and decoder parameters, audio format, WebSocket protocol, VAD, utterance segmentation and empty-decode handling are unchanged. No retry of empty decodes. Nothing was merged or deployed; production relays (PID 67396 :8768, PID 40624 :8769) and `relays/` were not touched.

Work is in the isolated copy `relays_phase7c/` (own git repo). Commits: `874b131` (verbatim copy of `relays/`, pre-change), `387525e` (Phase 7C). Tested relay ran from that copy on :8771 (port override only, `benchmarks/results/phase7c/start_phase7c_relay.py`).

## Design (`core/scheduler.py`, new)
The engine's FIFO `asyncio.Lock` is replaced by `InferenceScheduler`. All native calls still run on the one dedicated executor thread (same thread affinity as before). The scheduler only chooses which waiting request runs next.

1. Final priority. Finals sit in a global FIFO deque and are always dispatched before any waiting partial. FIFO among finals preserves same-speaker final order. A running job is never preempted.
2. Partial backpressure. A partial is skipped (the engine returns `None`; nothing is queued) when the same speaker already has a partial queued or running (`same_speaker_pending`) or when any final is waiting (`final_waiting`). At most one queued partial per speaker, so the backlog is bounded by the speaker count. A queued partial is dropped when its speaker's final arrives (`superseded_by_final`) or when it has waited longer than `STT_PARTIAL_MAX_QUEUE_AGE_SECONDS` (default 2.0, `stale_in_queue`). With no final pressure partials run in arrival order, so they are not starved. Counters: requested, executed, skipped, skip reasons.
3. Final deadline. `speaker_session` passes `deadline = t_decode + FINAL_FLUSH_TIMEOUT_SECONDS` (10 s, from the flush request). Remaining time is checked at submit and again at dispatch; an expired final is never started and raises `FinalExpired`. The `asyncio.wait_for` 10 s timeout is kept. Cancelling the await only detaches the caller. The dispatcher awaits the executor future itself, so an abandoned job still occupies the worker until it returns and is marked `abandoned`. No thread is terminated.
4. Dropped-final accounting. `JobTicket` states: `queued`, `running`, `completed`, `failed`, `expired_in_queue`, `cancelled_before_dispatch`, `timed_out_running`, `cancelled_running`, `skipped`. Cancellation is classified with a 5 ms tolerance against the deadline. Flush-diag outcomes added: `dropped_expired_in_queue`, `dropped_cancelled_before_dispatch`, `dropped_timeout_running`, `dropped_cancelled` (plain `dropped_timeout` kept for engines without a scheduler). Records carry `sched_state`, `queue_wait_s`, `infer_s`, `sched_abandoned`. `dropped_empty_text` is untouched and separate from scheduling failures.
5. Double dispatch guard. Reusing a `JobTicket` raises `ValueError`; the dispatcher asserts `dispatch_count == 1`.
6. Diagnostics. Optional raw JSONL (`STT_SCHED_LOG_FILE`): `kind: job` (type, speaker, state, t_enq/t_start/t_end, queue_wait_s, infer_s, queue depth, abandoned) and `kind: skip`. Logging failures never affect scheduling. With it disabled behaviour is identical.

`speaker_id=None` means anonymous (no dedupe or supersede). The scheduler rebinds when the event loop changes (per-test loops). Engines without `supports_scheduling` (base default False) use the old path.

## Protocol and behaviour preserved
Partial response format and final transcript text are unchanged. A skipped partial sends nothing (same as no partial that cycle). Tests assert message format unchanged.

## Modified files (commit `387525e` vs `874b131`)
- `core/scheduler.py` new (319 lines)
- `core/config.py` (+`PARTIAL_MAX_QUEUE_AGE_SECONDS`, `SCHED_LOG_FILE`)
- `core/flush_diagnostics.py` (+4 outcomes)
- `core/speaker_session.py` (deadline/ticket, outcome mapping, skip handling)
- `engines/base_engine.py` (`supports_scheduling`)
- `engines/parakeet_native_engine.py` (lock replaced by scheduler)
- `tests/test_phase7c_scheduler.py` new (29 tests)
- `tests/test_engines.py`, `tests/test_phase7_asr.py` (adapted to new kwargs and skip semantics)
- `supervisor.py`, `combined_proxy.py` copied in so the copy's supervisor tests import (unchanged content)

`relays/` verified equal to the baseline commit apart from CRLF line endings (git autocrlf in the copy).

## Known behaviour notes
- `same_speaker_pending` never fired in the benchmarks because each speaker's partial loop awaits its previous partial. The rule is still enforced and tested.
- Partials are dropped, not delayed, under load. Under heavy load the UI shows older partial text.
- Not changed, per constraints: the partial cycle length (0.5 s) and the partial decode of the whole growing buffer.
