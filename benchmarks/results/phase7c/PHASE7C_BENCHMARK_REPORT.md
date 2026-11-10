# Phase 7C benchmark report

Same manifests, `benchmarks/ws_bench.py`, 1 warmup, as Phase 7B. Phase 7C relay: isolated copy on :8771 (CPU-only build). Machine: Windows 11, memory-tight (free RAM often 100-1,000 MB), no power-plan, affinity or priority changes. Warmup session excluded from all numbers. Monitoring: system CPU, relay CPU, free memory, relay RSS, queue depth, queue wait, inference duration, worker utilisation (`phase7c_sys.jsonl`, `phase7c_sched_*.jsonl`).

## Two things to know before reading the numbers
1. **Correction to the 7B baseline.** 7B split its 12-clip N=1/N=2 file at the largest idle gap, which put the level boundary in the wrong place. Re-cut by final counts: baseline N=1 queue p50/p95 0.0001/0.51 s (util 0.42); baseline N=2 queue p50/p95 **0.35/1.21 s** (7B reported 0.24/0.97), util **0.75** (7B reported 0.62). The N=3, N=4 and full-60 baseline figures were not affected.
2. **The machine speed drifted a lot between runs.** Final inference RTF p50: 7B baseline 0.12 (N=1,2), main 7C matrix 0.12 at N=1 then 0.17-0.19 at N>=2, and 0.083-0.085 in the later reruns. In the 7B N=4 run abandoned jobs ran at RTF about 1 with free RAM near 240 MB. A comparison of 7C against the 7B numbers is therefore confounded. To control for it I re-ran the **unmodified baseline** (7B instrumented launcher on `relays/`, :8770, own PID) and the 7C relay back-to-back in the same conditions (rerun, below).

## Result A: main matrix, 7C vs 7B baseline (different times)
Final queue wait (s), final total (queue+inference) p95, timeouts/drops.

| Run | Baseline queue p50/p95 | 7C queue p50/p95 | Baseline total p95 | 7C total p95 | Baseline drops | 7C drops |
|---|---|---|---|---|---|---|
| 12 clips N=1 | 0.00/0.51 | 0.00/0.58 | 1.50 | 1.46 | 0 | 0 |
| 12 clips N=2 | 0.35/1.21 | 0.20/1.15 | 1.91 | 2.18 | 0 | 0 |
| 12 clips N=3 | 1.25/3.26 | 0.47/1.64 | 4.67 | 2.74 | 0 | 0 |
| 12 clips N=4 | 1.22/7.19 | 0.67/2.34 | 9.21 | 3.22 | 63 of 158 (31 never started, 32 abandoned while running) | 0 of 160 |
| 60 clips N=2 | 0.33/1.70 | 0.17/1.25 | 2.90 | 2.47 | 0 | 0 |

7C worker utilisation: 0.42, 0.79, 0.97, 0.99, 0.74. Baseline: 0.42, 0.75, 0.97, 0.99, 0.78. At N=4 baseline lost 145.8 s of 314 s busy time to abandoned jobs; 7C had 0 abandoned jobs. The 7C N=2 total p95 is higher than baseline (2.18 vs 1.91) despite lower queue wait because inference was slower during that run (RTF 0.17 vs 0.12, see point 2 above), not because of queueing.

## Result B: paired rerun in the same conditions (12 clips)
Unmodified baseline vs 7C relay, run back-to-back (machine faster, RTF about 0.085).

| Run | Baseline queue p50/p95 | 7C queue p50/p95 | Baseline total p95 | 7C total p95 | Baseline util | 7C util | Drops (both) |
|---|---|---|---|---|---|---|---|
| N=2 | 0.10/0.54 | 0.06/0.65 | 1.10 | 1.31 | 0.60 | 0.60 | 0 / 0 |
| N=3 | 0.42/1.32 | 0.13/0.56 | 1.96 | 1.17 | 0.85 | 0.80 | 0 / 0 |
| N=4 | 0.67/1.55 | 0.13/0.68 | 2.09 | 1.27 | 0.96 | 0.91 | 0 / 0 |

Reading: in a fast machine state the **unmodified relay also had zero timeouts at N=3 and N=4**. The 7B N=4 failure (63 drops) therefore needed the slow, memory-pressured machine state; N=4 is not inherently a failure. What the scheduler changes: at N>=3 final queue wait and total latency are 2-3 times lower in both machine states, and the main-matrix N=4 run (slow state, RTF about 0.19) delivered all 160 finals where the 7B baseline lost 40%. It is the same direction in both states, but the proof that the scheduler prevents timeouts in a degraded state rests on one 7C N=4 run in the slow state compared with the 7B N=4 baseline from a different, slower state. I did not reproduce a slow state on demand, so a same-state paired slow-condition comparison is missing. At N=2 there is no measurable difference (7C 0.65 vs 0.54 s p95 is within run-to-run noise at 78-80 finals).

## Partials: requested / executed / skipped (7C, main matrix)
| Run | Requested | Executed | Skipped | Skip reasons (final_waiting / superseded_by_final / stale_in_queue) | Partial age p50/p95 (s) | Interval between a speaker's partials p50/p95 (s) |
|---|---|---|---|---|---|---|
| N=1 | 181 | 181 | 0 | - | 0.29/0.77 | 0.89/1.38 |
| N=2 | 278 | 247 | 31 (11%) | 13 / 16 / 2 | 0.51/1.40 | 1.16/2.67 |
| N=3 | 304 | 192 | 112 (37%) | 55 / 49 / 8 | 0.97/2.07 | 1.70/3.97 |
| N=4 | 390 | 139 | 251 (64%) | 148 / 82 / 21 | 1.19/2.37 | 2.26/4.16 |
| 60 clips N=2 | 1,532 | 1,419 | 113 (7%) | 48 / 57 / 8 | 0.38/1.36 | 1.01/2.55 |

Partial freshness (bench client): first-partial p50 7C vs baseline: N=1 0.85 vs 0.89 s; N=2 1.23 vs 1.06; N=3 1.87 vs 1.98; N=4 2.27 vs 1.91 (baseline N=4 was collapsing); 60 clips N=2 1.08 vs 1.19. Partials received by the client: N=2 177 vs 208, N=3 146 vs 147, 60 clips N=2 1,041 vs 963. In the paired rerun N=4: 385 partials, first-partial p50 1.19 s vs baseline 351 partials and 1.56 s. Partial revision rate unchanged within noise (0.34 vs 0.32 on 60 clips). Verdict: acceptable at N<=2 (a speaker still gets a fresh partial about every 1-1.2 s); at N>=3 partials get visibly sparser (every 1.7-2.3 s), by design, since finals come first. `same_speaker_pending` never fired because each speaker's loop already awaits its previous partial.

## Accuracy, duplicates, missing finals
- WER (svarah, raw): 12-clip N=1 31.38% (baseline 31.38%); N=2 31.38% (31.38%); N=3 31.38% (baseline 32.99%); N=4 33.19% (baseline 56.21%, because 63 finals were dropped). Rerun N=2/3/4: 31.38% in all (identical hypotheses).
- Full 60 clips N=2: **23.28% [19.3-27.4] vs baseline 23.07%**. 59 of 60 clips have identical hypotheses. The one difference is a single session of one clip (`..._f53_chunk...`, 7 more word errors, +0.2 point) where the client received 2 finals instead of 3. The relay did send that final (relay `final_sent` 394 vs client 393). The client harness stops reading once it has the expected final count (2), and the VAD split that clip into an extra short "Yeah." utterance, so the third final arrived after the client stopped. It is client-side timing of an unchanged VAD, not a scheduler drop. Within normal run-to-run variation; not a regression I can attribute to scheduling.
- Duplicates: 0 duplicate `(conn_id, seq)` in any flush diag; every scheduler job `dispatch_count == 1`.
- Missing finals: at every level scheduler final jobs = `final_sent` + `dropped_empty_text` (N=1 40=39+1, N=2 80=78+2, N=3 120=117+3, N=4 160=156+4, 60 clips 404=394+10). Differences between relay-sent and client-received (N=4: 156 vs 153; 60 clips: 394 vs 393) come from clips whose VAD split differs from the harness's expected count (same clips in baseline); none are scheduling drops.
- Dropped-final accounting, all runs: `expired_in_queue` 0, `cancelled_before_dispatch` 0, `timed_out_running` 0, completed and sent 100% of non-empty decodes, empty Parakeet decode 1/2/3/4/10 (about 2.5%, comparable across levels, unchanged handling and counted separately).

## Environment monitoring (main matrix)
| Run | Sys CPU mean/max % | Relay CPU mean (% of one core) | Free RAM min/median MB | Relay RSS max MB | Queue depth at enqueue mean/max |
|---|---|---|---|---|---|
| N=1 | 12/32 | 195 | 290/543 | 744 | 0/0 |
| N=2 | 17/34 | 317 | 1,495/1,912 | 744 | 0.09/2 |
| N=3 | 19/47 | 374 | 345/1,756 | 747 | 0.59/2 |
| N=4 | 26/74 | 381 | 348/809 | 741 | 1.32/4 |
| 60 clips N=2 | 20/52 | 315 | 104/586 | 730 | 0.07/2 |

CPU clock median 2.4 GHz throughout. Free memory dropped to 104 MB during the long run and system memory use peaked at 99%. The slower inference seen in the main matrix at N>=2 coincides with high memory pressure but I did not isolate the cause.

## Targets
| Target | Result |
|---|---|
| Zero final timeouts at N=2 | PASS (0 in 12-clip, 60-clip, rerun) |
| Zero at N=3 (experimental) | PASS (0 in main matrix and rerun) |
| N=2 final queue p95 < 1.5 s | PASS (1.15 s 12-clip, 1.25 s 60-clip, 0.65 s rerun) |
| No WER regression vs same-manifest baseline | PASS on 12-clip levels; 60-clip +0.21 point from one client-side missed final (see above) |
| No duplicate finals | PASS |
| No unexplained missing finals | PASS |
| Acceptable partial freshness | PASS at N<=2; degraded by design at N>=3 |

## What this does not show
- **Not a three-speaker production capacity claim.** At N=3 the worker is at 0.80-0.97 utilisation with no headroom, partials are 37% skipped, and the baseline itself also passed N=3/N=4 timeout targets when the machine was in a fast state. Passing the timeout target at N=3 reflects the test machine state and workload (12 clips, sessions started together); it is not evidence of headroom under slow-machine episodes, staggered traffic or longer utterances.
- No same-state paired comparison in a slow/degraded machine condition.
- CPU-only build; GPU not used.
- Unexplained: why inference RTF varied 0.083-0.19 across runs.

## Files
`phase7c_comparison.json` (baseline vs new, all levels, plus bench, partial stats, env and drift sections), `phase7c_bench_compare.json`, `phase7c_partial_stats.json`, `phase7c_env_summary.json`, `phase7c_sched_<level>.jsonl` and `phase7c_flush_diag_<level>.jsonl` (raw queue/inference logs), `phase7c_sys.jsonl` / `phase7c_ab_sys.jsonl` / `phase7c_drift_sys.jsonl` (CPU/memory), `phase7c_bench_*.json`, `phase7c_drift*`, `phase7c_ab_*` (paired rerun), `analyze_phase7c.py`, `bench_compare.py`, `run_matrix.sh`, `run_drift_baseline.sh`, `run_ab.sh`.
