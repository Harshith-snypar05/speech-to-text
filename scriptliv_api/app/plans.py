"""Plan and add-on catalogue. Minutes are the customer-facing unit; the ledger meters seconds."""
from dataclasses import dataclass

BASIC, PRO = "basic", "pro"


@dataclass(frozen=True)
class Plan:
    id: str
    name: str
    included_minutes: int
    price_usd_month: int  # whole US dollars; 0 = free
    blurb: str
    max_session_minutes: int | None = None  # per-session cap; None = no cap

    @property
    def included_seconds(self) -> int:
        return self.included_minutes * 60

    @property
    def max_session_seconds(self) -> int | None:
        return None if self.max_session_minutes is None else self.max_session_minutes * 60


PLANS = {
    BASIC: Plan(BASIC, "Basic", 300, 0, "300 free minutes every month, up to 30 minutes per session.", 30),
    PRO: Plan(PRO, "Pro", 2500, 20, "2,500 minutes every month."),
}
ADDON_MINUTES = 1000
ADDON_PRICE_USD = 10
