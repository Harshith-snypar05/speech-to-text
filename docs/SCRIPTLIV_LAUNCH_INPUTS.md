# ScriptLiv: launch inputs

Answers to the six launch questions. Section A is taken from the repository and can be relied on. Section B needs a decision or a fact from the business owner, so every line there is marked **TO CONFIRM** and nothing is guessed.

Prepared 2026-11-16 from branch `reliability-refactor`.

---

## A. Answered from the repository

### 3. Brand assets

| Item | Status | Where |
|---|---|---|
| Domain | `scriptliv.com` is live (HTTP 200 on 2026-11-16) | n/a |
| Logo and app icon (vector) | Available | `scriptliv_web/public/brand/scriptliv-app-icon.svg`, `scriptliv-app-icon-square.svg` |
| Web icons | Available | `scriptliv_web/public/icon-192.png`, `icon-512.png`, `apple-touch-icon.png` |
| Device mockups (laptop, phone) | Available | `scriptliv_web/public/brand/device-laptop.webp`, `device-phone.webp` |
| Android app screenshots | 11 shots (home, transcripts, transcript detail, settings, recording, onboarding, login, viewer join, shared view) | `docs/manual/app/` and `docs/screenshots/android/` |
| Web app screenshots | 15 shots (landing, register, login, dashboard, record, history, transcript, plans, settings, mobile dashboard, shared view, terms, privacy) | `docs/manual/web/` |
| iOS screenshots | None. iOS is untested | `docs/screenshots/ios/README.md` |
| Demo video | None found | n/a |
| Architecture diagram | Available | `docs/architecture/scriptliv-architecture.png` |

**Colours** (`docs/SCRIPTLIV_DESIGN_SYSTEM.md`)

| Role | Hex |
|---|---|
| Primary | `#6A00FF` |
| Secondary | `#A855F7` |
| Accent | `#E9D5FF` |
| Background | `#F8F7FF` |
| Text | `#0F172A` |

The invoice email uses a purple gradient in the same family.

### 5. Other documents

All are in the repository and can be shared as they are.

| Document | Path |
|---|---|
| Technical and Business Document | `docs/ScriptLiv_Technical_Business_Document.docx` |
| Technical Due Diligence and Handover | `docs/ScriptLiv_Technical_Due_Diligence_and_Handover.docx` |
| Knowledge Transfer (KT) document | `docs/ScriptLiv_KT_Document.docx` |
| App user manual | `docs/manual/ScriptLiv_App_User_Manual.docx` |
| Web user manual | `docs/manual/ScriptLiv_Web_User_Manual.docx` |
| STT Performance and Infrastructure Report | `STT_Performance_Infrastructure_Report.pdf` (repository root) |
| Release readiness, QA, platform, frontend, backend notes | `docs/SCRIPTLIV_*.md` |

`docs/ref/` holds files from an unrelated LMS project (Shiksha Setu). Do not send those with launch material.

### 1. Market evidence in the product (not a decision)

The product is built for **India first**:
- Prices are in rupees, with 18% GST added on top (`scriptliv_api/app/plans.py`).
- Payments run through Cashfree, an Indian payment provider.
- Invoices show GST and are issued by Snypar Tech.
- Language support is **English only** for now (`docs/SCRIPTLIV_PLATFORM.md`).

Nothing in the code supports Canada or the US: no dollar pricing is shown, no sales-tax handling, no regional data setup. A legacy USD field exists in the plan data but is unused.

### Product facts for launch copy

- **What it does:** live speech-to-text. A speaker records on the Android app or the web app and sees words appear as they speak. Anyone with a share link can watch the transcript live, read-only. An optional access code protects a session.
- **Also included:** transcript history, accounts with email verification, an admin area, and a Settings area (account, membership, payment history, theme, text size, microphone, help, cancel membership, delete account).
- **Platforms:** Android and web. iOS is untested.
- **Speech engine:** NVIDIA Parakeet, run on our own servers. Measured against Whisper variants in earlier testing and kept for better accuracy and speed (see the performance report).

**Plans**

| Plan | Price | Minutes | Per-session limit |
|---|---|---|---|
| Basic | Free | 300 per month | 30 minutes |
| Pro | ₹999 per month + 18% GST (₹1,178.82 charged) | 2,500 per month | 2 hours |
| Add-on | ₹499 + 18% GST | 1,000 extra minutes, valid until the plan period ends | 2 hours |

Paused sessions use no minutes: minutes are counted from audio received.

### 6. Competitors: what the repository says

No competitor is named anywhere in the repository. The only comparison work is internal, between speech engines (see the performance report). A competitor review (for example Otter, Google Live Transcribe, Rev) has not been done and would be new research.

---

## B. Needs the business owner

**TO CONFIRM** means a person must fill it in. These facts are not in the code or the docs.

### 1. Target customers

- First customer group: **TO CONFIRM** (students, journalists, people with hearing loss, meeting-heavy professionals, churches and events, or businesses buying for a team).
- First market: **TO CONFIRM** (India only, or also Canada and the US). If Canada or the US is in scope, the product needs dollar pricing, sales-tax handling and a payment route that accepts those cards. None exists today.

### 2. Launch timing and budget

- Target launch date: **TO CONFIRM**
- Marketing budget: **TO CONFIRM** (even "organic only" is a useful answer)

Any date depends on the readiness items in section C.

### 4. Accounts

| Item | Status |
|---|---|
| Google Play developer account | **TO CONFIRM** |
| Social handles for ScriptLiv | **TO CONFIRM** |
| Launch under Snypar Technologies Private Limited | **TO CONFIRM**. The invoice currently says "Snypar Tech". A company name and GST registration number will be needed on invoices. |
| Support email | `info@scriptliv.com` is used in the invoice footer. **TO CONFIRM** that the mailbox exists and is monitored. |

### 6. Competitors

Competitors already looked at: **TO CONFIRM**. The rest can be researched on request.

---

## C. What stands between today and a public launch

From the production audit of 2026-11-16. The verdict was: **ready for staging and demo, not for production.**

Must be done before launch:
1. Production hosting with HTTPS, container and CI setup. None exists; only the local `start_all.sh` script and `Caddyfile`.
2. Redeploy the demo server. It lacks account deletion, the feedback form and the invoice email.
3. Go live on Cashfree. Payments are sandbox only, and the real checkout and webhook signature have never been verified.
4. Confirm that transactional email (verification and invoices) reaches real inboxes and does not land in spam. Check SPF and DKIM for the sending domain.
5. Legal review of the Terms and Privacy pages (currently an unreviewed draft) and a data retention policy.
6. Monitoring, alerting, backups, error tracking and a support channel.
7. Security: a penetration test, a dependency vulnerability scan, and a stronger login throttle (the current one resets on restart and is per email only).
8. A health check that tests the database (the current `/healthz` always returns OK).

Smaller fixes:
- One failing API test (`test_pro_has_no_session_cap`).
- The Flutter `sdk: ^3.13.7` line in `pubspec.yaml` stops the app building on the local Dart 3.12.2. Loosening it to `^3.12.0` makes all tests pass.
- iOS has not been tested.
- The faster speech models (EOU 120M and Nemotron 0.6B) are code-only and not deployed.
- A demo video does not exist.
