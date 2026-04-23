"""Pure performance-fee calculator. Zero I/O, fully deterministic.

The output of this module is the authoritative source for the fee math —
everything else (data fetching, transfers, persistence) is an adapter
around this function.

Formula (quarterly):

    hurdle_floor = hwm_in * (1 + 0.05/4)

    if end_nav > hurdle_floor:              # strict greater-than
        fee_owed = 0.30 * (end_nav - hwm_in)     # catch-up: on ALL profit above HWM
        hwm_out  = max(peak_nav - fee_owed, hurdle_floor)
    else:
        fee_owed = 0
        hwm_out  = hurdle_floor              # HWM still ticks up by hurdle

Fees are quantized DOWN to 6 decimals (USDC precision). The residual
stays with the trading account — never transfer more than calculated.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_DOWN, Decimal

from .config import FEE_RATE, HURDLE_PER_PERIOD, USDC_QUANTUM


@dataclass(frozen=True)
class PeriodResult:
    period_start: datetime
    period_end: datetime
    start_nav: Decimal
    end_nav: Decimal
    peak_nav: Decimal
    hwm_in: Decimal
    hurdle_floor: Decimal
    hurdle_cleared: bool
    fee_owed: Decimal
    hwm_out: Decimal


def compute_period(
    hwm_in: Decimal,
    nav_series: list[tuple[int, Decimal]],
    period_start: datetime,
    period_end: datetime,
) -> PeriodResult:
    if not nav_series:
        raise ValueError("Cannot compute period with empty NAV series")

    start_nav = nav_series[0][1]
    end_nav = nav_series[-1][1]
    peak_nav = max(nav for _, nav in nav_series)

    hurdle_floor = hwm_in * (Decimal("1") + HURDLE_PER_PERIOD)

    if end_nav > hurdle_floor:
        raw_fee = FEE_RATE * (end_nav - hwm_in)
        fee_owed = raw_fee.quantize(USDC_QUANTUM, rounding=ROUND_DOWN)
        hwm_candidate = peak_nav - fee_owed
        hwm_out = max(hwm_candidate, hurdle_floor)
        hurdle_cleared = True
    else:
        fee_owed = Decimal("0")
        hwm_out = hurdle_floor
        hurdle_cleared = False

    return PeriodResult(
        period_start=period_start,
        period_end=period_end,
        start_nav=start_nav,
        end_nav=end_nav,
        peak_nav=peak_nav,
        hwm_in=hwm_in,
        hurdle_floor=hurdle_floor,
        hurdle_cleared=hurdle_cleared,
        fee_owed=fee_owed,
        hwm_out=hwm_out,
    )
