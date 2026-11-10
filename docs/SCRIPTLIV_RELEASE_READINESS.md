# ScriptLiv — staging release-candidate report and readiness decision

Scope: staging only. Nothing is deployed and nothing is committed (the tree is not a git repository). Statuses below come from
runs actually made in this pass; where a thing was only unit-tested with mocks it says so. Dummy staging credentials were not rotated by decision.

## Decision

**Staging release candidate: YES. Production: NOT ready.**
The strict-limit, concurrency, supersede and drop-recovery behaviour is verified on the real stack (API + relay + EOU/Nemotron workers).
Production is blocked by: no live email provider or Stripe test (mocks only), no iOS, `/internal/*` still on the public port,
in-memory login throttle, single ASR worker capacity (3 concurrent streams on this box), no logged-in on-device Android test.

## The 15 items

### 1. Changes (status: done)
- Strict limit end to end (relay `core/billing.py`, `core/streaming_session.py`; API `usage.py`, `usage_routes.py`). Close `4402 out_of_minutes`, no grace. Overshoot recorded as unbilled.
- Reservation/concurrency (`allowance_reserved`, `session_taken`, 4409 supersede, release on end/drop/timeout).
- Payment failure flow replaces the 3-day grace (`subscriptions.py`, `payments.py`, `routers/billing.py`): `past_due` (paid access kept, running recording never extended) -> configurable retries -> `restricted` (free Basic only; account and transcripts kept). Only provider-confirmed results change status.
- Email verification gate: register does not sign in (no token). Sign-in is refused (`email_not_verified`) until the emailed link is opened; signed-out resend endpoint added. Backend (transcription, share, purchase) and relay 4403 checks remain as defence in depth. Web and Flutter show a check-your-email screen.
- Email: shared token logic separate from delivery (`email_service.py`, `email_providers.py`): Gmail API OAuth2 send-only, Resend (for Outlook recipients), SMTP. Tokens 32-byte urlsafe, sha256 at rest, 24 h verify / 1 h reset, single-use, TTL index. Forgot/reset password in API, web and Flutter.
- Dedicated QA functionality removed from Flutter, web, API, relay (files retired under `staging_secrets/_retired_qa/`, `benchmarks/_retired_qa/`).
- Security hardening: API docs/openapi off unless `SCRIPTLIV_ENABLE_DOCS=1`; share token 96 -> 128 bit.
- MongoDB indexes added (see item 10).
- Relay: ASR-loss handling (`1011 asr_connection_lost` instead of a silent normal close); keepalive pings disabled on the loopback relay<->worker sockets (client side `engines/streaming_worker_engine.py`, server side `asr_worker/stream_worker.py`); **concurrency cap** `STT_MAX_ACTIVE_STREAMS` (default 3, 0 = unlimited): extra speakers get `1013 server_busy` before authorization, so nothing is reserved or billed.
- Clients: messages for 4402/4403/4409, payment banner, verify notice, forgot/reset password. Engines unchanged: EOU 120M streaming + Nemotron 0.6B refinement; whisper.cpp Parakeet engine retained untouched.

### 2. Tests executed (actual results)
| Suite | Result |
|---|---|
| API (`scriptliv_api`) | **113 passed** (incl. 20 new security, strict-limit, payment-failure, email tests) |
| Relay (`relays_phase7c`) | **187 passed, 1 skipped** (incl. ASR-loss test and 3 capacity-gate tests) |
| Web | tsc clean, eslint clean, 10 vitest pass, `next build` OK (rerun after the verify-before-login change) |
| Flutter | `analyze`: 4 pre-existing infos; 59 tests pass (rerun after the verify-before-login change; the APK on the phone is OLD, not rebuilt) |
| Real-stack e2e (`e2e_final.py`) | S2–S5 pass (below). S1 harness printed `1000` in the concurrent run; direct check, 4/4 runs: `4403 email_not_verified`. The harness flake is a client-side race in the scratch script, not proven; the direct result is what is claimed |
| Load (`e2e_load.py`) | see item 11 |

### 3. Strict-limit results — PASS
Real stack, personal limit 60 s, audio sent in real time:
- Closed `4402 out_of_minutes` with the error message; **billed exactly 60.0 s**; client had sent 63.0 s, the remainder was cut at the sample and never billed.
- Reconnect with the same session id: `4402 personal_limit`. New session: `4402 personal_limit`. Billed stays 60.0 s.
Boundary and ledger behaviour (exact edge, zero allowance, overshoot as unbilled, idempotent cumulative reports, no double billing) are covered by `test_strict_limit.py`.

### 4. Billing and concurrent-session results — PASS
- Concurrency: second concurrent speaker `4402 allowance_reserved`; after the first ended normally the next was allowed; billed 25.0 s over 2 sessions (expected ~25).
- Supersede: old socket `4409 superseded`, new one OK; billed 15.0 s, 1 session, no double billing.
- Abrupt drop: reservation released, next speaker allowed; billed 10.0 s.
- Cross-account: per-stream billing in the multi-session runs matched sent seconds exactly for every account (item 11); no cross-billing.
Caveat: results are from one machine with test accounts; production-scale reservation locks (`usage_locks`) not load-tested.

### 5. Payment retry / restriction results — PARTIAL
Logic verified by tests with a faked provider: `past_due` keeps paid access, running recording not extended, retry never activates without provider confirmation, configurable retry limit/interval/final status, restriction keeps account and transcripts, webhook HMAC-SHA256 with 300 s tolerance and unique `event_id`. **The Stripe adapter was never run against Stripe** (no keys). Real checkout, portal, renewal, failure and webhook delivery: NOT TESTED.

### 6. Gmail API results — NOT TESTED (mock only)
Provider code and token flow are unit-tested with a mocked transport. No real OAuth2 credentials/refresh token were used and no real message was sent or received. Real delivery is not claimed.

### 7. Outlook via Resend results — NOT TESTED (mock only)
Routing by recipient domain and the Resend request shape are unit-tested with mocks. No Resend key, no real send, no Outlook inbox/spam-folder check. Real delivery is not claimed.

### 8. Email verification security — PASS (logic), delivery NOT TESTED
Tested: tokens hashed at rest, expiring, single-use, wrong-kind token refused (reset token cannot verify email and vice versa), mailed tokens are not session tokens, access tokens cannot verify/reset, forgot-password does not reveal whether an account exists, reset invalidates old sessions (`pwv`), register returns no token and login is 403 until verified (smoke-tested live on :8790), unverified account blocked from transcription (4403, also verified on the real relay), share links and purchase. `SCRIPTLIV_DEV_RETURN_TOKENS=1` in staging returns `dev_token` in API responses: **must be off anywhere real mail is used.**

### 9. Security audit findings
Fixed: API docs/openapi exposure (now off by default); share-token entropy raised to 128 bit.
Tested PASS (20 tests in `test_security.py` + earlier): JWT alg-none / wrong secret / expired / wrong-type rejected; disabled account's token dead; login errors do not reveal which part was wrong; per-account usage/settings isolation; cross-user rename/unshare/read denied; relay cannot hijack another account's session id; relay usage cannot bill another's session; shared view leaks nothing private; billing endpoints need auth and are own-account only; `X-Relay-Secret` constant-time and near-miss rejected, closed when unset; CORS not wildcard and credentials off; errors do not leak internals; webhook signatures.
Open (disclosed, not fixed):
- `/internal/*` is served on the public API port; protected only by the relay secret. Needs a network-level restriction.
- Login/reset throttle is in-process memory (not shared across workers/restarts).
- Relay admission is a fixed cap, not adaptive load shedding.
- Staging uses dummy secrets by decision; production secrets/rotation not exercised.
- No external penetration test; dependency CVE scan not run.

### 10. MongoDB index audit — PASS for staging data volumes
Already correct: `users.email` unique, `subscriptions.user_id` unique, `usage_sessions.session_id` unique, `usage_minutes (session_id, minute)` unique, `sessions` (`session_id` unique, `owner_id`, `share_token` unique sparse), `email_tokens` (`token_hash` unique, TTL, `(user_id, kind, used)`), `provider_events.event_id` unique, `payments.provider_ref` partial unique, `transcript_events (session_id, seq)` unique.
Added: `settings.user_id`, `billing_details.user_id` (unique, fall back non-unique if old duplicates exist), `subscriptions.provider_customer_id` / `provider_subscription_id` (sparse), `usage_sessions (user_id, ended_at, last_report_at)`. A partial `$type` index was tried and dropped: not used for equality queries (COLLSCAN); sparse indexes verified as IXSCAN. `explain()` on the staging DB: all audited queries IXSCAN.
Caveat: tiny staging dataset; no production-scale data; `usage_locks` is keyed on `_id`.

### 11. Long-session and multi-session results — PARTIAL (capacity limited)
All on one machine, one GPU, one EOU worker process, real-time audio, test accounts.
- Single stream: real-time, first text ~2 s, no drift.
- Scaling probe (40 s each): 2 streams drift up to ~1.2 s; 4 streams up to ~3.4 s; all billed exactly 40.0 s, close 1000.
- **First run, 5 concurrent (600 s + 4x120 s), no cap: FAIL.** Every stream died with `1011 keepalive ping timeout`; billed 50–51 s of 120/600 s sent (fail-closed: under-billing, no over-billing). Cause: the single worker could not keep 5 streams real-time, audio backed up and the relay's client socket stopped answering pings. Mitigations applied: `asr_lost` handling, loopback keepalive off, and the capacity cap.
- **After fix, 3 concurrent x 300 s: PASS.** All three: close 1000, billed 300.0 s each (= sent), 23–26 finals each, no errors. Worst client drift 4.5 s, first text 7.7–12 s under load, max gap 10.7 s. Latency under load is visibly worse than single-stream.
- **After fix, 5 concurrent x 60 s with cap 3: PASS as designed.** 3 served and billed exactly 60.0 s; 2 refused `1013 server_busy`, billed 0, no session created.
- Not run: the 600 s single long session after the fix (the 300 s x 3 run is the longest verified); anything above 5 streams; multi-hour sessions; relay memory trend beyond 36 -> 45 MB observed earlier.
- Capacity is the real limit: **about 3 concurrent live streams per worker on this hardware.** Production needs more worker processes/GPUs and routing, not a bigger cap.
- Clients treat `1013` as retryable; there is no dedicated "server busy" message in web/Flutter yet.

### 12. Android verification — PARTIAL
Done on a connected phone (RZCT81J66RV), earlier and in this pass: debug build installed (`.staging` app id); live transcription with EOU + Nemotron refinement; shared-session deep link `scriptliv://s/<token>`; new build launched, login screen with "Forgot password?" checked visually; 3 background/foreground cycles and screen off/on with no crash/ANR (login screen only).
NOT TESTED on device: logged-in recording after this pass's changes, recording while backgrounded, network switching (Wi-Fi/mobile), verify banner and 4402/4403/4409 screens on device, Play signing.

### 13. iOS status — NOT TESTED
No Mac/Xcode/iPhone available. Flutter code is shared, iOS-specific background audio, permissions, universal links and App Store requirements are unverified. The iOS validation doc is design-only.

### 14. Remaining blockers
1. Real delivery tests: Gmail API (OAuth2), Resend to Outlook, spam-folder placement, bounce handling.
2. Real Stripe test-mode run: checkout, failed payment, retry, webhook, restriction.
3. iOS build and test; Android logged-in background/network-switch test.
4. Restrict `/internal/*` at network level; move throttling to shared storage.
5. ASR capacity: more workers/GPUs and routing; adaptive shedding; client "busy" UX; retest above 3 streams.
6. Production secrets, HTTPS/app links, retention/deletion policy, backups, monitoring, dependency/pen-test review.
7. Turn off `SCRIPTLIV_DEV_RETURN_TOKENS` outside staging.

### 15. Production-readiness decision
**NOT ready for production.** Ready as a staging release candidate for further testing, with the blockers above.

## Housekeeping disclosed
Temporary `~/.gradle/gradle.properties` (`-Xmx2G`); Flutter at `C:/flutter_3479`; `.staging` app id; e2e test accounts (`@example.com`) remain in staging Mongo; one accidental API kill/restart during testing; a dummy password was printed once; stale scratch files; `benchmarks/results/tail_hold/*.py` still reference the retired `qa.env`; ASR workers, API and relay were restarted with the new settings; the relay is running with the default cap of 3.
