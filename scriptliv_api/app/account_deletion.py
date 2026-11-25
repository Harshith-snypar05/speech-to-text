"""Tombstone-first account deletion.

Lifecycle (all state lives on the account's own users document; there is no separate jobs collection):

    ACTIVE    no deletion fields, or an expired claim
    CLAIMED   delete_claim_token + delete_claim_until (short, never renewed). Reversible: it expires or is released.
    DELETING  deleting=True + deletion_token. The tombstone. Irreversible, never expires, nothing here clears it.
    DELETED   the users document is gone (it is always the last thing removed).

    claim -> re-read + last-admin check -> subscription check -> tombstone -> idempotent cascade -> delete users document

Every transition is ONE conditional update_one on the users document, so it needs no transaction and no waiting lock.
The cascade is resumable: each finished stage is recorded on the document, a worker must hold an expiring lease to run it,
and `recover_deletions` re-drives anything a crashed process left behind. See docs/architecture/ACCOUNT_DELETION.md.
"""
import logging
import secrets
import socket
import os

from bson import ObjectId

from .deps import is_admin_account, now, other_admin_exists

log = logging.getLogger("scriptliv.deletion")

CLAIM_SECONDS = 60          # a claim only has to outlive the few queries between claim and tombstone; it is never renewed
LEASE_SECONDS = 120         # one worker's exclusive right to run the cascade; renewed before every stage
BACKOFF_BASE_SECONDS = 30   # after a failed attempt the account is not retried before base * 2^(attempts-1) ...
BACKOFF_MAX_SECONDS = 900   # ... capped here
RECOVERY_BATCH = 10         # accounts one recovery sweep may touch


def _delete_transcripts(db, uid):
    ids = [s["session_id"] for s in db.sessions.find({"owner_id": uid}, {"session_id": 1})]
    if ids:
        db.transcript_events.delete_many({"session_id": {"$in": ids}})


def _delete_sessions(db, uid):
    db.sessions.delete_many({"owner_id": uid})


def _delete_usage_minutes(db, uid):
    ids = [s["session_id"] for s in db.usage_sessions.find({"user_id": uid}, {"session_id": 1})]
    if ids:
        db.usage_minutes.delete_many({"session_id": {"$in": ids}})


def _by_user(coll):
    def run(db, uid):
        db[coll].delete_many({"user_id": uid})
    return run


def _delete_subscription(db, uid):
    sub = db.subscriptions.find_one({"user_id": uid}) or {}
    if sub.get("plan", "basic") != "basic" and not sub.get("cancel_at_period_end"):
        # Only reachable if a provider webhook activated Pro between the subscription check and the tombstone. Nothing here
        # may talk to a payment provider (billing policy is unchanged), so surface it for an operator.
        log.error("deletion_live_subscription uid=%s provider=%s provider_subscription_id=%s",
                  uid, sub.get("provider"), sub.get("provider_subscription_id"))
    db.subscriptions.delete_many({"user_id": uid})


def _delete_usage_lock(db, uid):
    db.usage_locks.delete_many({"_id": uid})


# Order matters only where a later stage derives its ids from an earlier collection that is still present
# (transcripts and usage_minutes are found through sessions / usage_sessions, so they go first). Each stage is a plain
# delete_many keyed by the account, hence safe to run any number of times. The users document is NOT a stage: it is removed
# last, and only after every stage is recorded as done.
STAGES = [
    ("transcript_events", _delete_transcripts),
    ("sessions", _delete_sessions),
    ("usage_minutes", _delete_usage_minutes),
    ("usage_sessions", _by_user("usage_sessions")),
    ("usage_ledger", _by_user("usage_ledger")),
    ("addons", _by_user("addons")),
    ("subscriptions", _delete_subscription),
    ("settings", _by_user("settings")),
    ("billing_details", _by_user("billing_details")),
    ("email_tokens", _by_user("email_tokens")),
    ("usage_locks", _delete_usage_lock),
]


# ---- state checks used by the write barriers ---------------------------------------------------------------------------

def is_deleting(user: dict | None) -> bool:
    """True for a tombstoned account. This is the single predicate every barrier uses."""
    return bool(user) and bool(user.get("deleting"))


def claim_active(user: dict | None, t: float | None = None) -> bool:
    return bool(user) and (user.get("delete_claim_until") or 0) > (t if t is not None else now())


def deletion_in_flight(user: dict | None) -> bool:
    """Claimed or tombstoned. Used to refuse actions that would start something an imminent deletion cannot undo (a purchase)."""
    return is_deleting(user) or claim_active(user)


def is_deleting_uid(db, uid) -> bool:
    """For callers that only hold an id (provider webhooks, relay reports). An id that is not an ObjectId is not an account."""
    try:
        oid = ObjectId(str(uid))
    except Exception:
        return False
    return db.users.find_one({"_id": oid, "deleting": True}, {"_id": 1}) is not None


def account_unavailable(db, uid) -> bool:
    """Tombstoned, or already deleted (the document is gone). Nothing may be written for such an account."""
    try:
        oid = ObjectId(str(uid))
    except Exception:
        return True
    u = db.users.find_one({"_id": oid}, {"deleting": 1})
    return u is None or bool(u.get("deleting"))


def reconcile_after_write(db, uid, missing_is_gone: bool = True) -> bool:
    """Compensating check for a write that passed its guard BEFORE the tombstone landed.

    Call it straight AFTER such a write. If the account is tombstoned (or, with `missing_is_gone`, already deleted), every
    keyed account record is deleted again (the same idempotent deletes as the cascade stages, no bookkeeping) and True is
    returned so the caller can refuse. Why this closes the race: the cascade only starts after the tombstone, so either this
    check runs before the tombstone (the write predates it and the cascade, including its final sweep, removes the row) or
    after it (this sweep removes the row). No transaction is needed. If the process dies between the write and this check,
    the final sweep of a still-running cascade is the remaining safety net.
    `missing_is_gone=False` treats only a tombstone as "gone" (for callers that may legitimately hold an id with no user
    document, such as tests and relay-only identities)."""
    gone = account_unavailable(db, uid) if missing_is_gone else is_deleting_uid(db, uid)
    if not gone:
        return False
    for name, fn in STAGES:
        try:
            fn(db, str(uid))
        except Exception as e:   # best effort: the cascade (or its recovery) still owns the final guarantee
            log.error("deletion_inflight_sweep_failed uid=%s stage=%s error=%s", uid, name, type(e).__name__)
    log.warning("deletion_inflight_write_swept uid=%s", uid)
    return True


# ---- transitions -------------------------------------------------------------------------------------------------------

def claim(db, oid) -> str | None:
    """ACTIVE -> CLAIMED for any account. Returns the claim token, or None if a claim is live or the account is tombstoned.
    The token is the ownership proof for every later step, so no request can release or overwrite another's claim."""
    token = secrets.token_hex(16)
    t = now()
    r = db.users.update_one(
        {"_id": oid, "deleting": {"$ne": True},
         "$or": [{"delete_claim_until": {"$exists": False}}, {"delete_claim_until": {"$lte": t}}]},
        {"$set": {"delete_claim_token": token, "delete_claim_until": t + CLAIM_SECONDS}})
    return token if r.matched_count == 1 else None


def release_claim(db, oid, token: str) -> None:
    """CLAIMED -> ACTIVE, only for the holder of `token`. A no-op once tombstoned (the claim fields are gone by then)."""
    db.users.update_one({"_id": oid, "delete_claim_token": token, "deleting": {"$ne": True}},
                        {"$unset": {"delete_claim_token": "", "delete_claim_until": ""}})


class LastAdmin(Exception):
    pass


class ClaimLost(Exception):
    pass


def verify_admin_safety(db, oid, token: str) -> dict:
    """Step 2. Re-read the account AFTER the claim so a stale `is_admin` (read before the password check, or changed by another
    request since) cannot decide. Returns the snapshot the tombstone must still match. Raises LastAdmin / ClaimLost."""
    fresh = db.users.find_one({"_id": oid, "delete_claim_token": token, "deleting": {"$ne": True}})
    if fresh is None:
        raise ClaimLost()
    admin = is_admin_account(fresh)
    if admin and not other_admin_exists(db, oid):
        raise LastAdmin()
    return {"email": fresh.get("email"), "admin": admin}


def tombstone(db, oid, token: str, snapshot: dict) -> bool:
    """CLAIMED -> DELETING. One atomic update that needs: the matching token, a claim that has not expired, an account that is
    not already tombstoned (a deleted account has no document to match), and an identity unchanged since the admin check
    (an account promoted to administrator after that check does not slip through). The claim is consumed in the same update."""
    t = now()
    q = {"_id": oid, "delete_claim_token": token, "delete_claim_until": {"$gt": t}, "deleting": {"$ne": True},
         "email": snapshot["email"]}
    if not snapshot["admin"]:
        q["is_admin"] = {"$ne": True}
    r = db.users.update_one(q, {
        "$set": {"deleting": True, "deletion_token": token, "deletion_started_at": t, "deletion_done": [],
                 "deletion_attempts": 0, "deletion_last_error": None},
        "$unset": {"delete_claim_token": "", "delete_claim_until": ""}})
    if r.matched_count == 1:
        log.info("deletion_tombstoned uid=%s", oid)
    return r.matched_count == 1


# ---- cascade -----------------------------------------------------------------------------------------------------------

def _worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{secrets.token_hex(4)}"


def _acquire(db, oid, token: str, worker: str) -> bool:
    t = now()
    r = db.users.update_one(
        {"_id": oid, "deleting": True, "deletion_token": token,
         "$or": [{"deletion_lease_until": {"$exists": False}}, {"deletion_lease_until": {"$lte": t}}]},
        {"$set": {"deletion_lease_owner": worker, "deletion_lease_until": t + LEASE_SECONDS, "deletion_last_attempt_at": t},
         "$inc": {"deletion_attempts": 1}})
    return r.matched_count == 1


def _renew(db, oid, token: str, worker: str) -> bool:
    return db.users.update_one({"_id": oid, "deleting": True, "deletion_token": token, "deletion_lease_owner": worker},
                               {"$set": {"deletion_lease_until": now() + LEASE_SECONDS}}).matched_count == 1


def _fail(db, oid, token: str, worker: str, err: Exception) -> None:
    """Release the lease with a back-off. The tombstone stays: a failed cascade never restores access."""
    doc = db.users.find_one({"_id": oid, "deletion_token": token}, {"deletion_attempts": 1}) or {}
    attempts = max(1, int(doc.get("deletion_attempts") or 1))
    wait = min(BACKOFF_MAX_SECONDS, BACKOFF_BASE_SECONDS * 2 ** (attempts - 1))
    db.users.update_one({"_id": oid, "deletion_token": token, "deletion_lease_owner": worker},
                        {"$set": {"deletion_lease_until": now() + wait, "deletion_last_error": f"{type(err).__name__}: {str(err)[:200]}"},
                         "$unset": {"deletion_lease_owner": ""}})


def run_deletion(db, oid, token: str, worker: str | None = None) -> str:
    """Drive the cascade for a tombstoned account. Returns one of:
      completed   every stage done and the users document removed
      busy        another worker holds the lease, or the account is backing off after a failure (nothing was done)
      failed      a stage raised; the lease was released with a back-off and the tombstone is untouched
      lease_lost  the lease was taken over mid-run; this worker stopped without touching the user document
    Safe to call any number of times and from any number of workers."""
    worker = worker or _worker_id()
    if not _acquire(db, oid, token, worker):
        return "busy"
    uid = str(oid)
    try:
        # Defence in depth, independent of the lease: no destructive work unless the tombstone for THIS token is in place.
        doc = db.users.find_one({"_id": oid, "deleting": True, "deletion_token": token}, {"deletion_done": 1})
        if doc is None:
            return "busy"
        done = set(doc.get("deletion_done") or [])
        for name, fn in STAGES:
            if name in done:
                continue
            if not _renew(db, oid, token, worker):
                return "lease_lost"
            fn(db, uid)
            db.users.update_one({"_id": oid, "deletion_token": token, "deletion_lease_owner": worker},
                                {"$addToSet": {"deletion_done": name}})
            log.info("deletion_stage uid=%s stage=%s", uid, name)
        if not _renew(db, oid, token, worker):
            return "lease_lost"
        # Last sweep: re-run the (idempotent) deletes once more straight before the final delete, so a request that was already
        # in flight when the tombstone landed and wrote a row after its stage ran does not outlive the account.
        for _, fn in STAGES:
            fn(db, uid)
        # The only place the users document is removed: tombstone token + our lease + every stage recorded.
        r = db.users.delete_one({"_id": oid, "deleting": True, "deletion_token": token, "deletion_lease_owner": worker,
                                 "deletion_done": {"$all": [n for n, _ in STAGES]}})
        if r.deleted_count != 1:
            return "lease_lost"
        log.info("deletion_completed uid=%s", uid)
        return "completed"
    except Exception as e:
        log.error("deletion_failed uid=%s error=%s", uid, type(e).__name__)
        _fail(db, oid, token, worker, e)
        return "failed"


def recover_deletions(db, limit: int = RECOVERY_BATCH, worker: str | None = None) -> dict:
    """Resume tombstoned accounts whose cascade is not running (a crashed process, or a failure whose back-off has elapsed).

    Bounded: at most `limit` accounts per call, oldest tombstone first. Idempotent and safe to run from several processes at
    once: each account needs its lease, so two sweeps never run the same cascade. Needs no authentication of the account."""
    worker = worker or _worker_id()
    limit = int(limit)
    if limit <= 0:                       # Mongo treats limit(0) as "no limit": never let a bounded sweep become unbounded
        return {"found": 0, "completed": 0, "failed": 0, "busy": 0, "lease_lost": 0}
    t = now()
    rows = list(db.users.find(
        {"deleting": True, "$or": [{"deletion_lease_until": {"$exists": False}}, {"deletion_lease_until": {"$lte": t}}]},
        {"_id": 1, "deletion_token": 1}).sort("deletion_started_at", 1).limit(limit))
    out = {"found": len(rows), "completed": 0, "failed": 0, "busy": 0, "lease_lost": 0}
    for row in rows:
        out[run_deletion(db, row["_id"], row["deletion_token"], worker)] += 1
    if rows:
        log.info("deletion_recovery found=%d completed=%d failed=%d busy=%d lease_lost=%d", *(out[k] for k in
                 ("found", "completed", "failed", "busy", "lease_lost")))
    return out


def pending_deletions(db) -> dict:
    """Operational view: tombstoned accounts still waiting for their cascade (the number that must trend to zero)."""
    t = now()
    rows = list(db.users.find({"deleting": True}, {"deletion_started_at": 1, "deletion_attempts": 1, "deletion_last_error": 1,
                                                   "deletion_lease_until": 1}))
    return {"pending": len(rows),
            "oldest_age_seconds": int(t - min((r.get("deletion_started_at") or t) for r in rows)) if rows else 0,
            "failing": sum(1 for r in rows if r.get("deletion_last_error")),
            "accounts": [{"id": str(r["_id"]), "attempts": r.get("deletion_attempts", 0), "last_error": r.get("deletion_last_error")}
                         for r in rows[:50]]}


RECOVERY_INTERVAL_ENV = "SCRIPTLIV_DELETION_RECOVERY_SECONDS"   # sweep period; 0 turns the background sweep off
DEFAULT_RECOVERY_INTERVAL = 60


def start_recovery_loop(get_db_fn, interval: float | None = None):
    """Run `recover_deletions` every `interval` seconds on a daemon thread. Returns a stop() callable.

    The first sweep happens one interval AFTER start (never at startup, so API start-up is not delayed), each sweep is bounded
    by RECOVERY_BATCH accounts, and an exception in a sweep is logged and the loop carries on. Several API processes may each
    run this: the per-account lease keeps them from running the same cascade. Returns a no-op when disabled."""
    import threading
    if interval is None:
        try:
            interval = float(os.environ.get(RECOVERY_INTERVAL_ENV, DEFAULT_RECOVERY_INTERVAL))
        except ValueError:
            interval = DEFAULT_RECOVERY_INTERVAL
    if interval <= 0:
        return lambda: None
    stop = threading.Event()

    def loop():
        while not stop.wait(interval):
            try:
                recover_deletions(get_db_fn())
            except Exception as e:   # never let the sweeper die: the next tick tries again
                log.error("deletion_recovery_error error=%s", type(e).__name__)

    t = threading.Thread(target=loop, name="deletion-recovery", daemon=True)
    t.start()
    return stop.set


if __name__ == "__main__":   # operator entry point:  python -m app.account_deletion [--status]
    import json
    import sys

    from .db import get_db
    logging.basicConfig(level=logging.INFO)
    _db = get_db()
    print(json.dumps(pending_deletions(_db) if "--status" in sys.argv else recover_deletions(_db)))
