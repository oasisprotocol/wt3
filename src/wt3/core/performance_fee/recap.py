"""Quarterly performance-fee recap tweet generator.

Pure string formatting. The scheduler posts this via SocialClient._tweet.
"""

from decimal import Decimal

from .calculator import PeriodResult


def _fmt(x: Decimal) -> str:
    return f"${x:,.2f}"


def generate_recap(
    result: PeriodResult,
    fee_paid: Decimal,
    tx_hash: str,
) -> str:
    period_label = (
        f"{result.period_start.strftime('%b %d')}"
        f" - {result.period_end.strftime('%b %d, %Y')}"
    )
    lines = [
        f"Quarterly Performance Report: {period_label}",
        "",
        f"  Start NAV: {_fmt(result.start_nav)}",
        f"  End NAV:   {_fmt(result.end_nav)}",
        f"  Peak NAV:  {_fmt(result.peak_nav)}",
        f"  Prev HWM:  {_fmt(result.hwm_in)}",
    ]
    if fee_paid > 0:
        lines.append(f"  Fee paid:  {_fmt(fee_paid)} (30% catch-up above HWM)")
        if tx_hash:
            lines.append(f"  tx: {tx_hash}")
    else:
        lines.append("  Fee paid:  $0 (hurdle not cleared)")
    lines.append(f"  New HWM:   {_fmt(result.hwm_out)}")
    return "\n".join(lines)


def generate_halt_alert(
    period_index: int,
    reason: str,
    fee_owed: Decimal,
) -> str:
    return (
        f"WT3 performance-fee pipeline halted for period {period_index}.\n"
        f"  Fee owed: {_fmt(fee_owed)}\n"
        f"  Reason: {reason}\n"
        f"  HWM not advanced. Manual intervention required."
    )
