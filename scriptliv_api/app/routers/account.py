import re
import time
from typing import Literal

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from pymongo.errors import DuplicateKeyError

from .. import email_service, subscriptions
from ..config import get_settings
from ..deps import current_user, db_dep, now, public_user
from ..security import hash_opaque, hash_password, make_token, new_opaque_token, verify_password

router = APIRouter(prefix="/v1", tags=["account"])

SUPPORTED_LANGUAGES = ["en"]  # only languages the apps are actually translated into
EMAIL_TOKEN_TTL = 24 * 3600
_attempts: dict[str, list[float]] = {}


def _err(status, code, message):
    raise HTTPException(status, {"code": code, "message": message})


def _throttle(key: str, limit=10, window=300):
    t = time.time()
    hits = [x for x in _attempts.get(key, []) if t - x < window]
    if len(hits) >= limit:
        _err(429, "too_many_attempts", "Too many attempts. Try again in a few minutes.")
    hits.append(t)
    _attempts[key] = hits


def _check_password_strength(pw: str):
    if len(pw) < 8:
        _err(422, "weak_password", "Password must be at least 8 characters.")


class RegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=256)


def _issue_email_token(db, user_id: str, kind: str, email: str) -> str:
    return email_service.issue_token(db, user_id, kind, email)


def _deliver_token(db, token: str, to: str, kind: str, user_id: str | None = None) -> dict:
    return email_service.send_token(db, token, to, kind, user_id)


@router.post("/auth/register", status_code=201)
def register(body: RegisterIn, db=Depends(db_dep)):
    _check_password_strength(body.password)
    email = body.email.lower()
    doc = {"name": body.name.strip(), "email": email, "email_verified": False, "pwhash": hash_password(body.password),
           "pwv": 1, "created_at": now(), "disabled": False}
    try:
        res = db.users.insert_one(doc)
    except DuplicateKeyError:
        _err(409, "email_taken", "An account with this email already exists.")
    uid = str(res.inserted_id)
    subscriptions.create_basic(db, uid)
    # No session token: the account cannot sign in until the email is verified.
    out = {"verification_required": True, "user": public_user({**doc, "_id": res.inserted_id})}
    try:
        out["verification"] = _deliver_token(db, _issue_email_token(db, uid, "verify", email), email, "verify", uid)
    except Exception:
        out["verification"] = {"delivery": "failed"}
    return out


@router.post("/auth/login")
def login(body: LoginIn, db=Depends(db_dep)):
    email = body.email.lower()
    _throttle("login:" + email)
    u = db.users.find_one({"email": email})
    # same response and similar work whether the email exists or not
    ok = verify_password(body.password, u["pwhash"]) if u else verify_password(body.password, "$2b$12$" + "x" * 53)
    if not u or not ok or u.get("disabled"):
        _err(401, "bad_credentials", "Email or password is incorrect.")
    _attempts.pop("login:" + email, None)
    if not u.get("email_verified"):
        # correct password, unverified email: no token. Only someone who knows the password learns this.
        _err(403, "email_not_verified", "Verify your email first. Open the link we sent you, then sign in.")
    return {"token": make_token(str(u["_id"]), u.get("pwv", 1)), "user": public_user(u)}


class ResendIn(BaseModel):
    email: EmailStr


RESEND_REPLY = {"status": "ok", "message": "If that account still needs verification, a new link is on its way."}


@router.post("/auth/resend-verification", status_code=202)
def resend_verification_public(body: ResendIn, db=Depends(db_dep)):
    """Signed-out resend for a new account that has not verified yet. Same reply whether or not the account exists."""
    email = body.email.lower()
    _throttle("resendpub:" + email, limit=5)
    u = db.users.find_one({"email": email})
    if not u or u.get("email_verified") or u.get("disabled") or not email_service.delivery_possible(email):
        return RESEND_REPLY
    uid = str(u["_id"])
    try:
        out = _deliver_token(db, _issue_email_token(db, uid, "verify", email), email, "verify", uid)
    except Exception:
        return RESEND_REPLY
    if out.get("dev_token"):          # SCRIPTLIV_DEV_RETURN_TOKENS=1 only (local testing)
        return {**RESEND_REPLY, "dev_token": out["dev_token"]}
    return RESEND_REPLY


class VerifyIn(BaseModel):
    token: str


@router.post("/auth/verify-email")
def verify_email(body: VerifyIn, db=Depends(db_dep)):
    _throttle("verify:" + hash_opaque(body.token[:64]), limit=20)
    row = email_service.consume_token(db, body.token, ("verify", "change"))   # atomic: unknown, expired and used all look alike
    if not row:
        _err(400, "invalid_token", "This link is invalid or has expired. Request a new verification email.")
    uid = ObjectId(row["user_id"])
    try:
        db.users.update_one({"_id": uid}, {"$set": {"email": row["email"], "email_verified": True}, "$unset": {"pending_email": ""}})
    except DuplicateKeyError:
        _err(409, "email_taken", "That email is already used by another account.")
    return {"user": public_user(db.users.find_one({"_id": uid}))}


@router.get("/me")
def me(user=Depends(current_user)):
    return {"user": public_user(user)}


class ProfileIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)


@router.patch("/me")
def update_profile(body: ProfileIn, user=Depends(current_user), db=Depends(db_dep)):
    db.users.update_one({"_id": user["_id"]}, {"$set": {"name": body.name.strip()}})
    return {"user": public_user(db.users.find_one({"_id": user["_id"]}))}


class EmailChangeIn(BaseModel):
    new_email: EmailStr
    password: str = Field(max_length=256)


@router.post("/me/email")
def request_email_change(body: EmailChangeIn, user=Depends(current_user), db=Depends(db_dep)):
    _throttle("emailchg:" + str(user["_id"]), limit=5)
    if not verify_password(body.password, user["pwhash"]):
        _err(403, "bad_password", "Password is incorrect.")
    new = body.new_email.lower()
    if new == user["email"]:
        _err(422, "same_email", "That is already your email.")
    if db.users.find_one({"email": new}):
        _err(409, "email_taken", "An account with this email already exists.")
    if not email_service.delivery_possible(new):
        _err(503, "email_not_configured", "Email delivery is not set up yet, so the email address cannot be changed.")
    db.users.update_one({"_id": user["_id"]}, {"$set": {"pending_email": new}})
    token = _issue_email_token(db, str(user["_id"]), "change", new)
    return {"pending_email": new, **_deliver_token(db, token, new, "change", str(user["_id"]))}


@router.post("/me/email/resend")
def resend_verification(user=Depends(current_user), db=Depends(db_dep)):
    _throttle("resend:" + str(user["_id"]), limit=5)
    target = user.get("pending_email") or user["email"]
    if user.get("email_verified") and not user.get("pending_email"):
        _err(409, "already_verified", "Your email is already verified.")
    if not email_service.delivery_possible(target):
        _err(503, "email_not_configured", "Email delivery is not set up yet.")
    kind = "change" if user.get("pending_email") else "verify"
    return _deliver_token(db, _issue_email_token(db, str(user["_id"]), kind, target), target, kind, str(user["_id"]))


class ForgotIn(BaseModel):
    email: EmailStr


FORGOT_REPLY = {"status": "ok", "message": "If an account exists for that email, a reset link is on its way."}


@router.post("/auth/forgot-password", status_code=202)
def forgot_password(body: ForgotIn, db=Depends(db_dep)):
    """Always the same answer (no account enumeration). The link is mailed only to the address on the account."""
    email = body.email.lower()
    _throttle("forgot:" + email, limit=5, window=900)
    u = db.users.find_one({"email": email})
    if u and not u.get("disabled") and email_service.delivery_possible(email):
        uid = str(u["_id"])
        out = _deliver_token(db, _issue_email_token(db, uid, "reset", email), email, "reset", uid)
        if out.get("dev_token"):          # SCRIPTLIV_DEV_RETURN_TOKENS=1 only (local testing)
            return {**FORGOT_REPLY, "dev_token": out["dev_token"]}
    return FORGOT_REPLY


class ResetIn(BaseModel):
    token: str = Field(max_length=200)
    new_password: str = Field(max_length=256)


@router.post("/auth/reset-password")
def reset_password(body: ResetIn, db=Depends(db_dep)):
    _throttle("reset:" + hash_opaque(body.token[:64]), limit=10)
    _check_password_strength(body.new_password)        # checked first so a weak password does not burn the link
    row = email_service.consume_token(db, body.token, ("reset",))
    if not row:
        _err(400, "invalid_token", "This link is invalid or has expired. Request a new reset email.")
    u = db.users.find_one({"_id": ObjectId(row["user_id"])})
    if not u or u.get("disabled"):
        _err(400, "invalid_token", "This link is invalid or has expired. Request a new reset email.")
    # new password; the pwv bump signs out every existing session
    db.users.update_one({"_id": u["_id"]}, {"$set": {"pwhash": hash_password(body.new_password), "pwv": u.get("pwv", 1) + 1}})
    return {"status": "ok", "message": "Password updated. Sign in with your new password."}


class PasswordIn(BaseModel):
    current_password: str = Field(max_length=256)
    new_password: str = Field(max_length=256)


@router.post("/me/password")
def change_password(body: PasswordIn, user=Depends(current_user), db=Depends(db_dep)):
    _throttle("pwchg:" + str(user["_id"]), limit=5)
    if not verify_password(body.current_password, user["pwhash"]):
        _err(403, "bad_password", "Current password is incorrect.")
    _check_password_strength(body.new_password)
    pwv = user.get("pwv", 1) + 1  # invalidates every other signed-in session
    db.users.update_one({"_id": user["_id"]}, {"$set": {"pwhash": hash_password(body.new_password), "pwv": pwv}})
    return {"token": make_token(str(user["_id"]), pwv)}


class SettingsIn(BaseModel):
    theme: Literal["light", "dark", "system"] | None = None
    language: str | None = None
    prevent_auto_lock: bool | None = None
    usage_warnings: bool | None = None
    warn_percents: list[int] | None = Field(default=None, max_length=4)
    personal_limit_minutes: int | None = Field(default=None, ge=0, le=1_000_000)


_DEFAULT_SETTINGS = {"theme": "system", "language": "en", "prevent_auto_lock": True, "usage_warnings": True,
                     "warn_percents": [80, 95], "personal_limit_minutes": None}


def _settings_out(doc):
    out = dict(_DEFAULT_SETTINGS)
    out.update({k: v for k, v in (doc or {}).items() if k in _DEFAULT_SETTINGS})
    return {"settings": out, "supported_languages": SUPPORTED_LANGUAGES}


@router.get("/settings")
def get_settings_route(user=Depends(current_user), db=Depends(db_dep)):
    return _settings_out(db.settings.find_one({"user_id": str(user["_id"])}))


@router.put("/settings")
def put_settings(body: SettingsIn, user=Depends(current_user), db=Depends(db_dep)):
    upd = body.model_dump(exclude_unset=True)
    if "language" in upd and upd["language"] not in SUPPORTED_LANGUAGES:
        _err(422, "unsupported_language", "That language is not available yet.")
    if "warn_percents" in upd:
        if any(p < 1 or p > 99 for p in upd["warn_percents"]):
            _err(422, "bad_warn_percents", "Warning levels must be between 1 and 99 percent.")
        upd["warn_percents"] = sorted(set(upd["warn_percents"]))
    if upd:
        db.settings.update_one({"user_id": str(user["_id"])}, {"$set": upd}, upsert=True)
    return _settings_out(db.settings.find_one({"user_id": str(user["_id"])}))
