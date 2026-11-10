"""Billing-period arithmetic. Periods are monthly, anchored to the subscription start day (clamped to month length)."""
import calendar
from datetime import datetime, timezone


def add_months(anchor_ts: float, months: int) -> float:
    a = datetime.fromtimestamp(anchor_ts, tz=timezone.utc)
    m0 = a.month - 1 + months
    y, m = a.year + m0 // 12, m0 % 12 + 1
    d = min(a.day, calendar.monthrange(y, m)[1])
    return a.replace(year=y, month=m, day=d).timestamp()


def period_for(anchor_ts: float, now: float) -> tuple[float, float, int]:
    """(start, end, index) of the period containing `now`."""
    k = 0
    while add_months(anchor_ts, k + 1) <= now:
        k += 1
    return add_months(anchor_ts, k), add_months(anchor_ts, k + 1), k
