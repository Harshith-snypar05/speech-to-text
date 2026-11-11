"""Email delivery providers. They only DELIVER a finished message; token creation, hashing, expiry and single use live in
email_service.py and do not depend on which provider carries the mail.

  Gmail API  (OAuth2, send-only scope)  -> every recipient except the Resend domains
  Resend     (API key, verified domain) -> Outlook/Hotmail/Live/MSN recipients (EMAIL_RESEND_DOMAINS)
  SMTP       (legacy, only if SMTP_HOST is set and Gmail is not configured)

Secrets come from the environment / a secret manager only, are never logged and never appear in responses.
NOTHING here has been run against live Gmail or Resend (no credentials exist in this environment): the code follows the
providers' documented HTTP APIs and is covered by tests that replace the HTTP layer. Real delivery must be verified with
real credentials and a real mailbox before it is claimed to work.
"""
import base64
import logging
import time
from dataclasses import dataclass
from email.message import EmailMessage

import httpx

from . import mailer
from .config import get_settings

logger = logging.getLogger(__name__)

GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.send"    # send only: cannot read, list or delete mail
GMAIL_TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
RESEND_URL = "https://api.resend.com/emails"
TIMEOUT = 10.0
MAX_ATTEMPTS = 3
BACKOFF = (0.5, 1.5)      # seconds slept before attempt 2 and 3


class EmailError(Exception):
    """`transient` errors (timeouts, 429, 5xx) are retried; the rest are final. `code` is safe to log and store."""

    def __init__(self, code: str, transient: bool = False):
        super().__init__(code)
        self.code = code
        self.transient = transient


@dataclass
class Message:
    to: str
    subject: str
    text: str
    html: str | None = None


@dataclass
class Sent:
    provider: str
    message_id: str | None = None


def _mime(m: Message, sender: str) -> EmailMessage:
    e = EmailMessage()
    e["From"] = sender
    e["To"] = m.to
    e["Subject"] = m.subject
    e.set_content(m.text)
    if m.html:
        e.add_alternative(m.html, subtype="html")
    return e


class GmailProvider:
    name = "gmail"

    def __init__(self):
        self._access = None
        self._expires = 0.0

    @staticmethod
    def configured() -> bool:
        s = get_settings()
        return bool(s.gmail_client_id and s.gmail_client_secret and s.gmail_refresh_token and s.gmail_sender)

    def _refresh(self) -> str:
        s = get_settings()
        try:
            r = httpx.post(GMAIL_TOKEN_URL, data={"client_id": s.gmail_client_id, "client_secret": s.gmail_client_secret,
                                                  "refresh_token": s.gmail_refresh_token, "grant_type": "refresh_token"}, timeout=TIMEOUT)
        except httpx.HTTPError:
            raise EmailError("gmail_token_unreachable", transient=True)
        if r.status_code in (400, 401):
            # invalid_grant: the refresh token was revoked/expired (e.g. test-mode OAuth apps expire tokens after 7 days).
            raise EmailError("gmail_refresh_token_invalid")
        if r.status_code >= 500 or r.status_code == 429:
            raise EmailError("gmail_token_unavailable", transient=True)
        r.raise_for_status()
        j = r.json()
        self._access = j["access_token"]
        self._expires = time.time() + int(j.get("expires_in", 3600)) - 60
        return self._access

    def _token(self, force=False) -> str:
        if force or not self._access or time.time() >= self._expires:
            return self._refresh()
        return self._access

    def _send(self, raw: str, token: str):
        try:
            return httpx.post(GMAIL_SEND_URL, json={"raw": raw}, headers={"Authorization": "Bearer " + token}, timeout=TIMEOUT)
        except httpx.HTTPError:
            raise EmailError("gmail_unreachable", transient=True)

    def send(self, m: Message) -> Sent:
        s = get_settings()
        raw = base64.urlsafe_b64encode(_mime(m, s.gmail_sender).as_bytes()).decode()
        r = self._send(raw, self._token())
        if r.status_code == 401:               # access token expired or revoked between refreshes: refresh once and retry
            r = self._send(raw, self._token(force=True))
        if r.status_code == 429 or r.status_code >= 500:
            raise EmailError(f"gmail_http_{r.status_code}", transient=True)
        if r.status_code in (401, 403):
            raise EmailError("gmail_unauthorized")
        if r.status_code >= 400:
            raise EmailError(f"gmail_http_{r.status_code}")
        return Sent("gmail", (r.json() or {}).get("id"))


class ResendProvider:
    name = "resend"

    @staticmethod
    def configured() -> bool:
        s = get_settings()
        return bool(s.resend_api_key and s.resend_from)   # RESEND_FROM must be an address on a domain verified in Resend

    def send(self, m: Message) -> Sent:
        s = get_settings()
        body = {"from": s.resend_from, "to": [m.to], "subject": m.subject, "text": m.text}
        if m.html:
            body["html"] = m.html
        try:
            r = httpx.post(RESEND_URL, json=body, headers={"Authorization": "Bearer " + s.resend_api_key}, timeout=TIMEOUT)
        except httpx.HTTPError:
            raise EmailError("resend_unreachable", transient=True)
        if r.status_code == 429 or r.status_code >= 500:
            raise EmailError(f"resend_http_{r.status_code}", transient=True)
        if r.status_code in (401, 403):
            raise EmailError("resend_unauthorized")           # bad API key, or the sender domain is not verified
        if r.status_code >= 400:
            raise EmailError(f"resend_http_{r.status_code}")
        return Sent("resend", (r.json() or {}).get("id"))


class SmtpProvider:
    name = "smtp"

    @staticmethod
    def configured() -> bool:
        return mailer.configured()

    def send(self, m: Message) -> Sent:
        try:
            mailer.send(m.to, m.subject, m.text)
        except Exception:
            raise EmailError("smtp_failed", transient=True)
        return Sent("smtp")


_gmail = GmailProvider()          # one instance so the refreshed access token is reused until it expires


def resend_domain(to: str) -> bool:
    domain = to.rsplit("@", 1)[-1].lower()
    return domain in {d.strip().lower() for d in get_settings().resend_domains.split(",") if d.strip()}


def provider_for(to: str):
    """The provider that must carry mail to `to`, or None when it is not configured. Outlook-family recipients go through
    Resend only (never silently through Gmail); everyone else through Gmail, then legacy SMTP."""
    if resend_domain(to):
        return ResendProvider() if ResendProvider.configured() else None
    if GmailProvider.configured():
        return _gmail
    if SmtpProvider.configured():
        return SmtpProvider()
    if ResendProvider.configured():   # no Gmail/SMTP set up: Resend carries everything rather than leaving users without email
        return ResendProvider()
    return None


def deliver(m: Message, sleep=time.sleep) -> tuple[Sent | None, int, str | None]:
    """(sent, attempts, error_code). Retries transient failures with backoff; a permanent failure stops at once."""
    p = provider_for(m.to)
    if p is None:
        return None, 0, "no_provider"
    err = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return p.send(m), attempt, None
        except EmailError as e:
            err = e
            logger.warning("email via %s failed (attempt %d): %s", p.name, attempt, e.code)
            if not e.transient or attempt == MAX_ATTEMPTS:
                break
            sleep(BACKOFF[min(attempt - 1, len(BACKOFF) - 1)])
    return None, attempt, err.code if err else "unknown"


def available_for(to: str) -> bool:
    return provider_for(to) is not None
