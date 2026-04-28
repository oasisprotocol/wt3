"""Performance-fee dry run against a live Hyperliquid wallet.

READ-ONLY. Fetches perp NAV from Hyperliquid, slices to a 3-month window,
and runs the pure calculator to show what the fee/HWM would have been.
Does NOT send any transfer, does NOT write any state file.

Usage:
    uv run python -m scripts.performance_fee_dry_run

Optional env:
    DRY_RUN_WALLET      default: 0xFc800e6e7147e544496D2DA73B4988916431B33a
    DRY_RUN_HWM_IN      default: 20000
    DRY_RUN_END_DATE    YYYY-MM-DD, default: today (UTC)
"""

import asyncio
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from wt3.core.performance_fee.calculator import compute_period
from wt3.core.performance_fee.config import (
    FEE_RATE,
    FEE_WALLET,
    HURDLE_PER_PERIOD,
)
from wt3.core.performance_fee.fee_ledger import (
    get_outbound_transfers,
    transfers_in_window,
)
from wt3.core.performance_fee.nav_source import fetch_perp_nav_window


DEFAULT_WALLET = "0xFc800e6e7147e544496D2DA73B4988916431B33a"


def _resolve_window() -> tuple[datetime, datetime]:
    end_str = os.getenv("DRY_RUN_END_DATE")
    if end_str:
        end = datetime.fromisoformat(end_str).replace(tzinfo=timezone.utc)
    else:
        end = datetime.now(timezone.utc).replace(
            hour=23, minute=59, second=59, microsecond=0
        )
    start = (end - timedelta(days=90)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return start, end


def _fmt_usd(x: Decimal) -> str:
    return f"${x:,.2f}"


async def main() -> None:
    wallet = os.getenv("DRY_RUN_WALLET", DEFAULT_WALLET)
    hwm_in = Decimal(os.getenv("DRY_RUN_HWM_IN", "20000"))
    period_start, period_end = _resolve_window()

    print("=" * 72)
    print("WT3 PERFORMANCE FEE DRY RUN — READ-ONLY, NO TRANSFERS")
    print("=" * 72)
    print(f"  Wallet:        {wallet}")
    print(f"  HWM (input):   {_fmt_usd(hwm_in)}")
    print(f"  Period start:  {period_start.isoformat()}")
    print(f"  Period end:    {period_end.isoformat()}")
    print(f"  Hurdle/period: {HURDLE_PER_PERIOD * 100:.4f}%")
    print(f"  Fee rate:      {FEE_RATE * 100:.1f}%")
    print(f"  Fee wallet:    {FEE_WALLET}")
    print()

    start_ms = int(period_start.timestamp() * 1000)
    end_ms = int(period_end.timestamp() * 1000)

    print("Fetching perp NAV window from Hyperliquid /info...")
    nav_series = await fetch_perp_nav_window(wallet, start_ms, end_ms)
    print(f"  -> {len(nav_series)} NAV samples in window")
    if nav_series:
        print(f"     first: {datetime.fromtimestamp(nav_series[0][0]/1000, tz=timezone.utc)} "
              f"NAV={_fmt_usd(nav_series[0][1])}")
        print(f"     last:  {datetime.fromtimestamp(nav_series[-1][0]/1000, tz=timezone.utc)} "
              f"NAV={_fmt_usd(nav_series[-1][1])}")
    print()

    if not nav_series:
        print("No NAV data available; aborting dry run.")
        return

    result = compute_period(
        hwm_in=hwm_in,
        nav_series=nav_series,
        period_start=period_start,
        period_end=period_end,
    )

    print("CALCULATOR RESULT")
    print("-" * 72)
    print(f"  start_nav:      {_fmt_usd(result.start_nav)}")
    print(f"  end_nav:        {_fmt_usd(result.end_nav)}")
    print(f"  peak_nav:       {_fmt_usd(result.peak_nav)}")
    print(f"  hwm_in:         {_fmt_usd(result.hwm_in)}")
    print(f"  hurdle_floor:   {_fmt_usd(result.hurdle_floor)}")
    print(f"  hurdle_cleared: {result.hurdle_cleared}")
    print(f"  FEE OWED:       {_fmt_usd(result.fee_owed)}")
    print(f"  hwm_out:        {_fmt_usd(result.hwm_out)}")
    print()

    change = result.end_nav - result.start_nav
    pct = (change / result.start_nav * 100) if result.start_nav else Decimal("0")
    print(f"  Raw period NAV change: {_fmt_usd(change)} ({pct:.2f}% of start_nav)")
    print()

    print("Checking on-chain outbound transfers to fee wallet in this window...")
    try:
        transfers = await get_outbound_transfers(wallet, since_ms=start_ms)
        in_window = transfers_in_window(transfers, start_ms, end_ms)
        if in_window:
            print(f"  Found {len(in_window)} outbound transfer(s) to {FEE_WALLET}:")
            for t in in_window:
                ts = datetime.fromtimestamp(t.timestamp_ms / 1000, tz=timezone.utc)
                print(f"    {ts.isoformat()}  {_fmt_usd(t.amount)}  tx={t.tx_hash}")
        else:
            print("  No outbound transfers to fee wallet in this window.")
    except Exception as exc:
        print(f"  Ledger check failed: {exc}")

    print()
    print("=" * 72)
    print("DRY RUN COMPLETE — no funds moved, no state written.")
    print("=" * 72)


if __name__ == "__main__":
    asyncio.run(main())
