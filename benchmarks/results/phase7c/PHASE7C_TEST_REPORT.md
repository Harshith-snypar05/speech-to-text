# Phase 7C test report

Run in `relays_phase7c/`: `python -m pytest -q` gives 135 passed, 1 skipped (136 collected; 38 s). Baseline copy before changes: 106 passed, 1 skipped. New: 29 tests in `tests/test_phase7c_scheduler.py`. The skipped test is the subprocess-based Parakeet CLI test (binary not present).

The real-model native engine test (`test_parakeet_native_engine_survives_concurrent_partial_and_final_calls`) ran and passed against the actual shared library with the new scheduler: concurrent partial/final calls, no crash, finals correct. It now accepts `None` or a non-empty list for a partial, since a partial may be skipped or dropped as stale.

## Coverage of the required regression areas
| Requirement | Tests |
|---|---|
| Final priority over queued partials | `test_final_runs_before_queued_partials`, `test_running_job_is_not_preempted` |
| Same-speaker final order | `test_same_speaker_finals_keep_order` |
| Partial skipping under backlog | `test_partial_skipped_when_final_waiting`, `..._same_speaker_already_pending`, `test_partial_backlog_is_bounded_by_speakers`, `test_queued_partial_dropped_when_own_final_arrives`, `test_stale_partial_dropped_unrun`, `test_session_skipped_partial_does_not_send_or_crash` |
| Partial executes with no final waiting, no starvation | `test_partial_runs_when_no_final_waiting`, `test_partials_not_starved_without_final_pressure` |
| Expired final before dispatch | `test_expired_final_never_started`, `test_final_with_deadline_already_passed_at_submit`, `test_caller_timeout_while_queued_is_accounted_as_expired`, `test_cancel_before_deadline_while_queued_is_cancelled_before_dispatch`, `test_session_final_expired_in_queue_reports_and_never_decodes` |
| Final timeout after dispatch (job keeps running, worker not reused early) | `test_final_timeout_after_dispatch_job_finishes_and_worker_not_reused_early`, `test_session_final_timeout_while_running_reports_timeout_running` |
| No duplicate final dispatch | `test_no_duplicate_final_dispatch`, `test_each_final_dispatched_exactly_once_under_load` |
| Empty decode unchanged | `test_empty_decode_text_returned_unchanged`, `test_session_empty_decode_unchanged_not_counted_as_scheduling_failure` |
| Engine errors | `test_engine_error_reaches_caller_and_worker_continues` |
| Multiple concurrent speakers | `test_session_multiple_concurrent_speakers_all_finals_delivered` |
| Diagnostics enabled / disabled | `test_scheduler_log_written_when_enabled`, `test_scheduler_writes_nothing_when_log_disabled`, `test_session_diagnostics_disabled_has_no_effect_on_behaviour` |
| No WebSocket message-format regression | `test_session_final_sent_with_scheduled_engine_and_message_format_unchanged` |
| Legacy engines (no scheduler) | `test_legacy_engine_without_scheduling_still_works_with_session` |

## Bugs found and fixed while testing
- Anonymous speakers (`speaker_id=None`) collided in the one-partial-per-speaker dict. Fixed with a unique per-partial key.
- A supervisor test import failed in the copy (`supervisor`, `combined_proxy` missing). Copied in.
- Test helper bug (gating by sample count). Fixed in the test helper only.

## Runtime evidence beyond unit tests (benchmarks)
Across about 1,160 finals in the main matrix and paired rerun: every scheduler job had `dispatch_count == 1`; no duplicate `(conn_id, seq)` in flush diag; scheduler final jobs = `final_sent` + `dropped_empty_text` at every level; 0 relay log errors or tracebacks.

## Not tested
- `timed_out_running` and `expired_in_queue` in a live benchmark: they never occurred (0 timeouts at any level), so these paths are covered by unit and session tests only.
- Real-network WebSocket clients other than `ws_bench.py`.
- Flutter client behaviour when partials are skipped.
