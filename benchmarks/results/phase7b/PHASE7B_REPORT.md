# ScriptLiv Phase 7B: concurrency investigation (read-only)

Engine: Parakeet TDT 0.6B v3 q8_0 only. No change to relay, scheduling, VAD, model or empty-decode handling. Measurement used `instrumented_relay.py`, which imports the unmodified relay module and wraps only the two engine entry points with timestamps. It runs the same lock, single-thread executor, partial cycle and 10 s `wait_for` as production. It ran on its own port 8770 (now stopped, PID 58620). Relays 67396 (:8768) and 40624 (:8769) were not touched. `svarah_wer.json` md5 `CCB7FBCF1C434DE7EAABD70BE12EF6C4` unchanged. `phase5_flush_diag.jsonl` still 87 lines. Phase 6, 6C and Phase 7 artifacts intact.

Runs (CPU-only build, RTX 5050 unused):
- 12-clip subset, N=1 and N=2.
- Full 60 clips, N=2 (matches Phase 7 load).
- 12-clip subset, N=3 and N=4.

Files: `phase7b_calls*.jsonl`, `phase7b_analysis*.json`, `phase7b_bench_*.json`, `phase7b_sys_*.jsonl`, `phase7b_flush_diag.jsonl`.

## Architecture facts (from source)
- One engine, one worker thread, one FIFO `asyncio.Lock`. Every partial and final from every speaker is serialized.
- Each speaker issues a partial every 0.5 s over the whole growing buffer. A final is queued behind whatever is already waiting. No priority.
- Final flush has `wait_for(..., 10 s)`. The timeout clock includes queue wait plus inference.
- Cancelling the await does NOT stop an executor job already running.

## Q1. Queue wait vs inference time

| level | final queue p50 / p95 / max (s) | final inference p50 / p95 (s) | worker utilisation |
|---|---|---|---|
| N=1 (12 clips) | 0.00 / 0.50 / 0.50 | RTF 0.12 | 0.41 |
| N=2 (12 clips) | 0.24 / 0.97 / 1.46 | RTF 0.12 | 0.62 |
| N=2 (60 clips) | 0.33 / 1.70 / 3.26 | RTF p50 0.128, p95 0.199 | 0.80 |
| N=3 | 1.25 / 3.26 / 4.41 | 0.61 / 1.51 s | 0.97 |
| N=4 | 1.22 / 7.19 / 7.95 | 0.47 / 3.17 s (non-cancelled) | 0.99 |

Up to N=2, inference speed does not change; the added latency is pure queueing. From N=3 the worker is saturated (97-99%). Queue wait then grows with backlog, and at N=4 it dominates: partial queue wait p95 9.5 s, max 14.4 s.

## Q2. Partials competing with finals
- Partials take 72-73% of worker time at N=1/N=2 (12 clips), 68% at N=2 (60 clips), 58% at N=3.
- At N=2 (60 clips), 288 of 386 finals waited behind a partial, about 0.5 s on average.
- Yes: partials are the main consumer of worker capacity and finals queue behind them.
- At N=4 the partial share drops to 28%, because abandoned final jobs take the worker (see Q6).

## Q3. Can finals get priority?
Yes, technically. The FIFO lock is the only ordering. A priority queue (finals ahead of waiting partials) would remove the partial-induced part of the final wait (about 0.5 s mean at N=2). A partial already running could not be preempted, because the executor job cannot be stopped. Not tested; this is a proposal.

## Q4. Can partial frequency be reduced safely?
Partials re-decode the whole growing buffer every 0.5 s, so their cost grows with utterance length and they hold 58-73% of worker time. Candidates: a longer cycle, or skip a partial while a decode is pending or backlog exists. Not tested. Safety needs a UI/latency check (partial staleness) that was out of scope. No quality risk to finals is expected, since finals are decoded independently, but that is not measured.

## Q5. Concurrent speaker capacity (measured)
- N=1 and N=2: no timeouts, no cancellations, final total max 4.8 s (N=2, 60 clips). Utilisation 0.41 and 0.62 to 0.80.
- N=3 (12 clips): no timeouts, no cancellations, but utilisation 0.97, final total max 5.9 s and p95 4.7 s. At the edge: no headroom.
- N=4: 63 of 158 finals cancelled (40%). Fails.
- Measured working capacity on this CPU-only build: 2 speakers with margin; 3 marginal; 4 fails. This replaces the earlier "about 2" extrapolation. The workload is the 12-clip subset with sessions started together, so real staggered traffic may differ.
- The "about 7 speakers without partials" estimate is still untested and not supported by a measurement.

## Q6. Why finals exceed 10 s
Reproduced at N=4: 63 final timeouts (`dropped_timeout` 63 in the 7B flush diag, all at N=4).

Mechanism, measured:
1. Worker saturates (utilisation 0.99). Final waits in the lock queue; mean cancelled-final audio 4.7 s.
2. Of the 63 cancelled finals, 31 never reached the worker (cancelled while waiting; queue wait p50 of the ones that did start was 8.8 s).
3. 32 had already been dispatched to the executor. Their jobs kept running after the timeout. Those abandoned jobs consumed 145.8 s of the 314.1 s of N=4 busy time (46%). Their results are discarded. Confirmed hypothesis from earlier phases.
4. Abandoned jobs delay later calls, which then also time out: a feedback loop.
5. Dropped finals are lost text, with no retry and no marker.

Inference was also slower for the abandoned jobs (p50 5.0 s for about 4.7 s audio, RTF about 1) while sys memory dipped to 241 MB available. The machine's CPU averaged 34.5% (max 89.5%) and median clock was 2.4 GHz. This points at co-running load or memory pressure, but the cause is not isolated.

## Reconciling the earlier figures
The figures in the decision note ("decode p50 0.433 to 6.478 s, RTF 0.104 to 2.196, 21 timeouts in the partial run") do not match the complete Phase 7 data (60 clips, N=2): completed-decode p50 1.164 s, RTF 0.216, 73 timeouts of 404 decodes. The 6.478 s / 2.196 / 21 values are not reproduced in any dataset I have; I cannot identify their source (possibly a partial earlier run). Use the Phase 7 and 7B numbers above. Phase 7's 73 timeouts clustered in two windows with median RTF about 2 while load was identical to quiet windows (RTF 0.13-0.18). Those windows were environmental slowdowns. They did not reproduce in the 7B N=2 60-clip run (0 timeouts, RTF p50 0.128, system CPU median 19.5%). 7B did reproduce timeouts, but at N=4 via saturation, not at N=2.

## Confirmed
- Single FIFO worker; no priority; partials are 58-73% of busy time.
- Up to N=2 added latency is queueing only (final queue p50 0.24-0.33 s).
- N=3 saturates the worker; N=4 produces 40% final timeouts.
- Timed-out finals that reached the executor keep running and waste 46% of busy time at N=4.

## Unresolved (not tested)
- Cause of the Phase 7 N=2 slowdown windows (other CPU load, memory pressure, power plan: all untested).
- Effect of finals priority and of reduced partial cadence.
- Whether staggered real traffic changes capacity.
- Capacity with GPU (CUDA rebuild was not attempted).

## Proposed fix (needs approval; nothing implemented)
1. Priority scheduling: finals ahead of queued partials (small change in engine call ordering).
2. Partial backpressure: skip a partial when a decode for that speaker is pending or the queue has finals waiting; optionally lengthen the cycle under load.
3. Timeout accounting: do not start a final whose 10 s budget already expired in the queue; mark it dropped. Also stop partial work for a dropped speaker.
4. Surface dropped finals (log or marker), which is separate from the empty-decode handling and does not change it.
5. Environment check: record CPU and memory during any slowdown (a sampler exists) before blaming code.
6. Later option: CUDA build to raise capacity (large change, separate approval).

Validation plan if approved: rerun the 12-clip N=1 to N=4 matrix and the 60-clip N=2 run on the instrumented path; success = 0 timeouts at N=3, final queue p95 below 1.5 s at N=2, no WER regression against the same-manifest baseline.

Stopping here. Waiting for approval.
