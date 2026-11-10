# ScriptLiv — Frontend guide (simple language)

What the user sees: the **web app** (`scriptliv_web`) and the **phone app** (`st_transcribe_app`, Flutter).
For each screen: what it is for, which backend endpoint it calls, and where each endpoint is used.
Endpoint details (inputs, outputs, errors) are in `SCRIPTLIV_BACKEND.md`.

---

## 1. Settings that point the frontends to the backend

| Frontend | Setting | Meaning |
|---|---|---|
| Web | `NEXT_PUBLIC_SL_API_BASE` | API address, e.g. `http://localhost:8790` (`lib/config.ts`) |
| Web | `NEXT_PUBLIC_WS_URL` | Relay address, e.g. `ws://localhost:8772`. Empty = record page shows "Live transcription is not configured" |
| Phone | `--dart-define=SL_API_HTTP=http://HOST:8790` | API address (`config/app_config.dart`). Empty = non-platform mode |
| Phone | `--dart-define=SL_WS=ws://HOST:8772` | Relay address |

Web must be rebuilt (`npx next build`) and restarted after a source change; `NEXT_PUBLIC_*` values are baked in at build time.

---

# PART A — Web app (Next.js, port 3100)

## A1. Shared building blocks

| File | Job |
|---|---|
| `lib/api.ts` | The only place that talks HTTP to the API. Typed functions (table in A4). Failed calls throw `ApiError(status, code, message)` |
| `lib/auth.tsx` | Keeps the login token in the browser (it is **not** stored at register). `signIn`, `signUp`, `signOut`, loads `me` and settings after login, `saveSettings` |
| `lib/live-client.ts` | Records the mic (AudioWorklet, 16 kHz mono PCM16) and streams it to the relay WebSocket. Reconnects with the same session id (capped backoff). Says "live" only when mic AND socket are both up. Stops for good on close codes 4400-4403 and 4409 |
| `lib/transcript-parser.ts` | Turns relay messages (`partial` words, `final` sentence, refine) into the text on screen |
| `lib/config.ts` | Reads the two `NEXT_PUBLIC_*` values |
| `lib/types.ts`, `format.ts`, `utils.ts` | Types and small helpers (minutes, dates) |
| `components/ui/index.tsx` | Buttons, Notice, cards, inputs |
| `components/check-email.tsx` | "Check your email" panel: shows the address, Resend button, staging link, Sign in link |
| `components/payment-banner.tsx` | Banner when payment is past due / restricted, with Retry payment and Manage billing |
| `components/auth-shell.tsx`, `brand.tsx`, `waveform.tsx` | Layout, logo, audio bars |

## A2. Pages

### Public pages

| Route | File | What it is | Backend calls |
|---|---|---|---|
| `/` | `(marketing)/page.tsx` | Marketing home | none |
| `/register` | `register/page.tsx` | Sign up form. After success shows **Check your email** (never goes into the app) | `POST /v1/auth/register` |
| `/login` | `login/page.tsx` | Sign in. If the API says `email_not_verified` shows **Check your email** with "Back to sign in" | `POST /v1/auth/login`; Resend button (in `check-email`) -> `POST /v1/auth/resend-verification` |
| `/forgot-password` | `forgot-password/page.tsx` | Ask for a reset link | `POST /v1/auth/forgot-password` |
| `/reset-password?token=` | `reset-password/page.tsx` | Choose a new password | `POST /v1/auth/reset-password` |
| `/verify-email?token=` | `verify-email/page.tsx` | Opened from the email. On success says "Email confirmed", goes to `/login` after ~2 s (plus a Sign in button). Does not sign in | `POST /v1/auth/verify-email` |
| `/s/{token}` | `s/[token]/page.tsx` | Public shared transcript viewer (no account). Shows live while the session runs; has links to open the phone app | `GET /v1/shared/{token}` |

### Signed-in pages (`(app)/app/*`, guarded by `(app)/layout.tsx`: no token = redirect to login). Top bar has the logo and Settings beside it.

| Route | File | What it is | Backend calls |
|---|---|---|---|
| `/app` | `(app)/app/page.tsx` | Dashboard: usage card (plan, minutes used/left, reset date, warnings), recent usage | `GET /v1/usage`, `GET /v1/usage/sessions` |
| `/app/record` | `.../record/page.tsx` | Record live. Makes a new session id, asks mic permission, streams audio, shows partial/final text, timer, "Open in history" when stopped | **WebSocket** `NEXT_PUBLIC_WS_URL/?role=speaker&session=<id>&token=<JWT>` (see A3) |
| `/app/history` | `.../history/page.tsx` | List of saved transcripts | `GET /v1/sessions` |
| `/app/history/{id}` | `.../history/[id]/page.tsx` | One transcript: read, rename, share on/off with copyable link, delete | `GET /v1/sessions/{id}`, `PATCH /v1/sessions/{id}`, `POST /v1/sessions/{id}/share`, `DELETE /v1/sessions/{id}/share`, `DELETE /v1/sessions/{id}` |
| `/app/plans` | `.../plans/page.tsx` | Plans and add-on. Upgrade / Buy buttons. **Disabled right now** because `purchasing_available` is false (no Stripe keys) | `GET /v1/plans`, `GET /v1/subscription`, `GET /v1/usage`, `POST /v1/billing/checkout` |
| `/app/settings` | `.../settings/page.tsx` | Profile, email change, password, preferences, usage warnings and personal limit, billing section | see below |

Settings page calls, by section:

| Section | Calls |
|---|---|
| Name | `PATCH /v1/me` |
| Email change | `POST /v1/me/email`; if unverified, `POST /v1/me/email/resend` |
| Password | `POST /v1/me/password` (token in the browser is replaced by the new one) |
| Preferences (theme, language, keep awake, warnings, personal limit) | `GET /v1/settings`, `PUT /v1/settings` (through `lib/auth.tsx`) |
| Billing | `GET /v1/subscription`, `GET /v1/billing/payment-method`, `GET /v1/billing/payments`, `GET /v1/billing/details`, `PUT /v1/billing/details`, `POST /v1/billing/portal`, `POST /v1/subscription/cancel`, `POST /v1/subscription/resume` |

The payment banner (any signed-in page when payment is not healthy): `POST /v1/billing/retry-payment`, `POST /v1/billing/portal`.
On every app load: `GET /v1/me` and `GET /v1/settings` (`lib/auth.tsx`).

## A3. Record page and the relay

1. Page creates `sessionId` and a `LiveClient` with the user's token.
2. Connects to the relay. The relay asks the API to authorize (verified email, minutes left, no clash).
3. Mic audio goes up as binary frames. Text comes down as JSON: `partial` (append words), `final` (sentence), `refine`.
4. On close:
   - 4402: out of minutes / personal limit / allowance reserved / payment required, shown as a message. No reconnect.
   - 4403: email not verified. 4409: started elsewhere. 4401: sign in again. 4400: bad request. No reconnect.
   - 1011 / 1013 / network drop: treated as retryable; same session id is reused.
5. Stopping saves the transcript on the server; "Open in history" goes to `/app/history/{id}`.

No dedicated "server busy" screen yet for 1013.

## A4. Every API function in `lib/api.ts` and where it is used

| Function | Endpoint | Used in |
|---|---|---|
| `register` | `POST /v1/auth/register` | `lib/auth.tsx` (signUp) <- `/register` |
| `login` | `POST /v1/auth/login` | `lib/auth.tsx` (signIn) <- `/login` |
| `resendVerificationPublic` | `POST /v1/auth/resend-verification` | `components/check-email.tsx` (register, login) |
| `forgotPassword` | `POST /v1/auth/forgot-password` | `/forgot-password` |
| `resetPassword` | `POST /v1/auth/reset-password` | `/reset-password` |
| `verifyEmail` | `POST /v1/auth/verify-email` | `/verify-email` |
| `me` | `GET /v1/me` | `lib/auth.tsx` on load |
| `updateName` | `PATCH /v1/me` | Settings |
| `changeEmail` | `POST /v1/me/email` | Settings |
| `resendVerification` | `POST /v1/me/email/resend` | Settings |
| `changePassword` | `POST /v1/me/password` | Settings |
| `settings` / `saveSettings` | `GET` / `PUT /v1/settings` | `lib/auth.tsx`, Settings |
| `usage` | `GET /v1/usage` | Dashboard, Plans |
| `usageSessions` | `GET /v1/usage/sessions` | Dashboard |
| `plans` | `GET /v1/plans` | Plans |
| `subscription` | `GET /v1/subscription` | Plans, Settings |
| `checkout` | `POST /v1/billing/checkout` | Plans (Upgrade / Add-on) |
| `retryPayment` | `POST /v1/billing/retry-payment` | Payment banner |
| `portal` | `POST /v1/billing/portal` | Payment banner, Settings |
| `cancelPlan` / `resumePlan` | `POST /v1/subscription/cancel` / `resume` | Settings |
| `paymentMethod` | `GET /v1/billing/payment-method` | Settings |
| `payments` | `GET /v1/billing/payments` | Settings |
| `billingDetails` / `saveBillingDetails` | `GET` / `PUT /v1/billing/details` | Settings |
| `sessions` | `GET /v1/sessions` | History list |
| `session` | `GET /v1/sessions/{id}` | History detail |
| `renameSession` | `PATCH /v1/sessions/{id}` | History detail |
| `deleteSession` | `DELETE /v1/sessions/{id}` | History detail |
| `share` / `unshare` | `POST` / `DELETE /v1/sessions/{id}/share` | History detail |
| `shared` | `GET /v1/shared/{token}` | `/s/{token}` |

Not called by any frontend: `/healthz`, `/internal/v1/*` (relay only), `/v1/billing/webhook` (Stripe only).

## A5. Checks

`npx tsc --noEmit` clean, `npx eslint app components lib` clean, `npx vitest run` 10 pass, `npx next build` OK.

---

# PART B — Phone app (Flutter, Android; iOS untested)

## B1. Files that matter

| File | Job |
|---|---|
| `config/app_config.dart` | `SL_API_HTTP`, `SL_WS` build values; `platformMode` is true when the API address is set |
| `services/platform_api.dart` | The only HTTP client to the API. Throws `ApiException(status, code, message)`. Holds the token in `PlatformSession.token` |
| `services/auth_service.dart` | Login state. `login`, `register`, `resendVerification`, `logout`. `currentEmail` and `unverifiedEmail` notifiers drive the UI |
| `services/transcription_client.dart` | The speaker WebSocket to the relay: sends PCM16 audio, reads partial/final/refine. Maps close codes (4402, 4403, 4409, 4400/4401) to messages. Exposes `closeReason` |
| `services/viewer_client.dart` | Viewer WebSocket (watch someone else's live session) |
| `services/live_transcript_parser.dart` | Turns relay messages into text |
| `services/transcript_storage.dart` | Local transcript files (used outside platform mode and for export) |
| `services/app_settings.dart` | Local preferences, relay URL |
| `services/session_id.dart` | Makes a new session id and access code |
| `main.dart` | App start, theme, deep links: `https://.../s/<token>` and `scriptliv://s/<token>` open the shared-link screen |
| `widgets/brand.dart`, `st_logo.dart`, `waveform.dart`, `share_link_sheet.dart` | Logo, audio bars, share sheet |

## B2. Screens

| Screen | File | What it is | Backend calls |
|---|---|---|---|
| Splash | `splash_screen.dart` | Start-up | none |
| Auth gate | `auth_gate.dart` | Logged in -> app shell, otherwise login | restores session with `GET /v1/me` (in `AuthService`) |
| Login / Register | `login_screen.dart` | Sign in, sign up, forgot password. After register or an unverified login shows "Verify your email" with **Resend verification email** and **I have verified, sign in**. Password field is cleared | `POST /v1/auth/login`, `POST /v1/auth/register`, `POST /v1/auth/resend-verification`, `POST /v1/auth/forgot-password` |
| App shell | `app_shell.dart` | Top bar (logo + Settings), bottom tabs Home / Transcripts, centre mic button opens recording | none |
| Home | `home_screen.dart` | Usage card, recent items | `GET /v1/usage`, `GET /v1/sessions` (via `loadHistory`) |
| Recording | `session_screen.dart` | Live recording; makes a session id, connects with the JWT, shows partial/final text, share-link sheet, messages for 4402/4403/4409 and a payment banner | **WebSocket** `SL_WS/?role=speaker&session=<id>&token=<JWT>` |
| Transcripts | `history_screen.dart` | List of saved sessions | `GET /v1/sessions` |
| Transcript detail | `transcript_detail_screen.dart` | Read / export local transcript | local storage only |
| Platform session | `platform_session_screen.dart` | One account session: view, share on/off, delete | `GET /v1/sessions/{id}`, `POST` / `DELETE /v1/sessions/{id}/share`, `DELETE /v1/sessions/{id}` |
| Shared link | `platform_session_screen.dart` (shared view, from deep link) | Public view, no account needed | `GET /v1/shared/{token}` |
| Viewer | `viewer_screen.dart` | Watch a live session | **WebSocket** `?role=viewer&session=...` |
| Settings | `settings_screen.dart` | Account info, verify notice, preferences, sign out, copyright "Snypar Tech" | `GET /v1/me`; unverified: `POST /v1/me/email/resend`; logout is local |

## B3. Every `PlatformApi` call and where it is used

| Function | Endpoint | Used in |
|---|---|---|
| `login` | `POST /v1/auth/login` | `AuthService.login` <- login screen |
| `register` | `POST /v1/auth/register` (returns only the email, no token) | `AuthService.register` <- login screen |
| `resendVerificationFor(email)` | `POST /v1/auth/resend-verification` | `AuthService.resendVerification` <- login screen |
| `forgotPassword` | `POST /v1/auth/forgot-password` | login screen |
| `resendVerification()` | `POST /v1/me/email/resend` | Settings (signed in) |
| `me` | `GET /v1/me` | `AuthService` restore, Settings |
| `usage` | `GET /v1/usage` | Home |
| `sessions` | `GET /v1/sessions` | Home, Transcripts |
| `session(id)` | `GET /v1/sessions/{id}` | Platform session screen |
| `share(id)` / `unshare(id)` | `POST` / `DELETE /v1/sessions/{id}/share` | Platform session screen |
| `deleteSession(id)` | `DELETE /v1/sessions/{id}` | Platform session screen |
| `shared(token)` | `GET /v1/shared/{token}` | Shared-link screen (deep link) |

Phone app does **not** have: plans/checkout/billing screens, settings sync, rename, email/password change, or reset-password screen (reset is done on the web via the emailed link). Those are web-only today.

## B4. Close codes on the phone

| Code | Phone shows |
|---|---|
| 4402 | Out of minutes / personal limit / allowance reserved / payment required (with `closeReason`) |
| 4403 | Verify your email |
| 4409 | Session started on another device |
| 4400 / 4401 | Sign in again |
| 1011 / 1013 | Treated as retryable; no special "server busy" text yet |

## B5. Build and checks

- Flutter at `C:/flutter_3479`: `flutter analyze` (4 old infos), `flutter test` (59 pass).
- Debug build uses the `.staging` app id. **The APK on the phone is old (before verify-before-login); rebuild to see the new screens.**

---

# Quick cross-reference: endpoint -> who uses it

| Endpoint | Web | Phone |
|---|---|---|
| `POST /v1/auth/register` | register | login screen |
| `POST /v1/auth/login` | login | login screen |
| `POST /v1/auth/resend-verification` | check-email panel | login screen |
| `POST /v1/auth/verify-email` | verify-email page | (opens link in browser) |
| `POST /v1/auth/forgot-password` | forgot-password | login screen |
| `POST /v1/auth/reset-password` | reset-password | (web link) |
| `GET /v1/me` | auth bootstrap | restore session, Settings |
| `PATCH /v1/me` | Settings | - |
| `POST /v1/me/email`, `/email/resend` | Settings | resend only (Settings) |
| `POST /v1/me/password` | Settings | - |
| `GET`/`PUT /v1/settings` | auth bootstrap, Settings | - |
| `GET /v1/plans` | Plans | - |
| `GET /v1/subscription` | Plans, Settings | - |
| `POST /v1/billing/checkout` | Plans | - |
| `POST /v1/billing/portal`, `retry-payment` | Banner, Settings | - |
| `POST /v1/subscription/cancel`, `resume` | Settings | - |
| `GET /v1/billing/payment-method`, `payments`, `details`; `PUT details` | Settings | - |
| `GET /v1/usage` | Dashboard, Plans | Home |
| `GET /v1/usage/sessions` | Dashboard | - |
| `GET /v1/usage/sessions/{id}/minutes` | not used yet | not used yet |
| `GET /v1/sessions` | History | Home, Transcripts |
| `GET /v1/sessions/{id}` | History detail | Session screen |
| `PATCH /v1/sessions/{id}` | History detail | - |
| `DELETE /v1/sessions/{id}` | History detail | Session screen |
| `POST`/`DELETE /v1/sessions/{id}/share` | History detail | Session screen |
| `GET /v1/shared/{token}` | `/s/{token}` | Shared-link screen |
| Relay WebSocket (speaker) | Record page | Recording screen |
| Relay WebSocket (viewer) | - | Viewer screen |
| `/internal/v1/*` | - | - (relay only) |
| `/v1/billing/webhook` | - | - (Stripe only) |
