# Phase 7D performance report

Staging relay :8772 (Phase 7C scheduler + QA layer), CPU-only Parakeet, memory-tight Windows 11 machine. Raw: `phase7d_perf_simul.json`, `phase7d_perf_long.json`, `phase7d_sys.jsonl`, `phase7d_sched.jsonl`, `phase7d_flush_diag.jsonl`, `relay.log`, `long.log`.

| Run | Final jobs | Queue wait p50/p95/max (s) | Inference p50/p95 (s) | Final total p95 (s) | Partials run/skipped | Utilisation | Abandoned |
|---|---|---|---|---|---|---|---|
| Simul, 3 accounts x 4 clips | 41 | 0.109 / 0.514 / 0.745 | 0.333 / 0.656 | 1.055 | - / 13 | 0.725 | 0 |
| Long, 3 accounts, 20 min | 801 (781 + 20 empty) | 0.204 / 0.803 / 2.028 | 0.381 / 0.952 | 1.478 | 2502 / 207 (2709 jobs) | 0.891 | 0 |

Partial skip reasons (long, event counts): final_waiting 261, superseded_by_final 198, stale_in_queue 9.

System (long run): system CPU mean 19% (max 96.8%); relay CPU ~372% of one core; relay RSS 746 -> 701 MB (no leak trend); free RAM min **48 MB** (median 769 MB); memory max 99.7%. Simul run: free RAM min 1827 MB, CPU mean 15.5%, relay RSS max 751 MB.
Errors: 0 tracebacks or errors in relay logs. Connection diagnostics: no timeouts, no unexpected closes; 1 intentional abrupt drop in the reconnect run.

## Caveats
- QA overhead (encrypted recording, SQLite writes) was not A/B-measured against QA off; only "no regression seen vs Phase 7C" is supported.
- Paced replay of near-continuous speech is harsher than conversation, but utilisation 0.89 leaves little headroom.
- Free RAM touched 48 MB: on a slower episode this could cause timeouts. Memory pressure is the main risk on this host.
- No network/tunnel latency and no Flutter render time measured.
- No 3-speaker production capacity claim (unchanged from Phase 7C).
