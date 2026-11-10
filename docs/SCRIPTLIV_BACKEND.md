# ScriptLiv — Backend guide (simple language)

Everything that runs on the server side: what each piece does, every endpoint, who calls it, and what can go wrong.
Frontend (web + phone app) is in `SCRIPTLIV_FRONTEND.md`. Big picture is in `SCRIPTLIV_COMPLETE_BUILD.md`.

State: staging only. Nothing deployed, nothing committed.

---

## 1. The four backend parts

| Part | Folder | Port | One-line job |
|---|---|---|---|
| Platform API (FastAPI) | `scriptliv_api` | 8790 | Accounts, login, email verification, plans, usage minutes, billing, saved transcripts, sharing, settings |
| Relay (WebSocket) | `relays_phase7c` | 8772 | Takes live audio from the app, enforces the minute limit, sends text back |
| ASR worker EOU | `asr_worker` (venv `asr_venv`) | 8780 (local only) | Speech model that turns audio into live text |
| ASR worker Nemotron | `asr_worker` | 8781 (local only) | Second, bigger model that cleans up finished sentences |
| Database | MongoDB Atlas, db `scriptliv_staging` | - | Stores everything |

How they talk:

```
Phone / Web  --HTTP-->  API (8790)  <--HTTP, secret header--  Relay (8772)  --local WebSocket-->  ASR workers
Phone / Web  --WebSocket (audio + JWT)-------------------->  Relay
API  <---->  MongoDB          Relay  ---->  MongoDB (transcript mirror)
```

Key rule: **the relay never decides who may speak. The API decides.** The relay asks the API "may this user start?" and keeps reporting seconds used.

---

## 2. Platform API (port 8790)

All paths start with `/v1` except health and the relay-only `/internal/v1`.

### 2.1 How login works (JWT)

- Login returns a **token** (JWT, HS256, lives 7 days). Send it as header `Authorization: Bearer <token>`.
- Token carries `sub` (user id), `pwv` (password version) and `typ=access`.
- Changing or resetting the password bumps `pwv`, so every older token dies.
- Disabled account: token stops working (401).
- Two helper rules used below:
  - **auth** = valid token needed.
  - **verified** = valid token AND email verified, else 403 `email_not_verified`.

### 2.2 Error format

Every error looks like:

```json
{"error": {"code": "email_taken", "message": "Human readable text"}}
```

The web client (`ApiError`) and phone client (`ApiException`) read `code` and `message`.

### 2.3 Account endpoints (`routers/account.py`)

| Method + path | Auth | Body | Success | Errors | What it does |
|---|---|---|---|---|---|
| `GET /healthz` | none | - | `{"ok":true}` | - | Is the API alive |
| `POST /v1/auth/register` | none | `name, email, password` (min 8) | 201 `{verification_required:true, user, verification:{delivery, dev_token?}}` **no token** | 409 `email_taken`, 422 `weak_password` | Creates account, creates free Basic plan, emails verify link. Does NOT sign in |
| `POST /v1/auth/login` | none | `email, password` | `{token, user}` | 401 `bad_credentials`, 403 `email_not_verified` (no token), 429 `too_many_attempts` | Sign in. Refused until email verified |
| `POST /v1/auth/resend-verification` | none | `email` | 202 same reply always | 429 | Send a new verify link when signed out. Same answer for unknown/verified/disabled emails (nobody can probe which emails exist) |
| `POST /v1/auth/verify-email` | none | `token` | `{user}` | 400 `invalid_token` | Opens the emailed link. Accepts "verify" and "change email" tokens |
| `POST /v1/auth/forgot-password` | none | `email` | 202 same reply always | 429 | Emails a reset link (1 h) |
| `POST /v1/auth/reset-password` | none | `token, new_password` | ok | 400 `invalid_token`, 422 `weak_password` | Sets new password, kills old sessions |
| `GET /v1/me` | auth | - | `{user}` | 401 | Who am I |
| `PATCH /v1/me` | auth | `name` | `{user}` | - | Rename |
| `POST /v1/me/email` | auth | `new_email, password` | `{pending_email, delivery}` | 403 `bad_password`, 409 `same_email`/`email_taken`, 503 `email_not_configured` | Start email change; mails a "change" link to the new address |
| `POST /v1/me/email/resend` | auth | - | delivery info | 409 `already_verified`, 503 `email_not_configured` | Signed-in resend of verify link |
| `POST /v1/me/password` | auth | `current_password, new_password` | `{token}` (new one) | 403 `bad_password`, 422 | Change password; old tokens die, caller gets a fresh one |
| `GET /v1/settings` | auth | - | `{settings, supported_languages}` | - | Read user settings |
| `PUT /v1/settings` | auth | any of `theme` (light/dark/system), `language` ("en" only), `prevent_auto_lock`, `usage_warnings`, `warn_percents` (1-99, max 4 values), `personal_limit_minutes` (0..1,000,000 or null) | same shape | 422 | Save settings. `personal_limit_minutes` is a self-set hard cap |

Email tokens (verify / reset / change): 32 random bytes, only the SHA-256 is stored, single use, a token of the wrong kind is refused, mailed tokens are never login tokens. Lifetimes: verify/change 24 h, reset 1 h.

Throttles (in memory, per process): login, forgot (5 per 15 min), resend (5), email-change, password-change, verify (20), reset (10). Gone after restart.

### 2.4 Plans and billing endpoints (`routers/billing.py`)

Plans: **Basic** 300 free min/month, **Pro** 2,500 min/month for $20, **Add-on** 1,000 min for $10.

| Method + path | Auth | Body | Success | Errors | What it does |
|---|---|---|---|---|---|
| `GET /v1/plans` | none | - | plans, add-on, `purchasing_available` | - | Catalogue. `purchasing_available` is false until Stripe keys exist (that is why Upgrade is greyed out) |
| `GET /v1/subscription` | auth | - | `{subscription:{plan, plan_name, status, period_start, renews_or_resets_at, cancel_at_period_end, access_ends_at, price_usd_month, payment:{state, access_restricted, message, failed_attempts, max_retries, next_attempt_at, can_retry, retry_in_seconds}}, purchasing_available}` | - | My plan and payment state |
| `POST /v1/billing/checkout` | verified | `kind: "pro"` or `"addon"` | `{url}` | 409 `already_pro`, 402 `payment_required` (add-on while payment outstanding), 503 `payments_not_configured`, 502 `provider_error` | Gives a Stripe Checkout URL |
| `POST /v1/billing/portal` | auth | - | `{url}` | 404 `no_billing_account` | Stripe customer portal URL |
| `POST /v1/billing/retry-payment` | auth | - | `{result, subscription}` | 409 `nothing_to_retry`, 429 `retry_too_soon`, 402 `payment_failed` | Retry failed invoice. Access restored only if Stripe confirms |
| `POST /v1/subscription/cancel` | auth | - | `{subscription}` | 409 `nothing_to_cancel` | Cancel at period end |
| `POST /v1/subscription/resume` | auth | - | `{subscription}` | 409 `nothing_to_resume` | Undo cancel |
| `GET /v1/billing/payment-method` | auth | - | `{available, payment_method}` | - | Card brand/last4 from Stripe |
| `GET /v1/billing/payments` | auth | - | `{available, payments[]}` up to 100 | - | Payment history |
| `GET /v1/billing/details` | auth | - | `{details}` | - | Invoice name/address |
| `PUT /v1/billing/details` | auth | `name, company, address, country (2 letters), tax_id` | `{details}` | 422 | Save invoice details |
| `POST /v1/billing/webhook` | Stripe signature header (no JWT) | raw Stripe event | 200 | 400 bad signature | Stripe tells us what happened |

Webhook events handled: `checkout.session.completed`, `invoice.paid`, `invoice.payment_failed`, `customer.subscription.updated`, `customer.subscription.deleted`. Signature is HMAC-SHA256, 300 s tolerance, each `event_id` processed once (`provider_events`).

**Payment states**: `active` -> (payment fails) `past_due` (paid access kept, but a running recording is never extended) -> after configured retries `restricted` (falls back to free Basic; account and transcripts kept) -> or `canceled`.

**Not run against real Stripe yet.** Only tested with a fake provider.

### 2.5 Transcript sessions and sharing (`routers/sessions.py`)

All owner-only: another user's session gives 404 (not 403), so existence is not leaked.

| Method + path | Auth | Success | Errors | What it does |
|---|---|---|---|---|
| `GET /v1/sessions?limit=` (1-200) | auth | `{sessions[]}` | - | My transcript list |
| `GET /v1/sessions/{id}` | auth | session + `transcript` (list of final texts) | 404 | One transcript |
| `PATCH /v1/sessions/{id}` body `{title}` | auth | session | 404 | Rename |
| `DELETE /v1/sessions/{id}` | auth | 204 | 404 | Delete transcript text. Usage records are kept (billing history stays) |
| `POST /v1/sessions/{id}/share` | verified | session with `share_url` = `APP_URL/s/<token>` | 404, 403 | Turn on public link (128-bit token) |
| `DELETE /v1/sessions/{id}/share` | auth | session | 404 | Turn off link. A turned-off token never works again |
| `GET /v1/shared/{token}` | **none** | `{session_id, title, live, started_at, ended_at, transcript, app_links{deep_link, android_store, ios_store}}` | 404 `not_found` | Public read-only view. Leaks no email or user id. Only GET allowed |

### 2.6 Usage endpoints (`routers/usage_routes.py`, prefix `/v1/usage`)

| Method + path | Auth | Returns |
|---|---|---|
| `GET /v1/usage` | auth | Plan, included minutes, used seconds, remaining, % used, add-ons, reset date, warnings, `restricted`, `cancel_at_period_end` |
| `GET /v1/usage/sessions?limit=` | auth | Per session: metered, included, add-on, unbilled-overshoot seconds |
| `GET /v1/usage/sessions/{id}/minutes` | auth | Minute-by-minute breakdown of one session (404 for someone else's) |

### 2.7 Internal endpoints for the relay (`routers/internal.py`, prefix `/internal/v1`)

Only the relay calls these. Header `X-Relay-Secret` must match `SCRIPTLIV_RELAY_SECRET` (constant-time compare; if the secret is unset the endpoints are closed, 403 `forbidden`).

| Method + path | Body | Returns | What it does |
|---|---|---|---|
| `POST /internal/v1/sessions/start` | `token` (the user's JWT), `session_id` (6-64 chars) | `{allowed, reason, remaining_seconds, user_id}` | Checks JWT, rejects unverified (`email_not_verified`), rejects a session id owned by someone else (`session_taken`), asks `usage.authorize` for a reservation, creates the `sessions` row |
| `POST /internal/v1/usage` | `user_id, session_id, cumulative_seconds, final` | allowed + remaining | Records seconds (idempotent, cumulative: repeating never double-bills), re-authorizes mid-session, sets `ended_at` when final. 409 `session_owner_mismatch` if the session is not that user's |

**Known gap**: these live on the same public port as the rest. Needs a network restriction before production.

---

## 3. How minutes are counted (`usage.py`, `subscriptions.py`)

1. Relay calls **start**. API checks plan + add-ons + personal limit and reserves the allowance in `usage_sessions`.
2. While audio flows, the relay takes audio from the allowance **chunk by chunk, before the engine sees it**.
3. Every ~10 s (`SCRIPTLIV_REPORT_EVERY_SECONDS`) and at the end, the relay calls **usage** with the running total.
4. **Strict limit**: when allowance hits zero, the audio is cut at the exact sample and the socket closes with 4402. No grace. Anything past the limit is stored as "unbilled overshoot".
5. Order of spending: included minutes first, then add-ons.
6. Only one live stream can hold the reserved allowance at a time: a second concurrent speaker gets `allowance_reserved`. Same session id on a new socket takes over the old one (4409).
7. Warnings appear at the user's `warn_percents` (default thresholds) and at 100%.

---

## 4. Relay (port 8772) — the live audio WebSocket

Connect: `ws://host:8772/?role=speaker&session=<session_id>&token=<JWT>`
Viewers: `ws://host:8772/?role=viewer&session=<session_id or access code>`

### 4.1 What a speaker does
1. Connect with the JWT.
2. Send **binary** audio: 16 kHz, mono, 16-bit PCM, little-endian (the web uses an AudioWorklet; the phone sends PCM16).
3. Receive **JSON text** messages back.

### 4.2 Messages from relay
```json
{"text": "hello wor", "partial": true}      // new words to append to the current sentence
{"text": "hello world.", "partial": false}  // the finished sentence
{"type": "error", "code": "out_of_minutes", "message": "..."}
```
A "refine" message may follow a final when Nemotron has cleaned a sentence; stored text is updated too.

### 4.3 Close codes (what the client must understand)

| Code | Reason | Meaning |
|---|---|---|
| 1000 | normal | Finished, or the 4-hour max session length reached |
| 1011 | `asr_connection_lost` | The speech engine connection died; reconnect |
| 1013 | `server_busy` | More than `STT_MAX_ACTIVE_STREAMS` (default 3) speakers; refused **before** billing, nothing charged |
| 4400 | malformed | Bad access code or session id |
| 4401 | invalid token | Bad/expired JWT |
| 4402 | `out_of_minutes` / `personal_limit` / `allowance_reserved` / `payment_required` | Billing says stop |
| 4403 | `email_not_verified` | Account not verified |
| 4409 | `superseded` | Same session id started on another socket |

### 4.4 Inside the relay
- `parakeet_relay.py`: accepts sockets, role routing, concurrency gate, calls billing, starts the session loop.
- `core/billing.py`: `BillingContext` — asks API to authorize, takes seconds per chunk, reports usage. Switched on only when `SCRIPTLIV_API_URL` and `SCRIPTLIV_RELAY_SECRET` are set.
- `core/streaming_session.py`: the speaker loop. Sends audio to the worker immediately, ends a sentence on the model's end-of-utterance or after 0.5 s of silence, holds a half-formed last word for 0.25 s, writes numbers as digits.
- `core/session_manager.py`: who is speaking and who is viewing a session; broadcasts to viewers.
- `core/transcript_store.py` + `core/mongo_mirror.py`: every final is saved (local SQLite) and mirrored into Mongo `transcript_events`.
- `core/refiner.py`: queues finished sentences + their audio for Nemotron.
- `engines/streaming_worker_engine.py`: the relay-side client to the ASR worker. The older whisper.cpp engine (`parakeet_engine.py`) is kept but unused.

### 4.5 Relay settings (env)
`STT_LISTEN_PORT`, `STT_ENGINE`, `STT_ASR_WORKER_URL`, `STT_REFINE_ENGINE`, `STT_REFINE_WORKER_URL`, `STT_MAX_ACTIVE_STREAMS`, `STT_MAX_TOTAL_CONNECTIONS`, `STT_MAX_VIEWERS_PER_SESSION`, `STT_SESSION_MAX_DURATION_SECONDS` (default 4 h), `STT_STREAM_ENDPOINT_SECONDS` (0.5), `STT_STREAM_TAIL_HOLD_SECONDS` (0.25), `STT_STREAM_MAX_UTTERANCE_SECONDS` (25), `STT_SILENCE_RMS_THRESHOLD`, `SCRIPTLIV_API_URL`, `SCRIPTLIV_RELAY_SECRET`, `SCRIPTLIV_REPORT_EVERY_SECONDS`, `MONGODB_URI`.

---

## 5. ASR workers (`asr_worker/stream_worker.py`)

- One Python process per model, WebSocket on `127.0.0.1` only (not reachable from outside).
- EOU on 8780 (Parakeet EOU 120M, live text + end-of-utterance), Nemotron on 8781 (0.6B, refinement).
- Runs on the GPU with NeMo. Capacity on this machine: **about 3 simultaneous live streams** per worker. More needs more workers/GPUs and routing.
- Keepalive pings are off on these loopback sockets (they caused false disconnects under load).

---

## 6. Database (MongoDB Atlas, db `scriptliv_staging`)

MongoDB has **collections** (like tables) holding **documents** (like rows). It has no enforced foreign keys: a "relation" here is a plain text field that holds another document's id. The code keeps those links correct.

### 6.1 The map (who points to whom)

```
users (_id)  <-- the center. Every other collection points back to the user id.
  |
  |-- user_id --> subscriptions      1 per user (plan, period, payment state)
  |-- user_id --> addons             0..many (extra minute packs)
  |-- user_id --> settings           0..1
  |-- user_id --> billing_details    0..1
  |-- user_id --> payments           0..many
  |-- user_id --> email_tokens       0..many (verify / reset / change links)
  |-- user_id --> email_deliveries   0..many (mail send log)
  |-- user_id --> usage_sessions     0..many (one per recording, billing side)
  |-- user_id --> usage_ledger       0..many (every second taken, with its source)
  |-- owner_id -> sessions           0..many (one per recording, transcript side)
  `-- _id (as text) --> usage_locks  short lock per user

sessions.session_id == usage_sessions.session_id == transcript_events.session_id == usage_minutes.session_id
    (the recording id is the glue between billing, transcript and minute rows)

addons._id   <--  usage_ledger.addon_id    (which add-on pack paid for those seconds)
payments._id <--  addons.payment_id        (which payment bought the pack)
subscriptions.provider_customer_id  <--  Stripe webhook events (found by this id)
provider_events.event_id == Stripe event id (dedupe only, no link)
```

Two ids to keep apart:
- `users._id` is a MongoDB ObjectId. Other collections store it as **text** (`user_id` / `owner_id`).
- `session_id` is a text id made by the app (6-64 chars, e.g. `sess_ab12...`). It is the same string in the relay, the API and the web/phone URL.

### 6.2 Collection details

**`users`** — one per account. Created by register.
Fields: `_id`, `name`, `email` (lower case), `email_verified` (false until the link is opened), `pwhash`, `pwv` (password version, in every JWT), `created_at`, `disabled`, `pending_email` (only while an email change waits for its link).
Index: `email` unique. Used by login, register, verify, reset.

**`subscriptions`** — exactly one per user (made right after register as free Basic).
Fields: `user_id`, `plan` (`basic`/`pro`), `status` (`active`/`past_due`/`restricted`/`canceled`), `anchor`, `period_start`, `period_end`, `included_used_seconds` (seconds spent this period), `cancel_at_period_end`, `provider` (`stripe` or null), `provider_customer_id`, `provider_subscription_id`, `created_at`, and payment-failure fields `payment_failed_count`, `last_payment_failed_at`, `next_payment_attempt_at`, `payment_state_at` (time of the newest Stripe event applied; older events never override it).
The period rolls forward automatically when read after `period_end` (usage resets).
Indexes: `user_id` unique; `provider_customer_id`, `provider_subscription_id` sparse (webhook lookups).

**`addons`** — one document per bought pack (1,000 min, $10).
Fields: `user_id`, `seconds_total` (60,000), `seconds_used`, `purchased_at`, `expires_at` (= end of the period it was bought in), `payment_id`.
Index: `(user_id, expires_at)`. Spent after the included minutes, oldest expiry first.

**`usage_sessions`** — billing record of one recording. Also the **reservation** that stops two streams sharing one allowance.
Fields: `session_id`, `user_id`, `started_at`, `ended_at` (null while live), `metered_seconds` (total audio seen), `included_seconds`, `addon_seconds`, `unbilled_overshoot_seconds`, `last_report_at`, `grant_seconds` (how much was reserved).
Indexes: `session_id` unique; `(user_id, ended_at, last_report_at)` (find open reservations); `(user_id, started_at)`.
Rule: `included_seconds + addon_seconds + unbilled_overshoot_seconds = metered_seconds`.

**`usage_minutes`** — one row per minute of a recording, for the per-minute breakdown.
Index: `(session_id, minute)` unique. Link: `session_id`.

**`usage_ledger`** — append-only list of every chunk of seconds taken and from where.
Fields: `user_id`, `session_id`, `seconds`, `source` (`included` / `addon` / `unbilled_overshoot`), `addon_id` (text id, only for `addon`), `period_start`, `ts`.
Index: `(user_id, period_start)`.

**`usage_locks`** — a tiny lock so two requests for one user cannot reserve at the same instant.
Fields: `_id` = user id text, `until` (lock expiry, 5 s). Only index is `_id`. Stale locks just have `until` in the past.

**`sessions`** — the transcript session the user sees in History.
Fields: `session_id`, `owner_id` (user id text), `title` (null until renamed), `started_at`, `ended_at`, `created_at`, `shared_at`, `share_token` (present only while sharing is on; removed on unshare), `access_code` (written by the relay mirror, used for viewer connections).
Indexes: `session_id` unique; `owner_id`; `share_token` unique sparse.
Two writers: the API (`/internal/v1/sessions/start`, rename, share) and the relay mirror. Both upsert on `session_id`, so it stays one document.

**`transcript_events`** — the sentences.
Fields: `session_id`, `seq` (0,1,2... order), `text`, `created_at`. A Nemotron refinement overwrites `text` of an existing row (matched by `session_id`, `seq` and the old text).
Index: `(session_id, seq)` unique. Written by the relay mirror. The API only reads it, and deletes it when a user deletes a session.

**`settings`** — per-user preferences. Document: `user_id` plus `theme`, `language`, `prevent_auto_lock`, `usage_warnings`, `warn_percents`, `personal_limit_minutes`. Missing keys fall back to defaults (`system`, `en`, true, true, `[80, 95]`, null). Index: `user_id` (unique when old data allows).

**`billing_details`** — invoice info. Document: `user_id`, `details{name, company, address, country, tax_id}`. Index: `user_id` unique.

**`payments`** — payment history, written only from Stripe webhooks.
Fields: `user_id`, `created_at`, `description`, `amount_cents`, `currency`, `status` (`paid` / `failed`), `provider_ref` (Stripe id; failed attempts use `failed:<invoice id>`), `receipt_url`.
Indexes: `(user_id, created_at)`; `provider_ref` unique (partial, strings only) so a payment can never be stored twice.

**`provider_events`** — Stripe event ids already handled. Fields: `event_id`, `type`, `at`. Index: `event_id` unique. If processing fails, the row is deleted so the Stripe retry gets processed.

**`email_tokens`** — mailed links.
Fields: `token_hash` (SHA-256; the real token is never stored), `user_id`, `kind` (`verify` / `reset` / `change`), `email` (address the link was sent to), `created_at`, `expires_at`, `expires_dt` (a real date for the cleanup index), `used`.
Indexes: `token_hash` unique; `expires_dt` with automatic delete one day after expiry; `(user_id, kind, used)`.

**`email_deliveries`** — log of every mail attempt. Fields: `user_id`, `kind`, `to_domain` (domain only, no full address), `provider`, `message_id`, `status`, `attempts`, `error`, `ts`. Index: `(user_id, ts)`.

### 6.3 Two stores for transcripts
The relay first writes finals to a local SQLite file (`relays_phase7c/data/transcripts.db`, tables `sessions` and `transcript_events`), then a background thread mirrors them into Mongo `sessions` / `transcript_events`. A Mongo outage does not stop recording; the mirror retries. The API and the apps read Mongo only.

### 6.4 What happens to data on common actions

| Action | What changes |
|---|---|
| Register | insert `users`; insert `subscriptions` (Basic); insert `email_tokens` (+ `email_deliveries`) |
| Verify email | `email_tokens.used = true`; `users.email_verified = true` |
| Change password / reset | `users.pwhash` updated, `pwv` +1 (all older JWTs die) |
| Start recording | `usage_sessions` created or reopened (reservation); `sessions` upserted with `owner_id` |
| While recording | relay mirror writes `transcript_events`; `usage_sessions` counters grow; `usage_ledger` and `usage_minutes` rows added; `subscriptions.included_used_seconds` and `addons.seconds_used` grow |
| End of recording | `usage_sessions.ended_at` and `sessions.ended_at` set (reservation released) |
| Delete a transcript | `transcript_events` and `sessions` rows removed; `usage_sessions`, `usage_minutes`, `usage_ledger` **kept** (billing history stays correct) |
| Share on / off | `sessions.share_token` and `shared_at` set / removed |
| Pro paid (webhook) | `subscriptions` set to Pro, period reset; `payments` row; `provider_events` row |
| Add-on paid | `addons` row; `payments` row |
| Payment fails | `subscriptions.status` becomes `past_due` or `restricted`; `payments` row with status `failed` |
| Period ends | `subscriptions.included_used_seconds` back to 0 when next read; expired `addons` stop counting |

### 6.5 Notes
- No document stores a plain password, a plain email token, or a card number. Cards live only at Stripe.
- All audited queries use an index (checked with `explain()`). Staging data is tiny; nothing is tested at production volume.
- Deleting a user account is not implemented (no endpoint), so there is no cascade rule yet. A retention/deletion policy is a production to-do.
- Backups and retention are Atlas settings, not set up by this project yet.

---

## 7. Email (`email_service.py`, `email_providers.py`, `mailer.py`)

- Token logic (make, hash, consume) is separate from delivery.
- Provider chosen by recipient domain: Gmail API (OAuth2, send-only) by default; Resend for `outlook.com, hotmail.com, live.com, msn.com` (list in `EMAIL_RESEND_DOMAINS`); SMTP as a third option.
- **All three are mock-tested only. No real email sent yet.**
- Staging switch `SCRIPTLIV_DEV_RETURN_TOKENS=1` puts the token in the API reply so the web shows an "Open the verification link" shortcut. **Must be off wherever real mail is used.**

---

## 8. API settings (env, `config.py`; all in the root `.env` template)

| Variable | Meaning |
|---|---|
| `MONGODB_URI`, `SCRIPTLIV_DB` | Database (default db `scriptliv_staging`) |
| `SCRIPTLIV_JWT_SECRET` | Signs tokens |
| `SCRIPTLIV_TOKEN_TTL_SECONDS` | Token life (default 7 days) |
| `SCRIPTLIV_RELAY_SECRET` | Shared with relay for `/internal` |
| `SCRIPTLIV_APP_URL` | Base for share links and email links (default http://localhost:3100) |
| `SCRIPTLIV_API_URL` | (relay side) where the API is |
| `SCRIPTLIV_CORS_ORIGINS` | Allowed web origins (never `*`) |
| `SCRIPTLIV_DEV_RETURN_TOKENS` | Staging only |
| `SCRIPTLIV_ENABLE_DOCS` | Turns on API docs; off by default |
| `SCRIPTLIV_ANDROID_STORE_URL`, `SCRIPTLIV_IOS_STORE_URL` | Store links in shared view |
| `SCRIPTLIV_PAYMENT_MAX_RETRIES` (3), `SCRIPTLIV_PAYMENT_RETRY_DAYS` ("1,3,5"), `SCRIPTLIV_PAYMENT_FINAL_STATUS` ("restricted"), `SCRIPTLIV_PAYMENT_RETRY_COOLDOWN` (60 s) | Payment failure flow |
| `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRO_PRICE_ID`, `STRIPE_ADDON_PRICE_ID` | Stripe (empty now) |
| `GMAIL_CLIENT_ID/SECRET/REFRESH_TOKEN/SENDER`, `RESEND_API_KEY`, `RESEND_FROM`, `SMTP_HOST`... | Email providers (empty now) |

---

## 9. Who calls what (backend side)

| Caller | Calls |
|---|---|
| Web + phone app | All `/v1/*` public/auth endpoints, plus the relay WebSocket |
| Relay | `/internal/v1/sessions/start`, `/internal/v1/usage` |
| Stripe | `/v1/billing/webhook` |
| Anyone with a link | `/v1/shared/{token}` |
| API | MongoDB, Stripe API, email providers |
| Relay | ASR workers, MongoDB (mirror) |

---

## 10. Security in short

Tested: JWT alg-none / wrong secret / expired / wrong type rejected; disabled accounts dead; login does not reveal which part was wrong; users cannot touch each other's sessions, usage, settings, billing; the relay cannot bill or hijack another user's session; shared view leaks nothing private; relay secret compare is constant-time; CORS not wildcard; API docs off by default; no stack traces in errors.
Open: `/internal/*` on public port; throttles in memory; no pen test; no dependency scan; dummy staging secrets by decision.

---

## 11. Run and test

- API: `python run_staging.py` in `scriptliv_api` (reads `staging_secrets/api.env`).
- Relay: `python benchmarks/results/phase7d/start_platform_relay.py` from repo root (set `STT_MAX_ACTIVE_STREAMS` first for another cap).
- ASR workers: from `asr_worker` with `asr_venv`, `stream_worker.py --port 8780` / `8781`.
- Tests: `python -m pytest -q -p no:warnings` in `scriptliv_api` (113 pass) and `relays_phase7c` (187 pass, 1 skipped).
