# Phase 7D real-client test report

**Client used: `qa_scenarios.py` (protocol-level: real WebSocket + HTTP, real-time pacing, 100 ms chunks, 3 accounts). It is NOT the Flutter app.** Items that need the real app are listed at the end as NOT TESTED. Relay: staging :8772, real Parakeet, Phase 7C scheduler. Audio: 12 Svarah clips (same manifest as 7C).

| Acceptance criterion | Result | Evidence |
|---|---|---|
| 3 QA accounts transcribe simultaneously | PASS (protocol client) | `phase7d_simul.json`: 14/14/12 finals; 20-min run below |
| No duplicate finals | PASS | 0 duplicate (conn_id, flush_seq) in 866 flush records; client text == DB text |
| No unexplained missing finals | PASS | simul: 41 scheduler final jobs = 40 sent + 1 `dropped_empty_text`; long: 801 = 781 sent + 20 empty. Flush diag overall: 835 final_sent, 22 dropped_empty_text, 9 dropped_not_pending. Client finals == backend-stored finals for all 3 accounts |
| Skipped partials do not break UI | PARTIAL | A skipped partial sends nothing, so the wire stream is unchanged. Flutter UI not tested |
| Finals display correctly | NOT TESTED (UI) | text delivered correctly on the wire |
| Audio downloadable by authorized users only | PASS (API) | own download bit-exact vs streamed PCM (incl. 20-min, ~38.5 MB each); other accounts 404; no token 401 |
| Disconnect/reconnect does not corrupt sessions | PASS for QA store, **FAIL for legacy store** | see below |
| Long-duration without unexplained failures | PASS | 20 min x 3 accounts: 280/244/257 finals, 0 abandoned, 0 relay errors/tracebacks |
| Account-level isolation | PASS | `phase7d_access.json` 19/19 checks |
| Logs traceable to session and account | PASS | `qa_events`/`qa_audit` carry account, session, connection index, conn_id, seq; scheduler and flush-diag logs join on conn_id |
| No regression in Parakeet path | PASS (limited) | 150 tests pass, 1 skipped; inference path and decoder params untouched; WER not re-measured in 7D |

## Reconnect (`phase7d_reconnect.json`)
Connection 0 dropped abruptly mid-session, reconnect with the same session id. QA store: 2 connections recorded (conn 0: 3 finals, conn 1: 8 finals + 1 empty drop), audio 1,432,670 B downloaded == sent, no duplicate (conn, seq). Conn 0's third final came from the relay's disconnect flush after the socket was dead: stored, but the client never received it.

**Finding (pre-existing, unchanged per the no-refactor rule):** legacy `start_session` clears events when a session id is reused. After the same reconnect, `data/transcripts.db` held 8 events instead of 11. Viewer/history replay loses the first connection's transcript. QA store is unaffected. Needs your decision (small fix in production code).

## Other results
- Empty decodes: 1 in simul, 20 in long (all tester one); accounted as `dropped_empty_text`, no retry (per constraint).
- 0 errors/tracebacks in `relay.log` / `long.log`.
- Performance numbers: see `PHASE7D_PERFORMANCE_REPORT.md`.

## NOT TESTED (needs you, on real devices)
1. Flutter app on any device: login, consent screen, mic capture, live display, partial-skip rendering, auto-reconnect UI, viewer/share link.
2. Audio playback/download/history UI (does not exist in the app; API only).
3. Real network or tunnel latency, real mics, three physical users.
4. Real tester consent.
5. Flutter build: installed Dart 3.12.2 < pubspec `^3.13.7`; only analyzed in a scratch copy with the SDK constraint lowered (clean).
Run the app with `--dart-define=QA_BACKEND_HTTP=http://<host>:8772` and `QA_BACKEND` pointing at the staging WS.
