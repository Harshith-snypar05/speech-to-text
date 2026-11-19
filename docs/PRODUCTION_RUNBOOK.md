# ScriptLiv production runbook

How to deploy, run and recover ScriptLiv. Written 2026-11-16. Items marked **OWNER** need an account, access or a person that is not in this repository; they are not done.

## 1. What runs where

| Part | How it runs | Public? |
|---|---|---|
| Caddy (HTTPS, certificates) | container, `deploy/docker-compose.yml` | yes, ports 80 and 443 |
| Web (Next.js, port 3100) | container | only through Caddy |
| API (FastAPI, port 8790) | container, bound to `127.0.0.1` | no. `/internal/*` is answered with 404 by Caddy |
| Relay (speech engine, port 8772) | on the host, not in a container. It needs the Parakeet model and the native whisper.cpp build | only the WebSocket path, through Caddy |
| Canary accuracy worker (port 8781) | on the host, next to the relay, own Python venv. Needs an NVIDIA GPU. See section 12 | no, loopback only |
| MongoDB | MongoDB Atlas | no |

## 2. First deploy

1. Provision a server (Linux, Docker, enough CPU/GPU for the relay) and point the DNS name at it. **OWNER**
2. `cp deploy/production.env.example deploy/production.env` and fill it in. Generate each secret with `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
   - `SCRIPTLIV_ENV=production` turns on the startup check. The API refuses to start if the JWT secret is under 32 characters, the relay secret is missing, the app URL or CORS origins are not `https://`, dev tokens or `/docs` are enabled, or Cashfree live mode is paired with a test key.
   - `SCRIPTLIV_CORS_ORIGINS` must list the public origin only. The default is localhost.
3. Start the relay on the host with `STT_LISTEN_PORT=8772`, `SCRIPTLIV_API_URL=http://127.0.0.1:8790`, and the same `SCRIPTLIV_RELAY_SECRET` as the API.
4. `docker compose -f deploy/docker-compose.yml --env-file deploy/production.env up -d --build`
5. Check: `curl https://<domain>/sl/healthz` returns `{"ok":true}` (it returns 503 if the database is unreachable). `curl -i https://<domain>/sl/internal/v1/x` must return 404.
6. Register an account, verify the email, record a short session, open the share link in a second browser.

The Docker files were written but **not built on the author's machine** (the Docker daemon was not running). The CI job `images` builds both, so the first CI run is the first real build. Fix anything it reports.

## 3. Continuous integration

`.github/workflows/ci.yml` runs on every push and pull request: API tests and `pip-audit`, relay tests, web typecheck, lint, tests, build and `npm audit`, Flutter analyze and tests, then the Docker builds. Make it a required check on `main`.

## 4. Going live on Cashfree (**OWNER**)

Everything so far ran against the Cashfree sandbox. The real checkout and the real webhook signature have never been exercised.

1. Complete Cashfree business KYC and get live approval.
2. Put the **live** App ID and secret in `production.env` and set `CASHFREE_LIVE=1`. The API refuses to start if live mode is paired with a test key.
3. In the Cashfree dashboard, set the live webhook URL to `https://<domain>/sl/v1/billing/webhook/cashfree` and keep the webhook secret private.
4. Create the live subscription plan with the id in `CASHFREE_PRO_PLAN_ID`.
5. Make one real payment of the smallest amount, confirm: the plan changes to Pro, the invoice email arrives, the payment shows in Settings, and a refund works. Do this before telling anyone.
6. Confirm the seller name, address and GST number on the invoice (`scriptliv_api/app/invoice.py` still says "Snypar Tech").

## 5. Email delivery (**OWNER**)

Mail goes through Resend for Microsoft domains and Gmail for the rest.
1. Verify the sending domain in Resend and publish SPF, DKIM and DMARC records. Check with an inbox test tool.
2. Send a verification mail and an invoice to a Gmail, an Outlook and a company inbox. Confirm none land in spam.
3. Confirm `info@scriptliv.com` exists and someone reads it. It is printed on every invoice.

## 6. Monitoring and alerting

- Uptime: point an external monitor (UptimeRobot, Better Stack, or similar) at `https://<domain>/sl/healthz` every minute. It fails when the database is down, not just when the process is. **OWNER** to create the account.
- Errors: add an error tracker (for example Sentry) to the API and web. Not done.
- Logs: `docker compose logs -f api web`. The API never logs secrets or tokens.
- Alert on: health check failing for 2 minutes, disk above 80% on the relay host, payment webhook failures (`payments` documents stuck in a non-final status), and email delivery failures (`email_deliveries` with `status` not `sent`).
- Support channel: `info@scriptliv.com`. **OWNER** decides who answers and how fast.

## 7. Backups

- MongoDB Atlas: turn on continuous cloud backup (point-in-time recovery) on the production cluster. Keep at least 7 days. **OWNER**
- Test a restore into a scratch cluster once before launch, and after any big schema change.
- Secrets: keep `production.env` in a password manager, not in the repository.
- The Caddy volume `caddy_data` holds the certificates. It is re-created automatically if lost.

## 8. Data retention policy (draft, needs legal review)

| Data | Kept | Then |
|---|---|---|
| Account (email, name, password hash) | while the account exists | deleted on `DELETE /v1/me` or the Settings "Delete account" action |
| Transcripts | until the user deletes them or the account | removed with the account |
| Audio | never stored. It is transcribed live and discarded | not applicable |
| Payment records | 8 years, as required for tax records in India (**OWNER** to confirm with the accountant) | kept even after account deletion, with personal details removed where the law allows |
| Invoice emails | in the user's inbox; delivery log kept in `email_deliveries` | review yearly |
| Login throttle entries | 5 to 60 minutes | removed by the database TTL index |
| Feedback | 2 years | delete on request |

Account deletion already removes the user's transcripts and sessions. The payment-record rule above needs a decision before launch.

## 9. Legal (**OWNER**)

The Terms and Privacy pages in the web app are an unreviewed draft. A lawyer must review them, and they must match section 8 and the real list of processors (MongoDB Atlas, Cashfree, Resend, Google, the hosting provider).

## 10. Security

Done in the repository:
- Login throttle moved into MongoDB. It survives restarts and works across several API processes. Per-IP limits added on register, login, resend verification and forgot password. The forwarded-IP header is trusted only when `SCRIPTLIV_TRUST_PROXY=1`, which compose sets because Caddy is in front.
- Startup refuses an unsafe production configuration.
- `/internal/*` blocked at the edge.
- Dependency audit: `pip-audit` on the API found nothing. `npm audit` found Next.js 15.5.4 with a critical advisory; upgraded to 15.5.29, now 0 vulnerabilities. Both audits run in CI.

Not done (**OWNER**):
- A penetration test by a person or a firm.
- A scan of the relay's dependencies (`relays_phase7c/requirements.txt`) and of the Flutter packages.
- Rate limits at the edge (Caddy or a CDN) for the WebSocket and public share endpoints.

## 11. Go-live checklist

- [ ] Server, DNS, HTTPS working
- [ ] `production.env` filled, API starts without the "Refusing to start" error
- [ ] Relay running, session transcribes end to end through the public URL
- [ ] `/internal/*` returns 404 from the internet
- [ ] Uptime monitor and error tracker live
- [ ] Atlas backups on, one restore tested
- [ ] Cashfree live keys, one real payment and refund tested
- [ ] Invoice and verification emails reach real inboxes
- [ ] Terms, Privacy and retention reviewed by a lawyer
- [ ] Penetration test done and findings fixed
- [ ] Android build tested on a clean device; iOS decision made (untested today)
- [ ] Demo server redeployed or retired
- [ ] If using the Canary pass: worker running, `STT_REFINE_ENGINE=canary` set, a test session shows lines being corrected

## 12. Accuracy pass: Parakeet live, Canary second pass

Parakeet TDT stays the live engine, so the words appear at once. Each finished line is then re-listened to by `nvidia/canary-qwen-2.5b`, and if the result is a safe correction the line is replaced in place on the web and in the app (a `refine` message). If the worker is down, slow or answers something odd, the live text simply stays. Nothing is lost.

- Worker: `asr_worker/canary_worker.py`, run from the repo root with a Python that has torch (CUDA), NeMo and peft (on the staging laptop that is the `asr_venv` next to the repo): `<venv>\Scripts\python.exe asr_worker\canary_worker.py --port 8781`. It binds to `127.0.0.1` only. First start downloads about 5 GB and loads in about 70 s.
- Relay switch: set `STT_REFINE_ENGINE=canary` (and optionally `STT_REFINE_WORKER_URL=ws://127.0.0.1:8781`, `STT_REFINE_LOG_FILE=<path>`) in the relay's environment. Unset means no second pass.
- GPU: about 5.2 GB of VRAM for Canary. Measured on an RTX 5050 8 GB: 1.1 s median per utterance, 2.7 s at the 95th percentile. Parakeet through the whisper.cpp build runs on CPU, so both fit on one 8 GB card. The second pass is one utterance at a time, so under heavy load the corrections lag behind but the live text never does.
- Limits: English only, about 40 s per clip (the worker cuts longer audio). It writes brand names it does not know phonetically (a test clip turned "Bisleri" into "pissillary"), which is why a change is accepted only when it keeps most of the live words.
- Measured: Canary alone scored 6.8% WER on 60 Indian-English clips (Svarah). Parakeet was not scored on the same clips, so the gain is not measured. This is not a promise for your audio.
- Check it: `STT_REFINE_LOG_FILE` gets one JSON line per utterance with `accepted` true or false and both texts.
- Tested end to end on 2026-11-17 against the real worker with a stand-in live engine. Not yet tested with the real Parakeet engine, a real microphone, or the Flutter app.

## 13. Inaugural offer (free, unlimited minutes)

Payments are postponed; everyone gets free, unlimited transcription from 2026-11-19 through 2026-11-30.

- Switch on: set `SCRIPTLIV_PROMO_UNLIMITED_UNTIL=YYYY-MM-DD` in the API environment and restart the API. The offer runs to the end of that day. Blank or past date means off, so it ends by itself.
- What changes: usage is still recorded (ledger, sessions, per-minute buckets) but nothing is taken from the plan or add-ons, so nobody reaches the end of the offer with minutes already spent. `/v1/usage` reports `unlimited: true` and a `promo` block; web and app show the offer instead of minute counts. `/v1/plans` reports `purchasing_available: false` and `promo_active: true`, and `POST /v1/billing/checkout` answers 409 `offer_active`.
- What still applies: 240 min per session, the account's own personal monthly limit, email verification, the relay's `STT_MAX_ACTIVE_STREAMS` and 4 h session cap. Unlimited is about minutes, not server capacity: with the GPU box the real limit is a few simultaneous speakers.
- Ending it: remove the variable (or let the date pass). Plans, add-ons and checkout come back with the same release; Cashfree live keys and KYC must be ready before then.

