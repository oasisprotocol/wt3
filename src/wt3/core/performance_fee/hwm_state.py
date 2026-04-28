"""High Water Mark (HWM) state persistence and reconstruction.

Cache at /storage/data/hwm_state.json (survives container restart within
the same persistent volume). Ground truth = Hyperliquid NAV history +
on-chain fee-transfer ledger. If the cache is lost, state is rebuilt
deterministically from the zero-trust sources.
"""

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Optional

from .calculator import PeriodResult, compute_period
from .config import INITIAL_HWM, STATE_FILE_PATH, USDC_QUANTUM
from .fee_ledger import FeeTransfer, transfers_in_window
from .periods import Period, closed_periods_before, period_for_index

logger = logging.getLogger(__name__)


class StateReconciliationError(Exception):
    """Raised when cache vs. on-chain ledger disagree beyond tolerance."""


@dataclass
class PeriodRecord:
    period_index: int
    period_start: str
    period_end: str
    start_nav: str
    end_nav: str
    peak_nav: str
    hwm_in: str
    hurdle_floor: str
    hurdle_cleared: bool
    fee_owed: str
    fee_paid: str
    hwm_out: str
    tx_hash: str
    computed_at: str

    @classmethod
    def from_result(
        cls,
        index: int,
        result: PeriodResult,
        fee_paid: Decimal,
        tx_hash: str,
    ) -> "PeriodRecord":
        return cls(
            period_index=index,
            period_start=result.period_start.isoformat(),
            period_end=result.period_end.isoformat(),
            start_nav=str(result.start_nav),
            end_nav=str(result.end_nav),
            peak_nav=str(result.peak_nav),
            hwm_in=str(result.hwm_in),
            hurdle_floor=str(result.hurdle_floor),
            hurdle_cleared=result.hurdle_cleared,
            fee_owed=str(result.fee_owed),
            fee_paid=str(fee_paid),
            hwm_out=str(result.hwm_out),
            tx_hash=tx_hash,
            computed_at=datetime.now(timezone.utc).isoformat(),
        )


@dataclass
class HwmState:
    version: int = 1
    hwm: str = str(INITIAL_HWM)
    last_processed_period_index: int = -1
    history: list[PeriodRecord] = field(default_factory=list)

    @property
    def hwm_decimal(self) -> Decimal:
        return Decimal(self.hwm)


def load_state(path: str = STATE_FILE_PATH) -> Optional[HwmState]:
    p = Path(path)
    if not p.exists():
        return None
    try:
        raw = json.loads(p.read_text())
        return HwmState(
            version=raw.get("version", 1),
            hwm=raw.get("hwm", str(INITIAL_HWM)),
            last_processed_period_index=raw.get("last_processed_period_index", -1),
            history=[PeriodRecord(**r) for r in raw.get("history", [])],
        )
    except Exception as exc:
        logger.error("Corrupt state file at %s: %s", path, exc)
        return None


def save_state(state: HwmState, path: str = STATE_FILE_PATH) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "version": state.version,
        "hwm": state.hwm,
        "last_processed_period_index": state.last_processed_period_index,
        "history": [asdict(r) for r in state.history],
    }
    p.write_text(json.dumps(data, indent=2))


def _tolerance() -> Decimal:
    return USDC_QUANTUM * Decimal("10")


def _transfers_for_period(
    ledger_transfers: list[FeeTransfer],
    period: Period,
) -> list[FeeTransfer]:
    """All fee-wallet transfers attributable to the given period.

    Window is [period.start, period.end + 1 day] — fees are paid
    shortly after period close.
    """
    return transfers_in_window(
        ledger_transfers, period.start_ms, period.end_ms + 60*60*24*1000
    )


def _match_ledger_transfer(
    fee_owed: Decimal,
    ledger_transfers: list[FeeTransfer],
) -> Optional[FeeTransfer]:
    for t in ledger_transfers:
        if abs(t.amount - fee_owed) <= _tolerance():
            return t
    return None


async def reconstruct_from_hyperliquid(
    trading_address: str,
    nav_fetcher,
    ledger_fetcher,
    now: datetime,
) -> HwmState:
    """Rebuild state by replaying closed periods.

    nav_fetcher(address, start_ms, end_ms) -> list[(ts_ms, Decimal)]
    ledger_fetcher(address, since_ms) -> list[FeeTransfer]

    Raises StateReconciliationError if ledger disagrees with calc beyond tolerance.
    """
    periods = closed_periods_before(now)
    state = HwmState()
    if not periods:
        return state

    ledger = await ledger_fetcher(trading_address, since_ms=periods[0].start_ms)
    consumed_tx_hashes: set[str] = set()

    hwm = INITIAL_HWM
    for period in periods:
        nav_series = await nav_fetcher(trading_address, period.start_ms, period.end_ms)
        if not nav_series:
            raise StateReconciliationError(
                f"No NAV data available for period {period.index} "
                f"({period.start.isoformat()} -> {period.end.isoformat()})"
            )

        result = compute_period(
            hwm_in=hwm,
            nav_series=nav_series,
            period_start=period.start,
            period_end=period.end,
        )

        period_transfers = [
            t
            for t in _transfers_for_period(ledger, period)
            if t.tx_hash not in consumed_tx_hashes
        ]

        if result.fee_owed > 0:
            matched = _match_ledger_transfer(result.fee_owed, period_transfers)
            if matched is None:
                raise StateReconciliationError(
                    f"Period {period.index}: calculator says fee owed "
                    f"{result.fee_owed} but no matching outbound transfer found on chain"
                )
            fee_paid = matched.amount
            tx_hash = matched.tx_hash
            consumed_tx_hashes.add(tx_hash)
        else:
            if period_transfers:
                raise StateReconciliationError(
                    f"Period {period.index}: calculator says no fee but chain shows "
                    f"{len(period_transfers)} transfer(s) to fee wallet "
                    f"(amounts: {[str(t.amount) for t in period_transfers]})"
                )
            fee_paid = Decimal("0")
            tx_hash = ""

        state.history.append(
            PeriodRecord.from_result(period.index, result, fee_paid, tx_hash)
        )
        hwm = result.hwm_out
        state.last_processed_period_index = period.index

    state.hwm = str(hwm)
    return state
