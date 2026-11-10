"""MongoDB access. One process-wide database handle; tests swap it with mongomock via set_db()."""
import threading

from pymongo import ASCENDING, MongoClient

from .config import get_settings

_db = None
_lock = threading.Lock()


def set_db(db):
    global _db
    _db = db
    ensure_indexes(db)


def get_db():
    global _db
    if _db is None:
        with _lock:
            if _db is None:
                s = get_settings()
                if not s.mongodb_uri:
                    raise RuntimeError("MONGODB_URI is not set")
                client = MongoClient(s.mongodb_uri, serverSelectionTimeoutMS=8000, appName="scriptliv-api")
                _db = client[s.mongodb_db]
                ensure_indexes(_db)
    return _db


def _per_user(coll):
    """One document per user. Unique when existing data allows it; otherwise fall back to a plain index instead of failing startup."""
    try:
        coll.create_index("user_id", unique=True)
    except Exception:
        coll.create_index("user_id")


def ensure_indexes(db):
    db.users.create_index("email", unique=True)
    db.subscriptions.create_index("user_id", unique=True)
    # webhook / retry lookups by provider ids (previously collection scans). Sparse, not partial: the planner uses a sparse
    # index for an equality match, but cannot prove an equality satisfies a partial {"$type": "string"} filter.
    for f in ("provider_customer_id", "provider_subscription_id"):
        db.subscriptions.create_index(f, sparse=True)
    _per_user(db.settings)          # read on every authorize()
    _per_user(db.billing_details)
    db.usage_sessions.create_index([("user_id", ASCENDING), ("ended_at", ASCENDING), ("last_report_at", ASCENDING)])  # open-session / reservation scan
    db.addons.create_index([("user_id", ASCENDING), ("expires_at", ASCENDING)])
    db.usage_sessions.create_index("session_id", unique=True)
    db.usage_sessions.create_index([("user_id", ASCENDING), ("started_at", ASCENDING)])
    db.usage_minutes.create_index([("session_id", ASCENDING), ("minute", ASCENDING)], unique=True)
    db.usage_ledger.create_index([("user_id", ASCENDING), ("period_start", ASCENDING)])
    db.sessions.create_index("session_id", unique=True)
    db.sessions.create_index("owner_id")
    db.sessions.create_index("share_token", unique=True, sparse=True)
    db.email_tokens.create_index("token_hash", unique=True)
    # spent/expired tokens disappear a day after they expire (TTL index on a real date field)
    db.email_tokens.create_index("expires_dt", expireAfterSeconds=86400)
    db.email_tokens.create_index([("user_id", ASCENDING), ("kind", ASCENDING), ("used", ASCENDING)])
    db.email_deliveries.create_index([("user_id", ASCENDING), ("ts", ASCENDING)])
    db.payments.create_index([("user_id", ASCENDING), ("created_at", ASCENDING)])
    # a provider event / payment reference can be applied only once, even when delivered twice at the same moment
    db.provider_events.create_index("event_id", unique=True)
    db.payments.create_index("provider_ref", unique=True, partialFilterExpression={"provider_ref": {"$type": "string"}})
