"""Fee transfer via Hyperliquid usd_transfer.

Wraps exchange.usd_transfer with:
  - Round-down to USDC 6-decimal precision (never over-transfer).
  - Withdrawable-balance check before attempting.
  - Retry with exponential backoff on transient failures.
  - Structured result so the scheduler can halt cleanly on failure.

The actual on-chain action is exchange.usd_transfer(amount: float, destination: str)
from the Hyperliquid SDK (hyperliquid/exchange.py:506). It uses the ROFL-signed
trading wallet to send USDC on the L1 directly to the fee wallet.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from typing import Any, Optional

from .config import FEE_WALLET, MAX_TRANSFER_RETRIES, USDC_QUANTUM

logger = logging.getLogger(__name__)


class TransferError(Exception):
    pass


@dataclass(frozen=True)
class TransferResult:
    success: bool
    amount_requested: Decimal
    amount_transferred: Decimal
    tx_hash: str
    error: Optional[str] = None


def round_down_to_usdc(amount: Decimal) -> Decimal:
    return amount.quantize(USDC_QUANTUM, rounding=ROUND_DOWN)


def get_withdrawable_usdc(info: Any, wallet_address: str) -> Decimal:
    """Perps withdrawable USDC for the given address."""
    user_state = info.user_state(wallet_address)
    return Decimal(str(user_state.get("withdrawable", "0")))


def _extract_tx_hash(response: dict[str, Any]) -> str:
    """Best-effort tx-hash extraction from Hyperliquid response."""
    if not isinstance(response, dict):
        return ""
    resp = response.get("response", {})
    data = resp.get("data", {})
    if isinstance(data, dict):
        statuses = data.get("statuses", [])
        if statuses and isinstance(statuses[0], dict):
            return statuses[0].get("hash", "")
    return ""


async def pay_fee(
    exchange: Any,
    info: Any,
    trading_address: str,
    amount: Decimal,
    destination: str = FEE_WALLET,
    max_retries: int = MAX_TRANSFER_RETRIES,
) -> TransferResult:
    """Transfer amount USDC from trading wallet to destination.

    Returns TransferResult with success=False on permanent failure. Caller MUST
    halt the fee pipeline and NOT advance HWM if success is False.
    """
    rounded = round_down_to_usdc(amount)
    if rounded <= 0:
        return TransferResult(
            success=False,
            amount_requested=amount,
            amount_transferred=Decimal("0"),
            tx_hash="",
            error="Rounded amount is zero or negative",
        )

    try:
        withdrawable = get_withdrawable_usdc(info, trading_address)
    except Exception as exc:
        return TransferResult(
            success=False,
            amount_requested=amount,
            amount_transferred=Decimal("0"),
            tx_hash="",
            error=f"Failed to read withdrawable USDC: {exc}",
        )

    if withdrawable < rounded:
        return TransferResult(
            success=False,
            amount_requested=amount,
            amount_transferred=Decimal("0"),
            tx_hash="",
            error=(
                f"Insufficient USDC: withdrawable={withdrawable} < required={rounded}. "
                "Halting fee transfer; positions must be closed to free balance."
            ),
        )

    last_error: Optional[str] = None
    for attempt in range(1, max_retries + 1):
        try:
            response = await asyncio.to_thread(
                exchange.usd_transfer, float(rounded), destination
            )
            status = response.get("status") if isinstance(response, dict) else None
            if status != "ok":
                last_error = f"Non-ok response: {response}"
                logger.warning(
                    "Transfer attempt %d/%d returned non-ok: %s",
                    attempt,
                    max_retries,
                    response,
                )
            else:
                tx_hash = _extract_tx_hash(response)
                logger.info(
                    "Transferred %s USDC to %s (tx=%s)", rounded, destination, tx_hash
                )
                return TransferResult(
                    success=True,
                    amount_requested=amount,
                    amount_transferred=rounded,
                    tx_hash=tx_hash,
                )
        except Exception as exc:
            last_error = str(exc)
            logger.warning("Transfer attempt %d/%d raised: %s", attempt, max_retries, exc)

        if attempt < max_retries:
            await asyncio.sleep(2**attempt)

    return TransferResult(
        success=False,
        amount_requested=amount,
        amount_transferred=Decimal("0"),
        tx_hash="",
        error=last_error or "Exhausted retries",
    )
