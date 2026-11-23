# Account deletion architecture

Code: `scriptliv_api/app/account_deletion.py` (lifecycle, cascade, recovery), `routers/account.py` (`DELETE /v1/me`),
`main.py` (recovery loop start/stop). Tests: `tests/test_account_deletion.py`, `tests/test_admin_delete_race.py`,
`tests/test_inflight_reconcile.py`; relay: `relays_phase7c/tests/test_relay_deletion_barrier.py`.
Relay and in-flight hardening: see [Phase 3](#phase-3-relay-and-in-flight-write-hardening).

Deleting an account is **tombstone first**. The user document is marked deleting *before* any related record is touched,
the mark never expires and never reverses, and the cascade can be resumed by anyone (the request, or the background
sweep) until it finishes. The user document is the last thing removed.

There is no separate jobs collection. The state lives on the user document, because every transition is then a single
conditional `update_one` on one document. The API uses a plain `MongoClient` (no replica set, no transactions), so
single-document atomicity is the only atomicity available, and this design needs nothing more.

## Lifecycle

| State | On the users document | Meaning |
|---|---|---|
| ACTIVE | none of the fields below | Normal account |
| CLAIMED | `delete_claim_token`, `delete_claim_until` (now + 60 s) | One request owns the right to try deleting. **Reversible**: the claim is released on any refusal and lapses on its own |
| DELETING | `deleting: true`, `deletion_token`, `deletion_started_at`, `deletion_done[]`, `deletion_attempts`, `deletion_last_error`, lease fields | Tombstoned. **Irreversible** and has no expiry. Cascade pending or running |
| DELETED | no document | Every stage done, then the user document removed |

```
ACTIVE --claim--> CLAIMED --verify admin safety--> --tombstone--> DELETING --cascade (all stages)--> DELETED
                    |  (last_admin / active_subscription / any refusal / expiry)
                    +--> ACTIVE (claim released)
```

### Atomic transitions

All are one conditional `update_one`; the filter is the guard.

1. **Claim** (`claim`) — filter: not `deleting` and no unexpired claim. Sets a fresh random token. Applies to **every**
   account, not only administrators. A second request finds a live claim and gets `409 delete_in_progress`.
2. **Release** (`release_claim`) — filter: the caller's token and not `deleting`. A request can only release its own claim,
   and cannot release anything once the tombstone exists.
3. **Tombstone** (`tombstone`) — filter: matching claim token, claim not expired (`delete_claim_until > now`), not
   `deleting`, same email as the snapshot taken at verification, and (when the snapshot was a non-admin) still not an
   administrator. It sets `deleting` and clears the claim fields in the same update. A forged or stale token, an expired
   claim, an already-deleted account or a changed identity matches nothing and the account stays ACTIVE.
4. **Cascade** (`run_deletion`) — see below. Needs the tombstone for the same token **and** the worker lease.
5. **Final delete** — one `delete_one` filtered on `deleting`, the token, the lease owner and
   `deletion_done ⊇ every stage`. If any part fails to match, nothing is deleted.

Nothing writes `deleting: false`, and nothing clears `deletion_token`. There is no code path from DELETING back to ACTIVE.
Login, token validation, password change, reset and verification all refuse a deleting account instead of touching it.

## Last-administrator protection

`DELETE /v1/me`: throttle, password check, then:

1. **Claim** the account.
2. **Re-read** the account fresh, filtered on our token and not deleting (`verify_admin_safety`). Its *current* admin
   identity is evaluated: the `is_admin` flag or an address in `SCRIPTLIV_ADMIN_EMAILS`. This is the point that closes the
   stale-admin race. The identity checked is the one stored now, not the one the request authenticated with.
3. If it is an administrator, `other_admin_exists` must find another **usable** administrator: enabled, not deleting, and
   not holding a live claim. Claimed, disabled and tombstoned administrators do not count. Otherwise the claim is released
   and the existing `409 last_admin` is returned.
4. The tombstone filter repeats the identity snapshot. An ordinary account promoted *between* the check and the tombstone
   is refused (`409 delete_conflict`) rather than deleted as an ordinary user.

Two administrators deleting at once each hold a claim, so neither counts the other as usable: both may be refused
(`last_admin`), never both succeeded. The refusal is conservative; the user can retry. Ordering of an expired claim,
promotion and demotion during a request are covered in the test file.

## What a deleting account is blocked from

Enforced in the API and the relay path, not in any frontend.

| Surface | Behaviour |
|---|---|
| `current_user` (every authenticated route, so settings, transcripts, shares, billing writes, usage, feedback, account update, password change) | 401 `invalid_token` |
| Login | 401 `bad_credentials`, identical to a wrong password |
| Token refresh | There is no refresh endpoint. Tokens are JWTs checked by `current_user` on every call, so an old token dies with the tombstone |
| Email verification, password reset | `400 invalid_token`; the update is itself filtered on `deleting != true` |
| Forgot password, resend verification | Skipped silently; no token issued |
| Relay `internal/v1/sessions/start` (new session and reconnect) | `allowed: false`, `invalid_token` |
| Relay `internal/v1/usage` | Writes nothing; `allowed: false`, `account_unavailable`. A non-final answer stops the relay session |
| `usage.authorize`, `usage.record`, `get_subscription` | Refuse / no-op; `get_subscription` does not create a Basic row |
| Shared transcript links `/v1/shared/{token}` | 404 |
| Admin `PATCH /v1/admin/users/{id}` on that account | 409 `account_deleting` |
| Provider webhooks (Cashfree and Stripe: payment, add-on, invoice paid/failed) | No write; ERROR log `billing_event_for_deleting_account` |
| Checkout, retry-payment, resume | Also refused while **CLAIMED** (409 `delete_in_progress`) |

A CLAIMED account is otherwise unblocked: the claim is reversible and short-lived, so locking the user out on a claim that
may be released would be worse than the window it closes.

Other accounts and ordinary admin operations are unaffected.

## Cascade

`STAGES`, in order: `transcript_events`, `sessions`, `usage_minutes`, `usage_sessions`, `usage_ledger`, `addons`,
`subscriptions`, `settings`, `billing_details`, `email_tokens`, `usage_locks`. This is the pre-existing set, unchanged.
Each stage is a keyed `delete_many`, so repeating it is harmless.

- A worker takes the **lease** (`deletion_lease_owner`, `deletion_lease_until` = now + 120 s) with a conditional update.
  Only one worker per account can hold it.
- Before every stage the lease is renewed; if the renewal does not match, the worker stops (`lease_lost`) and never
  touches the user document.
- After each stage the stage name is `$addToSet` into `deletion_done`. A resumed run skips recorded stages.
- Before the final delete, all stages run once more (final sweep) to catch a row written by a request that was already in
  flight when the tombstone landed.
- The run also refuses to start unless the tombstone for its token is present, independently of the lease.
- A failure at any point leaves the tombstone in place and releases the lease with a back-off
  (30 s doubling to 15 min, `deletion_last_error` set). **A failure never restores access.**
- `DELETE /v1/me` returns `{"deleted": true}` once the cascade finished, or `{"deleted": true, "pending": true}` if it
  did not. In the second case the account is already unusable and recovery completes the rest.

`subscriptions` stage: if a live, non-cancelled paid subscription is found (it appeared after the pre-tombstone check),
the stage still removes the local row and logs ERROR `deletion_live_subscription`. Nothing in this code contacts the payment
provider; that needs an operator.

## Crash recovery

Trigger:
- **Background sweep.** `main.py` lifespan starts `start_recovery_loop` on a daemon thread. Every
  `SCRIPTLIV_DELETION_RECOVERY_SECONDS` (default 60; `0` turns it off) it runs `recover_deletions`. The first sweep is one
  interval *after* start, so API startup is never delayed. Each sweep takes at most 10 tombstoned accounts, oldest first,
  that have no live lease. An exception in a sweep is logged (`deletion_recovery_error`) and the loop continues.
- **Manual.** `python -m app.account_deletion` runs one bounded sweep; `--status` prints pending accounts.

Properties: idempotent; needs no authentication of the deleted account; serialized per account by the lease so
several API processes can each run the loop without duplicating work; a crashed worker's lease lapses after 120 s and the
next sweep resumes from `deletion_done`.

Monitoring: `pending_deletions()` / `--status` reports `pending`, `oldest_age_seconds`, `failing` and the first 50 accounts
with `deletion_attempts` and `deletion_last_error`. **Alert on `pending > 0` for longer than a few sweep intervals, and on
any `failing`.**

Retry: automatic through the loop with the back-off above, with no attempt cap. A deletion that keeps failing is retried
forever at 15-minute spacing and is visible in the status output.

### Log events

`deletion_tombstoned`, `deletion_stage`, `deletion_completed`, `deletion_failed` (ERROR), `deletion_recovery`,
`deletion_recovery_error` (ERROR), `deletion_live_subscription` (ERROR), `billing_event_for_deleting_account` (ERROR).
Account ids are logged, not emails or names.

## Retention review: collections the cascade does not delete

Behaviour is **unchanged**; nothing was added to or removed from the cascade. These are findings for a policy decision.

| Collection | Personal data | Needed for audit or disputes | Delete / anonymize / retain | What breaks if removed |
|---|---|---|---|---|
| `payments` | `user_id`, amounts, status, `provider_ref`, receipt URL. No card data; no name or email stored here | **Yes.** Financial record, refunds and chargebacks, tax | **Retain.** Anonymizing `user_id` is possible later but needs the finance/legal retention period first. Do not delete | `provider_ref` unique partial index is what makes webhooks idempotent, and a re-delivered webhook would re-insert. `GET /v1/billing/payments`, invoice emails read it |
| `email_deliveries` | `user_id`, kind, `to_domain` (domain only, never the address), provider, status, message id | Marginal. Debugging delivery, no financial value | **Safe to retain**; low sensitivity. Safe to delete or to blank `user_id` after a retention window | Nothing reads it for behaviour. Only operator diagnostics |
| `feedback` | `user_id`, **`email`**, `title`, free-text `message` | No | **Needs a decision.** It holds the user's address and arbitrary text, so deletion or anonymizing is the privacy-preferred option. Kept today by design (documented in `SCRIPTLIV_BACKEND.md`) | Nothing reads it. Each item was also mailed to the support inbox, which this does not touch |
| `throttle` | Keys such as `acctdel:<uid>`, `login:<email>`; counters | No | **Retain**; expires on its own (TTL index on `expires_at`) | Deleting would only reset rate limits |
| `provider_events` (not in the original list) | Event ids only | No | Retain | Webhook de-duplication |

Approval is needed before deleting or anonymizing `payments`, `email_deliveries` or `feedback`.

## Phase 3: relay and in-flight write hardening

Phase 2 made the API refuse a tombstoned account. Two paths still wrote around it: the relay (which wrote Mongo directly) and
API requests that were already past their auth check when the tombstone landed. Phase 3 closes both without new
infrastructure and without transactions.

### A. Relay deletion barrier

The relay is a separate process and cannot be told to stop, so the barrier is enforced where it writes, and refuses when
unsure. It applies in **owned mode**: `SCRIPTLIV_API_URL` and `SCRIPTLIV_RELAY_SECRET` set (production). Without them the relay
keeps its old standalone behaviour, which has no accounts to protect.

| Safeguard | Where | Behaviour |
|---|---|---|
| New session | API `sessions/start` (+ relay `parakeet_relay.py`) | Tombstoned or unknown account gets `allowed: false`. The relay closes the socket 4401 before building any session. An allowed answer with no `user_id` is also closed (4401 `billing_unavailable`). An unreachable API refuses the connection (unchanged) |
| Reconnect | same endpoint | A reconnect is a new `start`, so it is re-checked |
| Mongo mirror | `core/mongo_mirror.py` | Before **every** write the owning account is read (`sessions.owner_id`, then `users._id` not `deleting`). Missing owner, missing or deleting user, or a DB error drops the write and blocks the session (fail closed) |
| No row creation | same | In owned mode the relay never creates a `sessions` row; `start`, `end` and `refine` are updates without upsert. Only the API's `sessions/start` creates it, and it records `owner_id` |
| Event race | same | An event upsert is: check, write, check again; if the second check fails the row is deleted again and the session blocked, so the cascade's final sweep and the relay cannot disagree |
| Local transcripts | `core/transcript_store.py` | When a session is blocked its SQLite rows are purged and every later write is a no-op (`record_event` returns `None`). Cleanup (`end_session`) after a block creates nothing |
| Live session | `core/billing.py` | A `/internal/v1/usage` denial with `account_unavailable` or `invalid_token`, a mirror block, or an unverifiable API stops the session (see below) |

**Maximum detection delay (account tombstoned while a session is live):**

| Path | Delay |
|---|---|
| Mongo writes (transcript events, session rows) | **None.** Each write is checked, per final utterance, with one indexed read of two documents |
| Audio / session stop via the next usage report | Up to `SCRIPTLIV_REPORT_EVERY_SECONDS` (10 s) of audio, plus the report request (6 s timeout) |
| Audio stop via a mirror block | The next chunk after the first refused write (an in-memory set lookup; **no DB query per chunk**) |
| API unreachable | Session stops after `SCRIPTLIV_UNVERIFIED_GRACE_SECONDS` (default 60 s) of failed reports, then up to one more interval |

Nothing is written for a deleting account in any of these windows; the delay is only how long audio is still processed.
Close code is **4401** (`account_unavailable`, `invalid_token`, `billing_unavailable`), which web (`TERMINAL_CLOSE`) and
Flutter already treat as terminal, so clients do not retry. Quota exhaustion keeps 4402.

**Behaviour change (flag for review):** previously a relay that could not reach the API mid-session kept serving
(fail open). It now stops after the 60 s grace (fail closed, requirement 8). The grace counts from the first failed report
and resets on any success, so a healthy API, a quiet speaker or one failed report never trips it. Set
`SCRIPTLIV_UNVERIFIED_GRACE_SECONDS` higher to tolerate longer API outages.

### B. Coordination between the cascade and the relay

- **Can active relay sessions be identified and terminated?** Not reliably from the API. `usage_sessions` rows with
  `ended_at: null` are only a hint (a crashed relay never closes its rows), and the API has no channel to the relay. So
  there is no "kill this session" call.
- **Is a tombstone notification needed?** No. The relay already learns through the per-write check and the usage report;
  both read the same user-document tombstone.
- **Does the relay acknowledge that sessions stopped?** No, and deletion does **not wait for one**. There is no relay
  ack, no timeout to tune, and no indefinite wait. The cascade proceeds as soon as it holds the tombstone.
- **Relay unavailable during deletion:** nothing to write, nothing to wait for, the cascade completes. If the relay
  comes back later it is refused (`start` is `invalid_token`; its mirror drops writes for a missing or deleting owner).
- **Relay not updated or not restarted:** the barrier does not exist. Deploy and restart the relay **before or together with**
  the API (API first is also safe: the old relay then behaves as it did after Phase 2). The API must be reachable for owned mode.
- **Bounded reconciliation pass:** the cascade already ends with a final sweep of every stage. With the relay barrier the
  relay can no longer add rows after it, so no extra pass is added.

### C. In-flight API writes

A request that passed its guard just before the tombstone can finish one write. The compensating sweep
`account_deletion.reconcile_after_write(db, uid, missing_is_gone=True)` is called straight **after** such a write: if the
account is now tombstoned (or gone) it deletes the account's keyed rows with the same idempotent deletes as the cascade stages
and the caller refuses. It needs no transaction: the cascade only starts after the tombstone, so either the check runs before
the tombstone (the write predates it, so the cascade and its final sweep remove the row) or after it (the sweep removes the
row). Residual: a process crash between the write and the check; the final sweep of the still-running cascade is the safety net.

| Operation | Can finish after tombstone? | Guard before write | Compensating sweep |
|---|---|---|---|
| `internal/sessions/start` (session row, reservation) | yes | `deleting` check | yes, returns `invalid_token` |
| `internal/usage` (usage rows, `ended_at`) | yes | `account_unavailable` | yes, returns `account_unavailable` |
| `PUT /v1/settings` | yes | `current_user` | yes, 401 `invalid_token` |
| `get_subscription` (creates Basic row) | yes | `is_deleting_uid` | yes (`missing_is_gone=False`) |
| `email_service.issue_token` | yes | callers check | yes (`missing_is_gone=False`) |
| Admin `PATCH /v1/admin/users/{id}` (plan, add-on) | yes | `deleting` check | yes, 409 `account_deleting` |
| Billing writes in `routers/billing.py` (billing details, checkout bookkeeping) | yes | `current_user` | **no** (billing code deliberately untouched) |

`missing_is_gone=False` treats only a real tombstone as gone, for callers that may hold an id with no user document.

### D. Billing and payments (inspected, not changed)

No billing, webhook, subscription, entitlement, pricing or provider code was changed in Phase 3. Findings:

- Webhooks for a deleting account are already skipped (Phase 2 guards), with ERROR `billing_event_for_deleting_account`.
- **Risk:** a payment captured at the provider while deletion runs gets no local `payments` row. The provider keeps its
  own record, and the ERROR log is the cue for manual reconciliation. Cashfree and Stripe reconciliation (and any
  provider-side cancel) needs a product and finance decision and is deferred.
- A paid subscription activated between the pre-tombstone check and the tombstone is still only logged
  (`deletion_live_subscription`).
- The 1,000-minute introductory offer is a separate product task and is not part of this work.

## Known limitations

1. **Relay protection needs the relay updated and restarted**, and the API reachable (owned mode). Until then relay writes
   behave as in Phase 2.
2. **Relay SQLite is never pruned.** `data/transcripts.db` on the relay host keeps transcripts of finished sessions
   indefinitely. Sessions blocked while live are purged, but transcripts of an account deleted *between* sessions persist
   there. Closing this needs a retention decision (purge by owner, or by age) and an owner field on that table. Not guessed.
3. **Process crash between a write and its sweep** can leave one row; the cascade's final sweep covers it if the cascade is
   still running, otherwise the row has no live owner and is only reachable by id.
4. **`routers/billing.py` writes** (billing details, checkout bookkeeping) have no compensating sweep because billing code was out of scope.
5. **Webhooks for a deleting account are skipped**, so a charge captured in that window has no local record (see D).
6. **A paid activation between the subscription check and the tombstone** is only logged; this code never contacts the provider.
7. **A claimed account is not write-blocked**, apart from starting a purchase.
8. **The recovery loop is per API process** and its first run is one interval after start. If no API process is running
   nothing recovers; run `python -m app.account_deletion` instead.
9. **The email address stays reserved** (unique index) until the user document is finally deleted.
10. **Concurrent last-admin deleters may both be refused** (conservative by design).
11. **A mid-session API outage now stops sessions** after the grace period (previously fail-open).
