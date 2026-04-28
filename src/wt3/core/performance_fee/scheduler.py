"""Quarterly fee scheduler.

Entry point: maybe_run_quarterly_fee(agent, now).

This is called ~once a day from the main event loop. It determines
whether any closed period needs processing and, if so:
  1. Loads / reconstructs HWM state from the zero-trust sources.
  2. Fetches NAV window for the closed period from Hyperliquid.
  3. Runs the pure calculator.
  4. Checks on-chain ledger for any already-paid fee in that window
     (double-pay guard).
  5. Verifies withdrawable USDC, transfers the fee, captures tx hash.
  6. Persists the updated state and tweets the recap.
  7. On ANY failure that prevents a confirmed transfer, HALTS the
     pipeline WITHOUT advancing HWM — Oasis/Moonward must intervene
     manually. State stays consistent.

Idempotency:
  - last_processed_period_index in state prevents re-processing a period.
  - Double-pay guard catches a transfer that happened out-of-band.
  - Transfer rounds down to 6 decimals, never overshooting.
"""

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from .calculator import compute_period
from .config import (
    FEE_WALLET,
    GRACE_SECONDS_AFTER_PERIOD_END,
)
from .fee_ledger import (
    FeeLedgerError,
    get_outbound_transfers,
    transfers_in_window,
)
from .hwm_state import (
    HwmState,
    PeriodRecord,
    load_state,
    reconstruct_from_hyperliquid,
    save_state,
)
from .nav_source import NavSourceError, fetch_perp_nav_window
from .periods import closed_periods_before, period_for_index
from .recap import generate_halt_alert, generate_recap
from .transfer import pay_fee

if TYPE_CHECKING:
    from ...__main__ import WT3Agent

logger = logging.getLogger(__name__)


async def _tweet_safe(text: str) -> None:
    """Post a tweet; swallow any social errors (fees must not depend on Twitter)."""
    try:
        from ...clients.social import SocialClient

        client = SocialClient()
        client._tweet(text)
    except Exception as exc:
        logger.error("Failed to post recap tweet: %s", exc)


async def maybe_run_quarterly_fee(
    agent: "WT3Agent",
    now: datetime,
    *,
    nav_fetcher=fetch_perp_nav_window,
    ledger_fetcher=get_outbound_transfers,
    transfer_fn=pay_fee,
    state_loader=load_state,
    state_saver=save_state,
    state_reconstructor=reconstruct_from_hyperliquid,
    tweet_fn=_tweet_safe,
) -> None:
    """Runs the fee pipeline if a new period has closed.

    All external dependencies are injectable for testability.
    """
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    closed = closed_periods_before(now)
    if not closed:
        logger.debug("No closed periods yet (before START_DATE or mid-first-period)")
        return

    trading_address = agent.trading_tools.exchange_client.wallet.address

    state = state_loader()
    if state is None:
        logger.warning("HWM state cache missing; reconstructing from Hyperliquid")
        try:
            state = await state_reconstructor(
                trading_address, nav_fetcher, ledger_fetcher, now
            )
        except Exception as exc:
            logger.error("Reconstruction failed: %s", exc)
            await tweet_fn(generate_halt_alert(-1, f"Reconstruction failed: {exc}", Decimal("0")))
            return
        state_saver(state)

    next_index = state.last_processed_period_index + 1
    target_period = next(
        (p for p in closed if p.index == next_index and _past_grace(p.end, now)),
        None,
    )
    if target_period is None:
        logger.debug(
            "No new period due; last_processed=%d, now=%s",
            state.last_processed_period_index,
            now.isoformat(),
        )
        return

    logger.info(
        "Processing period %d (%s -> %s)",
        target_period.index,
        target_period.start.isoformat(),
        target_period.end.isoformat(),
    )

    try:
        nav_series = await nav_fetcher(
            trading_address, target_period.start_ms, target_period.end_ms
        )
    except NavSourceError as exc:
        logger.error("NAV fetch failed for period %d: %s", target_period.index, exc)
        await tweet_fn(
            generate_halt_alert(target_period.index, f"NAV fetch failed: {exc}", Decimal("0"))
        )
        return

    if not nav_series:
        logger.error("No NAV data for period %d", target_period.index)
        await tweet_fn(
            generate_halt_alert(target_period.index, "No NAV data available", Decimal("0"))
        )
        return

    result = compute_period(
        hwm_in=state.hwm_decimal,
        nav_series=nav_series,
        period_start=target_period.start,
        period_end=target_period.end,
    )

    try:
        existing_transfers = await ledger_fetcher(
            trading_address, since_ms=target_period.start_ms
        )
    except FeeLedgerError as exc:
        logger.error("Ledger fetch failed: %s", exc)
        await tweet_fn(
            generate_halt_alert(
                target_period.index, f"Ledger fetch failed: {exc}", result.fee_owed
            )
        )
        return

    guard_window_end_ms = target_period.end_ms + 86_400_000
    in_guard_window = transfers_in_window(
        existing_transfers, target_period.start_ms, guard_window_end_ms
    )
    already_paid = next(
        (t for t in in_guard_window if abs(t.amount - result.fee_owed) <= Decimal("0.00001")),
        None,
    )

    if already_paid is not None and result.fee_owed > 0:
        logger.warning(
            "Fee for period %d already paid on-chain (tx=%s); skipping transfer",
            target_period.index,
            already_paid.tx_hash,
        )
        fee_paid = already_paid.amount
        tx_hash = already_paid.tx_hash
    elif result.fee_owed > 0:
        transfer_result = await transfer_fn(
            agent.trading_tools.exchange_client.exchange,
            agent.trading_tools.exchange_client.info,
            trading_address,
            result.fee_owed,
            destination=FEE_WALLET,
        )
        if not transfer_result.success:
            logger.error(
                "Transfer failed for period %d: %s",
                target_period.index,
                transfer_result.error,
            )
            await tweet_fn(
                generate_halt_alert(
                    target_period.index,
                    f"Transfer failed: {transfer_result.error}",
                    result.fee_owed,
                )
            )
            return
        fee_paid = transfer_result.amount_transferred
        tx_hash = transfer_result.tx_hash
    else:
        fee_paid = Decimal("0")
        tx_hash = ""

    state.history.append(
        PeriodRecord.from_result(target_period.index, result, fee_paid, tx_hash)
    )
    state.hwm = str(result.hwm_out)
    state.last_processed_period_index = target_period.index
    state_saver(state)

    await tweet_fn(generate_recap(result, fee_paid, tx_hash))
    logger.info(
        "Period %d processed: fee_paid=%s, hwm_out=%s",
        target_period.index,
        fee_paid,
        result.hwm_out,
    )


def _past_grace(period_end: datetime, now: datetime) -> bool:
    return now >= period_end + timedelta(seconds=GRACE_SECONDS_AFTER_PERIOD_END)
