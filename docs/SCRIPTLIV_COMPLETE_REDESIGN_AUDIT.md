# ScriptLiv Redesign — Repo Audit (Phase A)

## Repos and locations
| Area | Path | Git |
|---|---|---|
| Backend (staging) | `relays_phase7c/` | yes, branch `redesign-staging` (commits `89b7be2`, `6598942`) |
| Flutter app | `st_transcribe_app/` | yes, branch `reliability-refactor` (has unrelated uncommitted `relays/` changes) |
| Website (new) | `scriptliv_web/` | **no** — `speech-to-text/` root is not a git repo |
| Branding | `assets/branding/` (installed into Flutter `assets/branding/`) | no |
| References | `stt/logo_ref`, `stt/img_ref` | n/a |

## Backend findings
- Parakeet is the only ASR engine; model, decoder, VAD, segmentation, scheduler untouched.
- Phase 7D QA layer already provides: allowlist (max 3), scrypt hashes, HMAC bearer tokens, consent `qa-consent-v1`, AES-256-GCM audio at rest, audit table, admin routes `/qa/admin/*` gated by `STT_QA_ADMINS`, signed 60 s audio link `/qa/sessions/<id>/audio-link`.
- Permissions are enforced server-side. The UI only hides controls as a convenience.
- WebSocket: `?role=speaker&session=<id>&token=<t>`; 16 kHz mono PCM16 in, JSON `{text, partial}` out; close codes 4401/4403 are terminal.

## Flutter findings (before redesign)
- Plaintext test accounts in `auth_service.dart`, shown nowhere in UI (test enforces this) but still in source for non-QA builds.
- No design system, no QA API client, no history from backend, no real mic level, no onboarding.

## Website findings
- Did not exist. Built from scratch (Next 15.5.4, React 19, Tailwind v4).

## Risks found
- No TLS on staging; token travels in the WS query string.
- Audio key lives on the relay host.
- Staging passwords were printed once into tool output during this work, and `passwords.txt` exists. Rotate before wider use.
- Flutter SDK here (3.44.6 / Dart 3.12.2) is older than the pubspec needs (`^3.13.7`), so the app cannot be built in this environment.
