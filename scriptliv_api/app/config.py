"""Environment-driven settings. Secrets come from the environment only; nothing here is logged."""
import os
from dataclasses import dataclass, field


def _int(name, default):
    return int(os.environ.get(name, default))


@dataclass
class Settings:
    mongodb_uri: str = field(default_factory=lambda: os.environ.get("MONGODB_URI", ""))
    mongodb_db: str = field(default_factory=lambda: os.environ.get("SCRIPTLIV_DB", "scriptliv_staging"))
    jwt_secret: str = field(default_factory=lambda: os.environ.get("SCRIPTLIV_JWT_SECRET", ""))
    token_ttl_seconds: int = field(default_factory=lambda: _int("SCRIPTLIV_TOKEN_TTL_SECONDS", 7 * 24 * 3600))
    # shared secret the speech relay presents on /internal/* calls
    relay_secret: str = field(default_factory=lambda: os.environ.get("SCRIPTLIV_RELAY_SECRET", ""))
    app_base_url: str = field(default_factory=lambda: os.environ.get("SCRIPTLIV_APP_URL", "http://localhost:3100"))
    # Mobile store links used by the web shared-link page when the app is not installed. Empty = hidden.
    android_store_url: str = field(default_factory=lambda: os.environ.get("SCRIPTLIV_ANDROID_STORE_URL", ""))
    ios_store_url: str = field(default_factory=lambda: os.environ.get("SCRIPTLIV_IOS_STORE_URL", ""))
    # Only for local/staging testing: return email-verification tokens in the API response instead of mailing them.
    dev_return_tokens: bool = field(default_factory=lambda: os.environ.get("SCRIPTLIV_DEV_RETURN_TOKENS") == "1")
    smtp_host: str = field(default_factory=lambda: os.environ.get("SMTP_HOST", ""))
    stripe_secret_key: str = field(default_factory=lambda: os.environ.get("STRIPE_SECRET_KEY", ""))
    stripe_webhook_secret: str = field(default_factory=lambda: os.environ.get("STRIPE_WEBHOOK_SECRET", ""))
    stripe_pro_price_id: str = field(default_factory=lambda: os.environ.get("STRIPE_PRO_PRICE_ID", ""))
    stripe_addon_price_id: str = field(default_factory=lambda: os.environ.get("STRIPE_ADDON_PRICE_ID", ""))
    # Payment failure policy (documented in docs/SCRIPTLIV_PLATFORM.md). All values are configurable.
    payment_max_retries: int = field(default_factory=lambda: _int("SCRIPTLIV_PAYMENT_MAX_RETRIES", 3))
    payment_retry_days: str = field(default_factory=lambda: os.environ.get("SCRIPTLIV_PAYMENT_RETRY_DAYS", "1,3,5"))
    payment_final_status: str = field(default_factory=lambda: os.environ.get("SCRIPTLIV_PAYMENT_FINAL_STATUS", "restricted"))
    payment_retry_cooldown: int = field(default_factory=lambda: _int("SCRIPTLIV_PAYMENT_RETRY_COOLDOWN", 60))
    # Email providers (shared verification logic in email_service.py; delivery in email_providers.py)
    gmail_client_id: str = field(default_factory=lambda: os.environ.get("GMAIL_CLIENT_ID", ""))
    gmail_client_secret: str = field(default_factory=lambda: os.environ.get("GMAIL_CLIENT_SECRET", ""))
    gmail_refresh_token: str = field(default_factory=lambda: os.environ.get("GMAIL_REFRESH_TOKEN", ""))
    gmail_sender: str = field(default_factory=lambda: os.environ.get("GMAIL_SENDER", ""))
    resend_api_key: str = field(default_factory=lambda: os.environ.get("RESEND_API_KEY", ""))
    resend_from: str = field(default_factory=lambda: os.environ.get("RESEND_FROM", ""))
    # recipient domains delivered through Resend (default: Microsoft consumer mail); everything else goes through Gmail
    resend_domains: str = field(default_factory=lambda: os.environ.get("EMAIL_RESEND_DOMAINS", "outlook.com,hotmail.com,live.com,msn.com"))
    cors_origins: list = field(default_factory=lambda: [o for o in os.environ.get("SCRIPTLIV_CORS_ORIGINS", "http://localhost:3100,http://127.0.0.1:3100").split(",") if o])


def get_settings() -> Settings:
    return Settings()
