"""Plan and add-on catalogue. Minutes are the customer-facing unit; the ledger meters seconds."""
from dataclasses import dataclass

BASIC, PRO = "basic", "pro"
GST_RATE = 0.18


def with_gst(amount_inr: float) -> float:
    """price_inr_month/ADDON_PRICE_INR below are the pre-tax catalogue price; this is what's actually
    charged (and what price_display shows) once India's 18% GST is added on top."""
    return round(amount_inr * (1 + GST_RATE), 2)


@dataclass(frozen=True)
class Plan:
    id: str
    name: str
    included_minutes: int
    price_inr_month: int  # whole Indian Rupees; 0 = free
    price_usd_month: int  # legacy/compat
    tax_note: str  # e.g. "+ GST"
    blurb: str
    max_session_minutes: int | None = None  # per-session cap in minutes; None = no cap

    @property
    def included_seconds(self) -> int:
        return self.included_minutes * 60

    @property
    def max_session_seconds(self) -> int | None:
        return None if self.max_session_minutes is None else self.max_session_minutes * 60

    @property
    def price_display(self) -> str:
        if self.price_inr_month == 0:
            return "Free"
        tax = f" {self.tax_note}" if self.tax_note else ""
        return f"₹{self.price_inr_month:,}{tax}"


PLANS = {
    BASIC: Plan(
        BASIC,
        "Basic",
        300,
        0,
        0,
        "",
        "300 free minutes every month. Up to 30 minutes per session.",
        30,
    ),
    PRO: Plan(
        PRO,
        "Pro",
        2500,
        999,
        20,
        "+ GST",
        "2,500 minutes every month. Up to 2 hours per session.",
        120,
    ),
}

ADDON_MINUTES = 1000
ADDON_PRICE_INR = 499
ADDON_PRICE_USD = 10
ADDON_TAX_NOTE = "+ GST"
ADDON_MAX_SESSION_MINUTES = 120
ADDON_NOTE = f"1,000 extra minutes for ₹{ADDON_PRICE_INR:,} {ADDON_TAX_NOTE}. Up to 2 hours per session. Only valid till plan end."


# Inaugural offer (config.promo_active): free, but each account gets a fixed number of minutes for the whole offer (not per
# month, not reset). Plan and add-on minutes are untouched. One session may run PROMO_MAX_SESSION_MINUTES, same as the relay's cap.
PROMO_MAX_SESSION_MINUTES = 240
PROMO_ALLOWANCE_MINUTES = 1000
PROMO_ALLOWANCE_SECONDS = PROMO_ALLOWANCE_MINUTES * 60
