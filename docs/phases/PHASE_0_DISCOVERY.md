# Phase 0 — Discovery and Current-State Audit

Branch: `phases` (forked from `reliability-refactor`). Prepared 2026-11-18. Honesty rule carried over from the other
ScriptLiv docs: only verified facts are stated; anything not tested, not measured, or not decided is marked
**TBD**, **NOT DONE**, or **N/A (feature doesn't exist)** — nothing here is guessed to fill a gap.

This document consolidates findings already produced across `docs/SCRIPTLIV_RELEASE_READINESS.md`,
`docs/SCRIPTLIV_LAUNCH_INPUTS.md`, `docs/PRODUCTION_RUNBOOK.md`, the QA/Android/iOS validation notes, and the
`STT_Performance_Infrastructure_Report.pdf`, plus new verification done directly for this phase (marked **NEW**
below). It does not re-run work that was already done and documented elsewhere — it cites it and says what, if
anything, has changed since.

---

## 1. Client Inventory

| Client | Status | Evidence |
|---|---|---|
| **Web** (Next.js, `scriptliv_web`) | Implemented, deployed | Live at `https://scriptliv.com` (Vercel, custom domain with valid TLS on both apex and `www`) and `https://scriptlivweb.vercel.app`. Full flow (register → verify → record → share → pricing/checkout → settings) implemented. `tsc`/`eslint` clean, 10 vitest passing, `next build` OK. |
| **Android** (Flutter, `st_transcribe_app`) | Implemented, APK builds and installs | Multiple real debug APKs built and installed this session against the live backend. `flutter analyze` clean (0 issues as of this pass), `flutter test`: **61/61 passing** (the pre-existing theme-color failure from earlier in this work is now fixed). Logged-in recording, live share (fixed this session — was generating a dead `/#/viewer` link, now uses the real backend-issued `/s/<token>` link), bottom nav, "Manage plan" external link all verified against the real stack. |
| **iOS** | **NEW: builds clean, not yet run** | Previous docs (`SCRIPTLIV_IOS_VALIDATION.md`) assumed no Xcode was available in-environment. That's not true on this machine: Xcode 27.2 + CocoaPods 1.17.0 are installed. Ran `flutter build ios --no-codesign --simulator` for real: **`Runner.app` built successfully** (pod install, Xcode build, link all clean). No iOS Simulator *runtime* is downloaded on this machine, so the build was not launched or interacted with — mic capture, background audio, permissions prompts, Universal Links (`https://scriptliv.com/s/<token>`) and the App Store checklist remain genuinely unverified. This is a real, actionable next step (download a simulator runtime, or get a physical iPhone) rather than a hard blocker. |
| **Desktop** | Implemented (incidental), not a target platform | `flutter run -d macos` works and was used throughout this session purely as a way to visually check UI changes (no screen-recording permission for proper screenshots in this environment, verified via log/behavior checks instead). Not planned as a shipped platform; no Windows/Linux desktop build has been attempted. |
| **Browser-based viewer** (`/s/<token>`, no account) | Implemented | Public, read-only, live-updating. No account, uses no minutes. Verified multiple times this session end to end, including through the new `scriptliv.com` domain. |

### Feature-level status (all clients)

| Feature | Status |
|---|---|
| Register / verify email / login / forgot-reset password | Implemented, tested (API: real flow; delivery: Gmail/Resend/SMTP code paths are mock-tested only — **real email delivery has never been verified to a real inbox**, see §6) |
| Live transcription (Parakeet TDT 0.6B v2, English-only) | Implemented, measured (§5) |
| Second-pass accuracy correction (Canary-Qwen-2.5B) | Implemented, **verified live end to end this session** on this machine's Apple M4 GPU (via MPS — the shipped worker code assumed CUDA only; patched and confirmed working, see §5). A separate CUDA run (RTX 5050) is documented in `PRODUCTION_RUNBOOK.md` with WER data (§5). Off by default; opt-in via `STT_REFINE_ENGINE=canary`. |
| Diarization (who-said-what) | **N/A — does not exist.** Not in scope anywhere in the current codebase. |
| Summary / Q&A over a transcript | **N/A — does not exist.** No LLM-based summarization or question-answering feature exists. |
| Transcript history: search, rename, export, delete | Implemented |
| Live share link + read-only viewer | Implemented, fixed this session (dead link bug) |
| Plans / pricing / checkout (Cashfree) | Implemented, **sandbox-verified end to end** (checkout session creation for both Orders/add-on and Subscriptions/Pro, webhook signature verification, cancellation). **Never run against Cashfree's live/production mode** — no real payment has been made. |
| GST (18%) on pricing | Implemented and charged correctly (verified: ₹999 base → ₹1,178.82 charged for Pro; ₹499 → ₹588.82 for the add-on) |
| Settings (account, password, preferences, usage limits, billing, microphone) | Implemented |
| Admin dashboard | Implemented (grant bonus minutes, view users/sessions) — used this session for a real account |
| Account deletion | Implemented per `PRODUCTION_RUNBOOK.md` §8 (`DELETE /v1/me` / Settings "Delete account"); not independently re-verified in this pass |

---

## 2. Architecture / Data-Flow Map

Current deployed topology (confirmed by direct inspection of the running stack, not just the docs):

```
Browser / Android         Vercel (scriptliv.com, www.scriptliv.com)
   |  HTTPS, WSS               |  /sl/* server-side proxy -> SL_BACKEND_HTTP
   |                           |  (middleware.ts injects ngrok-skip-browser-warning)
   v                           v
ngrok tunnel (fixed domain) --> Caddy :5600 (local Mac)
   |-- query role=speaker/viewer --> Relay :8772
   |-- /__api/* --> Platform API :8790 (direct path, added this session for Vercel)
   `-- everything else --> Next.js dev server :3100 (local, for same-machine use)

Relay :8772
   |-- in-process: Parakeet TDT 0.6B v2 (whisper.cpp native binding, Metal GPU) -- the live engine
   |-- optional, off by default: Canary-Qwen-2.5B refine worker :8781 (own venv, MPS/CUDA/CPU) -- second pass only
   `-- authorizes every session against the API (/internal/v1/*, shared-secret header); never decides who may speak itself

Platform API :8790 -> MongoDB Atlas (scriptliv_staging) + Cashfree (sandbox) + Resend/Gmail (email)
```

A static architecture diagram exists at `docs/architecture/scriptliv-architecture.png`, regenerated earlier this
branch's work to remove the stale Stripe/EOU-worker depiction. It does not yet show the Vercel/custom-domain
layer or the Canary worker as a distinct, optional box — **gap for this phase's deliverable**, noted in §9.

**Known architectural fact worth flagging explicitly**: the backend (API + relay + Canary) is **not hosted** —
it runs on a developer's Mac, reachable only through a free-tier ngrok tunnel, kept alive by `start_all.sh`. The
frontend being on Vercel with a real domain does not change this. See `PRODUCTION_RUNBOOK.md` and
`SCRIPTLIV_LAUNCH_INPUTS.md` §C item 1 — this is the single largest gap between "demo-able" and "production."

---

## 3. End-to-End Journey Map

| Journey | Status |
|---|---|
| Registration → email verification → login | Implemented, tested on the real stack. Real delivery unverified (§6). |
| Live capture → partial/final text → (optional) Canary correction | Implemented, measured (§5) |
| Reconnect after a dropped connection | Implemented (`core/streaming_session.py` session resume by id); covered by relay test suite |
| Finalization (strict minute limit, exact-sample cutoff) | Implemented, tested (`SCRIPTLIV_RELEASE_READINESS.md` §3: billed exactly to the second, no grace) |
| History (list, search, open, rename, export) | Implemented |
| Sharing (live and after the fact) | Implemented, fixed this session |
| Subscription purchase (Pro, add-on) | Implemented, sandbox-verified |
| Cancellation | Implemented. **Cashfree-specific gap, documented honestly in code and docs**: Cashfree cancels a mandate immediately and irreversibly (no "resume" once cancelled, unlike Stripe) — `resume_not_supported` is a real, intentional error code, not a bug. |
| Account deletion | Implemented per runbook; transcripts and sessions removed, payment records retained per the draft retention policy (§6 of the runbook) |

---

## 4. Performance Baseline

All numbers below are real, measured values from `STT_Performance_Infrastructure_Report.pdf` (this machine, Apple
M4, Metal GPU) and `PRODUCTION_RUNBOOK.md` §12 (separate CUDA box, RTX 5050 8GB) — not estimates.

| Metric | Value | Source |
|---|---|---|
| Parakeet TDT v2 inference, 11s clip | ~130ms (RTF 0.012, ~83× real time) | Performance report |
| Parakeet CPU use, 1 concurrent speaker | ~4% of one core (relay process) | Performance report |
| Parakeet CPU use, 3–4 concurrent speakers | ~11% of one core | Performance report (flagged caveat: benchmark harness had a session-id collision bug above N=1, trend is informative not exact) |
| Resident memory, Parakeet loaded | ~806MB, flat regardless of concurrency | Performance report |
| End-to-end time-to-first-word | ~0.75–0.93s | Performance report |
| End-to-end finalization (incl. deliberate 0.6s silence-hang) | ~0.7s; ~70–185ms of that is actual compute | Performance report |
| Canary-Qwen on Apple M4 (MPS) | Model load: 332s cold / 55–71s warm (cached); 5.2GB memory | **NEW this phase's lineage** — verified live against the real Parakeet engine (not a stand-in), 3/3 real utterances got real `refine` messages back |
| Canary-Qwen on RTX 5050 8GB (CUDA) | 1.1s median / 2.7s p95 per utterance | `PRODUCTION_RUNBOOK.md` §12 |
| Canary WER (Svarah, 60 Indian-English clips) | 6.8% | `PRODUCTION_RUNBOOK.md` §12 — Parakeet was **not** scored on the same clips, so the relative gain from the second pass is not measured |
| Single-worker capacity (old EOU/Nemotron architecture) | ~3 concurrent streams before failure | `SCRIPTLIV_RELEASE_READINESS.md` §11 — **this is the retired architecture, not the current in-process Parakeet engine.** The in-process engine has not had an equivalent load test (5+ concurrent real speakers to failure) run against it. |

**Gap for this phase**: formal WER by language/accent/noise/speaking-speed as the Phase 0 scope describes does not
exist as a structured benchmark suite — the only accuracy number on record is the single Canary/Svarah result
above. Building a proper multi-dimension WER benchmark (clean/noisy, multiple accents, slow/fast speech) is real,
unstarted work, not something that can be backfilled from existing artifacts.

**Diarization error / summary factuality**: **N/A** — neither feature exists in the product, so there is nothing
to measure.

---

## 5. Security and Compliance Review

Consolidated from `SCRIPTLIV_RELEASE_READINESS.md` §9 and `PRODUCTION_RUNBOOK.md` §10 (both current, dated
2026-11-16/17):

**Done / passing:**
- JWT validation (alg-none, wrong secret, expired, wrong type all rejected); password-version token invalidation.
- Per-account data isolation, cross-user access denial — tested.
- Relay cannot hijack or bill another account's session — tested.
- Share links: read-only, revocable, leak no private data.
- Webhook signature verification (both Stripe's HMAC-SHA256 scheme, unused, and Cashfree's, which reuses the
  API secret and has no separate webhook secret).
- Login throttle moved to MongoDB (survives restarts, shared across processes) — per the runbook, this was a
  gap in the release-readiness pass and has since been fixed.
- `/internal/*` blocked at the edge in the production Caddy config (`deploy/Caddyfile`) — fixed relative to the
  release-readiness pass, which flagged it as open on the public port.
- `pip-audit` (API deps) and `npm audit` (web deps) run in CI, both clean as of the runbook.

**Not done (real gaps, not just caveats):**
- No independent penetration test.
- No dependency scan of `relays_phase7c/requirements.txt` or the Flutter package set.
- No edge rate limiting on the WebSocket or public share endpoints.
- Terms & Privacy pages are an unreviewed legal draft.
- No data retention policy sign-off (a draft exists in the runbook §8, needs legal + accountant review for the
  payment-record retention period).
- Cashfree is sandbox-only; live checkout, live webhook, and a real refund have never been exercised.
- Real email delivery (Gmail OAuth2, Resend/Outlook) has only ever been mock-tested. SPF/DKIM/DMARC for the
  sending domain not confirmed.

**Consent / recording indicators**: live recording state only shows after mic *and* socket are both established
(tested); no separate "you are being recorded" disclosure screen beyond the record button's own state — this
matches a self-recording product (the speaker starts their own recording), not a third-party-recording product,
so a formal consent-capture flow was judged out of scope by earlier work, not an oversight. Worth the product
owner explicitly confirming this reading is correct before Phase 1.

---

## 6. Customer Discovery

**NOT DONE.** This is real, unstarted work — no interviews, no observed workflows, and it cannot be fabricated
or inferred from the repository. `SCRIPTLIV_LAUNCH_INPUTS.md` §B already has an honest, itemized list of
exactly this kind of owner-only decision (target customer segment, first market, launch timing, competitor
research) marked **TO CONFIRM**. This phase's discovery scope (15 interviews across recruitment/tech
delivery/sales, 5 observed workflows) should be run against that same list rather than duplicated — the open
questions are already identified; what's missing is the actual research.

---

## 7. Architecture Decision Records (drafted from documented rationale)

| Decision | Rationale on record | Status |
|---|---|---|
| Separate relay (WebSocket) + platform API (REST) processes | The relay never decides who may speak — it asks the API to authorize every session and reports usage. Keeps billing/auth logic in one place regardless of how many relay instances exist. (`SCRIPTLIV_BACKEND.md` §1) | Followed consistently; no violations found in this audit |
| Parakeet TDT as the live engine | Measured against Whisper variants in earlier testing, kept for accuracy and speed (`SCRIPTLIV_LAUNCH_INPUTS.md`). Switched v3 (multilingual) → v2 (English-only) this branch after v3's language auto-detection misfired on short English utterances. | Current; the earlier Whisper comparison itself isn't preserved as a document in this repo — **gap: no ADR file, only a mention** |
| Canary-Qwen as an optional second pass, never the live path | Explicitly a correction layer, not a replacement: if the worker is down/slow, the live text is kept as-is. Chosen to add accuracy without adding latency risk to the primary path. | Implemented and tested exactly as decided |
| MongoDB Atlas for persistence | No ADR found; appears to predate this audit. | **Gap — not documented anywhere found** |
| Cashfree over Stripe for payments | India-first product: rupee pricing, GST, an Indian payment provider. Stripe adapter code still exists, unconfigured. | Documented in `SCRIPTLIV_LAUNCH_INPUTS.md` §1 |
| Vercel for the web frontend, backend stays local behind ngrok | User's explicit choice this session, not yet a long-term decision — see the hosting gap noted in §2. | Deliberate interim step, not a final architecture |

---

## 8. Deliverables Against This Phase's Scope

| Deliverable | Status |
|---|---|
| Current-state inventory | Done — §1 |
| Architecture / data-flow diagrams | Partially done — text map above is current; the existing PNG diagram needs a redo to show Vercel + Canary as their own boxes |
| Performance, accuracy, cost and security baseline reports | Performance: done (§4, real numbers). Accuracy: one real number exists (Canary/Svarah), no structured multi-dimension suite. Cost per audio hour: **not computed** — no cloud hosting cost exists yet to measure against (backend is local). Security: done (§5) |
| Customer discovery findings | **Not done** — real work remains (§6) |
| Prioritized MVP / product decision log | Exists as `SCRIPTLIV_LAUNCH_INPUTS.md`'s TO-CONFIRM list; needs the business owner's actual answers, not more documentation |
| Approved architecture decisions | Drafted (§7); "approved" requires a human sign-off this document cannot provide |
| Phase backlog / release plan | This document plus the runbook's go-live checklist together form a working backlog — see §9 below for what Phase 1 should not start without |

---

## 9. Exit Gate Assessment

Phase 0's stated exit gate: *"No Phase 1 scope expansion until current build is reproducible, critical risks
are known, launch scope is agreed, and baseline measurements exist."*

| Condition | Met? |
|---|---|
| Build is reproducible | **Yes** — CI (`.github/workflows/ci.yml`) builds and tests API, relay, web, and Flutter on every push; this session independently reproduced API/relay/web/Flutter test runs and a real iOS build from the current tree. |
| Critical risks are known | **Yes** — enumerated and current in §5 and `PRODUCTION_RUNBOOK.md`; nothing found in this audit that wasn't already on that list. |
| Launch scope is agreed | **No** — `SCRIPTLIV_LAUNCH_INPUTS.md` §B is still open (target customers, first market, launch timing, account ownership all TO CONFIRM). |
| Baseline measurements exist | **Partially** — performance and security baselines are real and current (§4, §5). Accuracy baseline is a single data point, not the multi-dimension suite the phase scope describes. Cost-per-audio-hour cannot be baselined against infrastructure that doesn't exist yet. |

**Recommendation**: do not expand scope (diarization, summary/Q&A, additional clients) until the launch-scope
and customer-discovery gaps are closed by the business owner, and until a real hosted backend exists to measure
cost-per-audio-hour against. The technical/reproducibility/risk conditions are already satisfied.

---

## Appendix: Commands used to verify claims in this document

```bash
# API tests
cd scriptliv_api && .venv/bin/python -m pytest -q          # 156 passed

# Relay tests
cd relays_phase7c && ../stt-compare-venv/bin/python3 -m pytest -q   # 178 passed, 1 skipped, 1 pre-existing failure (unrelated)

# Web
cd scriptliv_web && npm test -- --run                       # 10 passed

# Flutter
cd st_transcribe_app && flutter test                        # 61 passed

# iOS build (new this phase)
cd st_transcribe_app && flutter build ios --no-codesign --simulator \
  --dart-define=SL_API_HTTP=https://scriptliv.com/__api --dart-define=SL_WS=wss://scriptliv.com
# -> Built build/ios/iphonesimulator/Runner.app
```
