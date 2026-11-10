# ScriptLiv — complete build description (current state)

Snypar Tech. Real-time speech-to-text platform. Staging only: nothing is deployed, nothing is committed (the tree is not a git repository).
Companion docs: `SCRIPTLIV_PLATFORM.md`, `SCRIPTLIV_API_INTEGRATION.md`, `SCRIPTLIV_RELEASE_READINESS.md`.

## 1. What it is

Users speak into the Flutter app or the web app. Audio streams over a WebSocket to a relay, which feeds a streaming ASR engine and sends text back live.
Every second of audio is metered against the user's plan, transcripts are saved per account, and sessions can be shared by link and watched live.

## 2. Components and ports

| Component | Folder | Port | Role |
|---|---|---|---|
| Platform API (FastAPI) | `scriptliv_api` | 8790 | Accounts, JWT, email verification, plans, usage ledger, reservations, billing, sessions, sharing, settings |
| Relay | `relays_phase7c` | 8772 | WebSocket speaker/viewer endpoint, billing enforcement, concurrency cap, talks to ASR workers |
| ASR worker EOU | `asr_worker` (venv `asr_venv`) | 8780 | Streaming Parakeet EOU 120M model (live text, end-of-utterance) |
| ASR worker Nemotron | `asr_worker` | 8781 | Nemotron 0.6B second-pass refinement of finished utterances |
| Web (Next.js) | `scriptliv_web` | 3100 | Marketing site and the signed-in web app |
| Mobile app (Flutter) | `st_transcribe_app` | — | Android app (iOS shares code, untested) |
| Database | MongoDB Atlas, db `scriptliv_staging` | — | All platform data |

Engines: EOU streaming model for live text, Nemotron for refinement. The whisper.cpp Parakeet engine is kept in the repo, untouched.

## 3. Account and email flow (latest change)

1. **Register** (`POST /v1/auth/register`) creates the account and sends a verification email. It does **not** sign the user in: the response has `verification_required: true` and no token.
2. **Sign-in is refused** (`POST /v1/auth/login` returns 403 `email_not_verified`, no token) until the emailed link is opened.
3. **Resend while signed out**: `POST /v1/auth/resend-verification`. Same 202 reply for unknown, verified or disabled accounts (no account enumeration), throttled to 5 per address. Signed-in resend (`/v1/me/email/resend`) still exists.
4. **Verify** (`POST /v1/auth/verify-email`). Web: after success the page says "Email confirmed… Taking you to sign in…" and moves to `/login` after about 2 seconds, with a Sign in button. Nothing signs the user in.
5. **Sign in** works once verified.
6. Forgot password / reset password: API, web and Flutter. Reset invalidates old sessions.

Tokens: 32-byte random, only the SHA-256 is stored, 24 h life for verify and 1 h for reset, single use, wrong-kind tokens refused, mailed tokens are never session tokens.
Defence in depth that remains: the backend still refuses transcription start, share links and checkout for an unverified account (403 `email_not_verified`), and the relay closes with 4403.

Email delivery: shared token logic is separate from delivery. Providers are Gmail API (OAuth2, send-only), Resend (used for Outlook/Hotmail/Live/MSN recipients) and SMTP, chosen by recipient domain. **All three are mock-tested only; no real email has been sent.**
In staging `SCRIPTLIV_DEV_RETURN_TOKENS=1` returns the token in the API response so the web screens can show an "Open the verification link" shortcut. Must be off wherever real mail is used.

## 4. Plans, usage and billing

- Plans: free Basic with 300 minutes a month, paid plans, add-on minutes.
- Per-second usage ledger. The relay takes audio from the allowance chunk by chunk before it reaches the engine. `usage.record` is idempotent and cumulative, so repeats never double-bill.
- **Strict limit**: when the allowance ends, the audio is cut at the exact sample and the socket closes with 4402 `out_of_minutes`. No grace period. Overshoot is recorded as unbilled. A personal limit set by the user works the same way (`personal_limit`).
- **Concurrency reservation**: authorize creates a reservation; a second concurrent speaker gets 4402 `allowance_reserved`. Reconnecting with the same session id reuses its reservation. The same session id on a new socket supersedes the old one (4409 `superseded`). Reservations are released on end, drop or timeout.
- **Payment failure flow** (replaces the old 3-day grace): `past_due` keeps paid access but a running recording is never extended, then configurable retries, then `restricted` (free Basic only; account and transcripts kept). Only provider-confirmed results change status. Retry button never activates a plan without provider confirmation. Webhooks: HMAC-SHA256, 300 s tolerance, unique `event_id`.
- **Stripe adapter exists but was never run against Stripe** (no keys). Checkout, portal, renewal, failure and webhook delivery are untested.

## 5. Relay

- Speaker and viewer roles, per-session broadcast, transcript stored per event.
- Wire format: `{"text":..., "partial": true|false}`; errors `{"type":"error","code":...}`.
- Close codes: 4401 invalid token, 4402 out of minutes / personal limit / allowance reserved / payment required, 4403 email not verified, 4409 superseded, 1011 `asr_connection_lost`, 1013 `server_busy`.
- **ASR-loss handling**: if the engine connection dies, the client gets 1011 with a clear message instead of a silent normal close. Keepalive pings are off on the loopback relay-to-worker sockets.
- **Capacity cap** `STT_MAX_ACTIVE_STREAMS` (default 3, 0 = unlimited). Extra speakers get 1013 before authorization, so nothing is reserved or billed. Measured: this machine (one GPU, one EOU worker process) handles about 3 real-time streams.
- Text quality: numbers are written as digits, tail-word hold prevents sub-word fragments, silence endpointing for every engine, optional Nemotron refinement that updates stored finals.

## 6. Web app (`scriptliv_web`)

Pages: marketing home, register, login, forgot/reset password, verify email, then the signed-in app: dashboard with usage card, record, transcripts (list, detail, rename, delete), share on/off with copyable link, plans and checkout, billing and payment status banner, settings, and the public shared viewer `/s/{token}` (live while the session runs).
Refreshed using the ScriptLiv gradient-play logo assets, with Settings placed in the top bar beside the logo.
Auth screens: "check your email" panel (address, Resend, staging link) after sign-up and when sign-in is refused for an unverified account.
Stack: Next.js, Tailwind, shared UI primitives (`components/ui`), `components/check-email.tsx`, `lib/api.ts` typed client. Checks: tsc clean, eslint clean, 10 vitest, `next build` succeeds.

## 7. Mobile app (`st_transcribe_app`)

Login and register (register shows "Verify your email" with Resend and "I have verified, sign in"), forgot password, live recording with partial/final text, usage card, sessions list, share, shared-link screen (`scriptliv://s/<token>`), wake-lock toggle, Snypar Tech copyright, messages for 4402/4403/4409 and a payment banner.
Debug build installed on a connected phone (`.staging` app id). **The APK currently on the phone is the build from before the verify-before-login change; it has not been rebuilt.**
Checks: `flutter analyze` shows 4 pre-existing infos; 59 tests pass.

## 8. Security

Done and tested (API suite): JWT alg-none / wrong secret / expired / wrong type rejected; disabled accounts dead; login errors reveal nothing; per-account isolation of usage, settings, sessions, billing; relay cannot hijack another account's session or bill another's usage; shared view leaks nothing private; `X-Relay-Secret` constant-time and closed when unset; CORS not wildcard, credentials off; API docs/openapi off unless `SCRIPTLIV_ENABLE_DOCS=1`; share tokens 128-bit; no stack traces in errors.
Open: `/internal/*` is on the public API port (needs a network restriction); login/reset throttle is in process memory; no external pen test; no dependency CVE scan; staging uses dummy secrets by decision.

## 9. Database

Indexes verified by `explain()` (all audited queries use an index): unique `users.email`, `subscriptions.user_id`, `usage_sessions.session_id`, `(usage_minutes: session_id, minute)`, session and share-token indexes, `email_tokens` (hash unique, TTL), `provider_events.event_id`, payments `provider_ref`, transcript `(session_id, seq)`; added `settings.user_id`, `billing_details.user_id`, subscription provider ids, and a usage-sessions reporting index. Tiny staging data only.

## 10. Test results (latest runs)

| Suite | Result |
|---|---|
| API | 113 passed |
| Relay | 187 passed, 1 skipped (includes ASR-loss and capacity-gate tests) |
| Web | tsc, eslint clean; 10 vitest; build OK |
| Flutter | 59 passed; 4 pre-existing analyzer infos |
| Live smoke (this pass) | register: no token; login unverified: 403; verify 200; login 200; web `/register` and `/verify-email` 200 |

Real-stack results (earlier in this work): limit 60 s billed exactly 60.0 s with 4402 and no re-entry; concurrency, supersede and drop-recovery behave and bill correctly; 3 concurrent streams x 300 s billed exactly 300.0 s each; 5 streams with cap 3 served 3 and refused 2 with 1013, billed 0. Latency under 3 streams is visibly worse than a single stream.

## 11. Not done / not tested

- Real email delivery (Gmail API, Resend to Outlook, spam placement, bounces).
- Real Stripe test-mode run.
- iOS (no Mac/Xcode/iPhone).
- Android: logged-in recording after the latest changes, background recording, network switching, and the new verify screens on a device (APK not rebuilt).
- ASR capacity above about 3 streams per worker; needs more workers or GPUs and routing. No dedicated "server busy" message in the clients yet.
- Production: secrets, HTTPS and app links, retention policy, backups, monitoring, `/internal/*` restriction, shared throttle storage.
- WER and QA were deliberately skipped by decision; the dedicated QA features were removed.

Decision: **staging release candidate yes, production no.**

## 12. Housekeeping to know about

Temporary `~/.gradle/gradle.properties` (`-Xmx2G`); Flutter at `C:/flutter_3479`; the `.staging` app id; leftover `@example.com` test accounts in staging Mongo; one accidental API kill/restart during testing; a dummy password printed once (not rotated by decision); `benchmarks/results/tail_hold/*.py` still reference the retired `qa.env`; QA files retired under `staging_secrets/_retired_qa/` and `benchmarks/_retired_qa/`.

## 13. How to run (staging)

- API: `python run_staging.py` in `scriptliv_api` (reads `staging_secrets/api.env`).
- Relay: `python benchmarks/results/phase7d/start_platform_relay.py` from the repo root. Set `STT_MAX_ACTIVE_STREAMS` first for a different cap.
- Web: `npx next build`, then `node node_modules/next/dist/bin/next start -p 3100` in `scriptliv_web`. A source change needs a rebuild and a restart.
- API/relay tests: `python -m pytest -q -p no:warnings` in each folder. Web: `npx vitest run`. Flutter: `flutter analyze`, `flutter test`.
