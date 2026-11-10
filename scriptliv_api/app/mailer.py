"""Email delivery. Real SMTP only: with SMTP_HOST unset, nothing is sent and callers are told so (no fake delivery)."""
import os
import smtplib
from email.message import EmailMessage

from .config import get_settings


def configured() -> bool:
    return bool(get_settings().smtp_host)


def send(to: str, subject: str, body: str) -> None:
    s = get_settings()
    if not s.smtp_host:
        raise RuntimeError("email_not_configured")
    msg = EmailMessage()
    msg["From"] = os.environ.get("SMTP_FROM", "no-reply@scriptliv.local")
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    with smtplib.SMTP(s.smtp_host, int(os.environ.get("SMTP_PORT", "587")), timeout=15) as smtp:
        smtp.starttls()
        user, pw = os.environ.get("SMTP_USER"), os.environ.get("SMTP_PASSWORD")
        if user and pw:
            smtp.login(user, pw)
        smtp.send_message(msg)
