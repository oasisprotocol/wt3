"""NAV source adapter.

Fetches perp-only NAV timeseries from Hyperliquid's public /info portfolio
endpoint and slices it to a specified [start_ts, end_ts] window.

Perps-only is intentional: the fee agreement is on trading profits, not
staked HYPE or HLP vault yield. We therefore read `perpMonth` and
`perpAllTime` (not the all-inclusive `month`/`allTime` keys).

Sampling reality (confirmed via live API):
    perpMonth    ~15 min – 26h per point (~46 points spanning ~30 days)
    perpAllTime  ~6 days per point

The caller decides which bucket to use based on how far back the window is.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from ...clients.pnl import PnLClient, PnLClientError

logger = logging.getLogger(__name__)


class NavSourceError(Exception):
    pass


def _extract_perp_history(
    portfolio: dict[str, Any],
    bucket_key: str,
) -> list[tuple[int, Decimal]]:
    """Pull accountValueHistory from a portfolio bucket, as [(ts_ms, Decimal)]."""
    bucket = portfolio.get(bucket_key)
    if not bucket:
        return []
    history = bucket.get("accountValueHistory", [])
    return [(int(ts), Decimal(str(nav))) for ts, nav in history]


def _slice_to_window(
    series: list[tuple[int, Decimal]],
    start_ts_ms: int,
    end_ts_ms: int,
) -> list[tuple[int, Decimal]]:
    """Return points with timestamp in [start_ts_ms, end_ts_ms] inclusive."""
    return [(ts, nav) for ts, nav in series if start_ts_ms <= ts <= end_ts_ms]


async def fetch_perp_nav_window(
    user_address: str,
    start_ts_ms: int,
    end_ts_ms: int,
) -> list[tuple[int, Decimal]]:
    """Fetch perp NAV timeseries for a wallet, clipped to the given window.

    Strategy:
    - Always fetch the full portfolio.
    - Prefer perpMonth when the window's start is within ~35 days of now
      (finer sampling).
    - Fall back to perpAllTime otherwise (coarser, ~6-day sampling).

    Raises NavSourceError if no data is available for the window.
    """
    try:
        client = PnLClient(user_address)
        portfolio = await client.get_portfolio_data()
    except PnLClientError as exc:
        raise NavSourceError(f"Failed to fetch portfolio: {exc}") from exc

    perp_month = _extract_perp_history(portfolio, "month")
    perp_alltime = _extract_perp_history(portfolio, "allTime")

    window_from_month = _slice_to_window(perp_month, start_ts_ms, end_ts_ms)

    if window_from_month and perp_month and perp_month[0][0] <= start_ts_ms:
        logger.info(
            "Using perpMonth for NAV window: %d points", len(window_from_month)
        )
        return window_from_month

    window_from_alltime = _slice_to_window(perp_alltime, start_ts_ms, end_ts_ms)
    if window_from_alltime:
        logger.info(
            "Using perpAllTime for NAV window (coarse sampling): %d points",
            len(window_from_alltime),
        )
        return window_from_alltime

    if window_from_month:
        logger.warning(
            "perpAllTime missing data; falling back to partial perpMonth: %d points",
            len(window_from_month),
        )
        return window_from_month

    raise NavSourceError(
        f"No NAV data available for window [{start_ts_ms}, {end_ts_ms}] "
        f"(user={user_address})"
    )
