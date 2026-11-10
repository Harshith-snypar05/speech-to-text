# ScriptLiv API Integration

No hardcoded backend URLs. No mock APIs. The dedicated QA endpoints, tester allowlist, QA consent, QA audio archive and
QA admin pages were removed; every account is a normal customer account on the platform API.

## Configuration
| Client | Setting | Kind |
|---|---|---|
| Web | `SL_BACKEND_HTTP` (Next rewrites `/sl/*` to the platform API) | build/run env |
| Web | `NEXT_PUBLIC_WS_URL` (browser connects to the relay directly) | **build-time** |
| Flutter | `--dart-define=SL_API_HTTP=http://HOST:8790` | build-time |
| Flutter | `--dart-define=SL_WS=ws://HOST:8772` | build-time |

## Typed clients
- Web: `scriptliv_web/lib/api.ts`, `live-client.ts`, `types.ts`. Token in `sessionStorage`.
- Flutter: `lib/services/platform_api.dart`, `lib/services/auth_service.dart` (token kept by the platform session), `lib/config/app_config.dart`.

## Endpoints used
- `/v1/auth/*` register (no token returned; verify email first), login (403 `email_not_verified` until verified), resend-verification, verify-email, forgot-password, reset-password; `/v1/me`, `/v1/usage`, `/v1/subscription`, `/v1/sessions`, share links, billing.
- WebSocket `?role=speaker&session=<id>&token=<t>`: binary 16 kHz mono PCM16 up; `{text, partial}` JSON down.
  Close codes: 4401 not allowed, 4402 out of minutes / allowance held / payment required, 4403 email not verified,
  4409 superseded by a newer connection for the same session. 4401/4402/4403 are terminal (no retry).

## Not provided
- No TLS on staging; token in WS query string.
