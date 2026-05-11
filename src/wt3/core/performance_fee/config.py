"""Performance fee constants.

All monetary values use Decimal to avoid float rounding in money math.
These are the public, auditable parameters of the fee agreement between
Oasis and Moonward Capital.
"""

from datetime import datetime, timezone
from decimal import Decimal

INITIAL_HWM: Decimal = Decimal("20000")

HURDLE_ANNUAL: Decimal = Decimal("0.05")
HURDLE_PER_PERIOD: Decimal = HURDLE_ANNUAL / Decimal("4")

FEE_RATE: Decimal = Decimal("0.30")

FEE_WALLET: str = "0xbf5f64d05e36a34bf43ea95e99657b09e4c7a1bb"

START_DATE: datetime = datetime(2026, 4, 1, 0, 0, 0, tzinfo=timezone.utc)

PERIOD_MONTHS: int = 3

USDC_DECIMALS: int = 6
USDC_QUANTUM: Decimal = Decimal("0.000001")

MAX_TRANSFER_RETRIES: int = 3

GRACE_SECONDS_AFTER_PERIOD_END: int = 3600

STATE_FILE_PATH: str = "/storage/data/hwm_state.json"
