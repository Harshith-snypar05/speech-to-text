# Phase 7D QA access audit

Enforced in the backend (`core/qa.py`, `core/qa_http.py`, `parakeet_relay.py`), not the frontend. QA layer is off unless `STT_QA_ENABLED=1`.

## Controls and live evidence (`phase7d_access.json`: 19/19 pass; 15 unit tests)
| Control | Result |
|---|---|
| Only 3 allowlisted accounts | config refuses more than 3; unknown email 401; validly signed token for non-listed email rejected (unit) |
| Credentials | scrypt hashes; fresh random passwords; lockout after 5 failures in 5 min (unit-tested, audited as `login_locked`; not run live) |
| Tokens | HMAC-signed, expiring; forged, expired, missing rejected (401) |
| WebSocket | no/bad token close 4401; no consent 4403; session id owned by another account 4403 |
| Data isolation | other account gets 404 on audio and transcript, same response as a nonexistent id; not in their listing; path traversal 404 |
| Encryption at rest | audio AES-256-GCM chunked, tamper detected (unit); transcript text encrypted; a transcript word searched in `qa.db` and the audio dir: 0 hits |
| Audit | live totals: audio_download 8 ok, audio_denied 5, transcript_read 7, transcript_denied 2, ws_denied 3, session_claim_denied 1, login ok 10 / fail 2, qa_access_denied 2, qa_not_found 1, consent_accept 10, list_sessions 3; admin CLI rows (`admin_sessions`, `admin_purge`, `admin_audit`) with actor `cli:sriha` |
| Retention/deletion | `purge_expired` (default 30 days, unit-tested incl. file removal) runs at relay start and via `qa_admin.py purge`; `qa_admin.py delete-account EMAIL` removes events and audio (audit rows kept, `session_deleted`). Live purge removed 0 sessions (none expired) |
| Consent | explicit, versioned (`qa-consent-v1`), required before any speaker session. In staging it was accepted programmatically, not by real testers |
| Admin access | server-side CLI only, no admin HTTP API; every action audited |

## Open risks
1. Real tester consent not collected. The 30-day retention is my proposal, not agreed. QA administrator role not named.
2. Audio key and token secret live in `staging_secrets/qa.env` on the relay host: host access means decryption. No KMS/rotation.
3. No TLS; token in WS query string (and `combined_proxy` logs paths); login is GET + Basic. Acceptable for localhost staging only. Flutter web would need CORS.
4. Audit table is not tamper-evident.
5. Legacy `transcripts.db` is plaintext, has no account column, and still records QA sessions. Viewer share links (public by design, optional access code) can read them, bypassing QA isolation. Decide whether QA builds must disable sharing.
6. Scheduler and flush-diag logs carry conn_id, not account or text; join via `qa_events`.
7. `staging_secrets/passwords.txt` still exists: hand out each line, then delete.
8. Old plaintext test accounts remain in `auth_service.dart` for non-QA builds (pre-existing).
