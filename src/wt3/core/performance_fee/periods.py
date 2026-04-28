"""Period boundary arithmetic.

Periods are 3 calendar months, anchored at START_DATE (2026-05-01 UTC).
Period 1: 2026-05-01 → 2026-07-31 23:59:59 UTC
Period 2: 2026-08-01 → 2026-10-31 23:59:59 UTC
...

Pure date math. No I/O.
"""

from calendar import monthrange
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .config import PERIOD_MONTHS, START_DATE


@dataclass(frozen=True)
class Period:
    index: int
    start: datetime
    end: datetime

    @property
    def start_ms(self) -> int:
        return int(self.start.timestamp() * 1000)

    @property
    def end_ms(self) -> int:
        return int(self.end.timestamp() * 1000)


def _shift_months(dt: datetime, months: int) -> datetime:
    """Add `months` calendar months to dt, keeping day-of-month where possible."""
    month_index = dt.month - 1 + months
    year = dt.year + month_index // 12
    month = month_index % 12 + 1
    day = min(dt.day, monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def period_for_index(index: int) -> Period:
    """Return the Period object for the given zero-based period index."""
    if index < 0:
        raise ValueError(f"Period index must be >= 0, got {index}")
    start = _shift_months(START_DATE, index * PERIOD_MONTHS)
    next_start = _shift_months(START_DATE, (index + 1) * PERIOD_MONTHS)
    end = next_start - timedelta(seconds=1)
    return Period(index=index, start=start, end=end)


def closed_periods_before(now: datetime) -> list[Period]:
    """All periods whose end < now, in chronological order."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    result: list[Period] = []
    i = 0
    while True:
        p = period_for_index(i)
        if p.end >= now:
            break
        result.append(p)
        i += 1
    return result


def current_period(now: datetime) -> Period | None:
    """The period that contains `now`, or None if before START_DATE."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    if now < START_DATE:
        return None
    i = 0
    while True:
        p = period_for_index(i)
        if p.start <= now <= p.end:
            return p
        if p.start > now:
            return None
        i += 1
