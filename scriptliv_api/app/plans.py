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

    @property
    def included_seconds(self) -> int:
        return self.included_minutes * 60


PLANS = {
    BASIC: Plan(BASIC, "Basic", 300, 0, "300 free minutes every month."),
    PRO: Plan(PRO, "Pro", 2500, 20, "2,500 minutes every month."),
}
ADDON_MINUTES = 1000
ADDON_PRICE_USD = 10
