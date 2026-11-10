# ScriptLiv platform: status, defaults, open decisions

Staging only. Not deployed. Not committed.

## Components
- `scriptliv_api` (FastAPI, MongoDB Atlas db `scriptliv_staging`, :8790): accounts, JWT, email verification, plans, per-second usage ledger, add-ons, sharing, settings, Stripe adapter.
- Relay (`relays_phase7c`, :8772 staging): live ASR over WebSocket; authorizes each session with the API and reports cumulative audio seconds every 10 s plus a final report on close.
- Web (`scriptliv_web`, Next.js, :3100): marketing, register/login, usage dashboard, record, transcripts, sharing, plans, settings, public shared viewer `/s/{token}`.
- Mobile (`st_transcribe_app`, Flutter): see its own notes.

## Verified end to end (real relay, eou120m engine)
- Register, JWT accepted by relay, 15 s streamed = 15.0 s metered, session ended, transcript saved, share link, shared view live then not live.
- Personal limit 1 min: speaker stopped with close 4402 at 60.1 s; new session refused with 4402 `personal_limit`.
- Overshoot is up to about 1 s.

## Assumed defaults (confirm)
- Per-second metering, no rounding up to minutes.
- No rollover. Monthly reset counted from subscription start; lazy roll on first use after the period ends.
- Included minutes are used before add-on minutes. Add-ons expire at period end.
- Only the speaker is billed. Viewers never use minutes. No device or login limit.
- Languages: English only for now.
- "Prevent auto-lock" is a client wake-lock setting.
- Personal usage limit blocks new sessions and stops a running one.
- Sharing is off by default; owner turns it on per session.

## Known gaps
- Forgot-password is implemented (`POST /v1/auth/forgot-password`, `/v1/auth/reset-password`, web pages `/forgot-password` and `/reset-password`, app login screen). Mail delivery is verified with mocked providers only, not against Gmail or Resend.
- Payments are not configured. Without Stripe keys, checkout returns 503 `payments_not_configured`; the UI disables purchase buttons.
- The dedicated QA functionality (tester allowlists, QA console, QA audio/transcript collection, Drive QA integration) was removed. Retired files are parked in `staging_secrets/_retired_qa/` and `benchmarks/_retired_qa/`. A few old benchmark scripts under `benchmarks/results/tail_hold/` still reference `qa.env` and removed endpoints; they are not part of the product.
- API docs (`/docs`, `/redoc`, `/openapi.json`) are off unless `SCRIPTLIV_ENABLE_DOCS=1`.
- `/internal/*` is on the same port as the public API and protected only by `X-Relay-Secret`; restrict it at the network level before any production use.
- The login/forgot-password throttle is in memory per process (not shared across workers).
- The relay is a single process with no load shedding. Under CPU starvation it falls behind real time and fails closed (no over-billing).
- Shared web viewer polls `GET /v1/shared/{token}` (1 s while live, 15 s after). It does not use the relay WebSocket because that needs a session id and access code the shared API does not expose.
- "Open in app" link `scriptliv://s/{token}` depends on the mobile app registering that scheme.
- No retention period is set; none invented.
- No capacity claim: only a handful of accounts were exercised.
- No iOS build or support claim without Xcode/macOS.
- Customer sessions need a streaming engine on the relay (`STT_ENGINE` not `parakeet`).

## Decisions needed
Rollover, rounding, add-on order, auto-lock semantics, retention period, language list, sharing default, payment provider and tax, final app name.

## Mobile (Flutter) platform mode
- Build with `--dart-define=SL_API_HTTP=http://HOST:8790 --dart-define=SL_WS=ws://HOST:8772`. Without them the app keeps its legacy local mode; (the QA build mode was removed).
- Added: register and sign-in, usage card (plan, minutes left, add-on balance, reset date, warnings), account sessions, share on/off with copyable link, delete, out-of-minutes message on relay close 4402, "prevent auto-lock" wake lock (on by default, toggle in Settings), shared-link screen (`scriptliv://s/TOKEN`, or `https://.../s/TOKEN`), "Snypar Tech" copyright.
- Android intent filter for `scriptliv://s` added. iOS URL scheme and universal links are not configured; no iOS build or support claim without Xcode/macOS.
- Verified: `flutter analyze` (info-level notes only) and 64 tests pass in a scratch copy. The installed Dart SDK is 3.12.2 but `pubspec.yaml` requires `^3.13.7`, so `flutter pub get` fails in the real project until the SDK is updated. The scratch copy used `^3.12.0`.
- Not verified on a device or emulator: the platform-mode screens, wake lock and deep link have not been run.

## Engines and text refinement (staging)

- `STT_ENGINE` unset or `parakeet`: the original whisper.cpp Parakeet engine (kept, untouched).
- `STT_ENGINE=eou120m`: streaming EOU model; partials and finals go out live.
- `STT_REFINE_ENGINE=nemotron` (+ `STT_REFINE_WORKER_URL`): optional second pass. After a final is sent, the utterance audio is
  re-recognised by `nvidia/nemotron-speech-streaming-en-0.6b` in a separate worker (:8781). If the result passes the guard, the stored
  line is replaced and clients get `{"type":"refine","seq":N,"original":"...","refined":"..."}` and swap the line in place.
  Set `STT_REFINE_ENGINE=""` to turn it off. `STT_REFINE_LOG_FILE` writes a jsonl of every decision.
- The live path never waits on refinement. Jobs are bounded (6 pending, one at a time, 20 s timeout); any failure keeps the EOU text.
- Guard (`core/refiner.py::refine_text`): spoken numbers become digits ("seven eight one" → 781); same words once case, punctuation,
  fillers and number format are ignored → accept; utterances under 4 words may only change formatting; otherwise word count within
  25% and word similarity ≥ 0.8.
- The relay retries the closing usage report up to 3 times so a transient API error cannot drop the end of a session's billing.

## Owner decisions: chosen defaults (written before implementation)

These replace the earlier 3-day grace policy. Every value is env-configurable (`SCRIPTLIV_*`) in `scriptliv_api/app/config.py`.

### Payment failure and access
| Setting | Default | Env |
|---|---|---|
| Provider retry attempts before final failure | 3 (total failed invoices tolerated) | `SCRIPTLIV_PAYMENT_MAX_RETRIES` |
| Interval between provider retries (days) | 1,3,5 (informational; the provider schedules retries) | `SCRIPTLIV_PAYMENT_RETRY_DAYS` |
| Status after the final failed retry | `restricted` | `SCRIPTLIV_PAYMENT_FINAL_STATUS` |
| Minimum seconds between user-triggered "Retry payment" calls | 60 | `SCRIPTLIV_PAYMENT_RETRY_COOLDOWN` |

State machine of `subscriptions.status`: `active` -> (invoice.payment_failed, attempts < max) `past_due` -> (invoice.paid) `active`
or -> (attempts >= max) `restricted` -> (invoice.paid) `active`. `customer.subscription.deleted` -> `canceled`.

- `past_due`: paid allowance still usable for NEW sessions (provider is still retrying); user sees a "payment failed, update your payment method" banner.
- `restricted`: no paid subscription allowance and no paid add-on seconds for new sessions; only the free allowance applies. Account, transcript history, billing page and retry stay available. API returns a clear `payment_required` message.
- Clicking Retry never changes status. Only an authenticated provider response (retry result fetched with the secret key) or a signed webhook does.
- A running recording is never cut because of a status change, and its allowed duration (the reservation grant) is never extended.

### Strict recording limit
- Limit = remaining funded seconds at session start (+ already-metered `base_seconds` on reconnect). No grace seconds.
- Relay checks the allowance BEFORE sending each audio chunk to the engine, truncates the chunk at the exact limit, closes 4402 `out_of_minutes`.
- Overshoot that cannot be avoided is recorded in the ledger with source `unbilled_overshoot` and never billed.

### Concurrency
- One active reservation per user; second session gets 4402 `allowance_reserved`. Reconnecting the same session id reuses its reservation.

### Email verification
- Register creates the account but does NOT sign in: the response has no token (`verification_required: true`). Sign-in is refused (403 `email_not_verified`, no token) until the emailed link is opened. Signed-out resend: `POST /v1/auth/resend-verification` (identical 202 reply for unknown, verified or disabled accounts; throttled). Web and Flutter show a "check your email" screen after sign-up and on a refused sign-in, with Resend.
- Defence in depth: the backend still refuses (403 `email_not_verified`) transcription start, share links and checkout for an unverified account, and the relay closes 4403, e.g. for an account whose email was changed later.
- Tokens: 32-byte random, only the SHA-256 hash stored, 24 h expiry (password reset 1 h), atomic single use.
- Providers: Gmail API (recipients other than Outlook domains) and Resend (Outlook/Hotmail/Live/MSN recipients), selected by recipient domain; env-configured; none configured -> endpoint answers "unavailable".

### Relay and close codes
- 4402 `out_of_minutes` / `personal_limit` / `allowance_reserved` / `payment_required`; 4403 `email_not_verified`; 4409 `superseded`; 4401 invalid token.
- The out-of-minutes notice is sent the moment the limit is reached; the socket is closed with 4402 after the already-allowed audio is finalized.
- A new speaker connection on the same session id closes the older one with 4409 and waits (up to 8 s) for its closing report before authorizing, so a reconnect never double-reserves.

### Email delivery configuration (none are set in staging)
`GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REFRESH_TOKEN`, `GMAIL_SENDER` (send-only OAuth2 scope); `RESEND_API_KEY`, `RESEND_FROM`
(verified domain); `EMAIL_RESEND_DOMAINS` overrides the Outlook-family list. Outlook-family recipients never fall back to Gmail.
`SCRIPTLIV_DEV_RETURN_TOKENS=1` returns the token in the API response for staging tests; it must be off in production.
