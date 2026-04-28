"""Tests for NAV source window slicing, bucket selection, and the
async fetch_perp_nav_window adapter.
"""

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from wt3.clients.pnl import PnLClientError
from wt3.core.performance_fee.nav_source import (
    NavSourceError,
    _extract_perp_history,
    _slice_to_window,
    fetch_perp_nav_window,
)


class TestExtractPerpHistory:

    def test_missing_bucket_returns_empty(self):
        assert _extract_perp_history({}, "month") == []

    def test_null_bucket_returns_empty(self):
        assert _extract_perp_history({"month": None}, "month") == []

    def test_missing_history_returns_empty(self):
        assert _extract_perp_history({"month": {}}, "month") == []

    def test_typical_bucket_parses_to_decimals(self):
        bucket = {
            "month": {
                "accountValueHistory": [
                    [1000, "20000.5"],
                    [2000, "20100.25"],
                ]
            }
        }
        result = _extract_perp_history(bucket, "month")
        assert result == [
            (1000, Decimal("20000.5")),
            (2000, Decimal("20100.25")),
        ]

    def test_string_floats_preserved_through_decimal(self):
        bucket = {
            "allTime": {
                "accountValueHistory": [[1, "20500.555555"]],
            }
        }
        result = _extract_perp_history(bucket, "allTime")
        assert result[0][1] == Decimal("20500.555555")


class TestSliceToWindow:

    def test_inclusive_bounds(self):
        series = [(100, Decimal("1")), (200, Decimal("2")), (300, Decimal("3"))]
        assert _slice_to_window(series, 100, 300) == series

    def test_clips_before_start(self):
        series = [(100, Decimal("1")), (200, Decimal("2")), (300, Decimal("3"))]
        assert _slice_to_window(series, 150, 300) == [
            (200, Decimal("2")),
            (300, Decimal("3")),
        ]

    def test_clips_after_end(self):
        series = [(100, Decimal("1")), (200, Decimal("2")), (300, Decimal("3"))]
        assert _slice_to_window(series, 100, 250) == [
            (100, Decimal("1")),
            (200, Decimal("2")),
        ]

    def test_empty_series(self):
        assert _slice_to_window([], 0, 1000) == []

    def test_no_points_in_window(self):
        series = [(100, Decimal("1")), (200, Decimal("2"))]
        assert _slice_to_window(series, 500, 1000) == []


def _portfolio(month_history, all_time_history):
    return {
        "month": {"accountValueHistory": month_history},
        "allTime": {"accountValueHistory": all_time_history},
    }


def _patch_pnl_client(portfolio_or_exc):
    """Patch the PnLClient symbol used inside nav_source.

    Pass a dict to make get_portfolio_data return it; pass an Exception
    instance to make it raise.
    """
    patcher = patch("wt3.core.performance_fee.nav_source.PnLClient")
    mock_class = patcher.start()
    if isinstance(portfolio_or_exc, Exception):
        mock_class.return_value.get_portfolio_data = AsyncMock(side_effect=portfolio_or_exc)
    else:
        mock_class.return_value.get_portfolio_data = AsyncMock(return_value=portfolio_or_exc)
    return patcher


class TestFetchPerpNavWindow:

    def test_uses_perpmonth_when_window_recent(self):
        portfolio = _portfolio(
            month_history=[
                [1000, "20000"], [1500, "20100"], [2000, "20200"]
            ],
            all_time_history=[
                [500, "0"], [3000, "20300"]
            ],
        )
        patcher = _patch_pnl_client(portfolio)
        try:
            result = asyncio.run(fetch_perp_nav_window("0xabc", 1000, 2000))
        finally:
            patcher.stop()
        assert result == [
            (1000, Decimal("20000")),
            (1500, Decimal("20100")),
            (2000, Decimal("20200")),
        ]

    def test_falls_back_to_perpalltime_for_old_window(self):
        portfolio = _portfolio(
            month_history=[
                [10000, "20000"], [20000, "20100"]
            ],
            all_time_history=[
                [100, "0"], [500, "5000"], [1000, "10000"], [10000, "20000"]
            ],
        )
        patcher = _patch_pnl_client(portfolio)
        try:
            result = asyncio.run(fetch_perp_nav_window("0xabc", 100, 1000))
        finally:
            patcher.stop()
        assert result == [
            (100, Decimal("0")),
            (500, Decimal("5000")),
            (1000, Decimal("10000")),
        ]

    def test_raises_when_no_data_in_window(self):
        portfolio = _portfolio(month_history=[], all_time_history=[])
        patcher = _patch_pnl_client(portfolio)
        try:
            with pytest.raises(NavSourceError, match="No NAV data"):
                asyncio.run(fetch_perp_nav_window("0xabc", 100, 1000))
        finally:
            patcher.stop()

    def test_propagates_pnl_client_error_as_nav_source_error(self):
        patcher = _patch_pnl_client(PnLClientError("boom"))
        try:
            with pytest.raises(NavSourceError, match="Failed to fetch portfolio"):
                asyncio.run(fetch_perp_nav_window("0xabc", 100, 1000))
        finally:
            patcher.stop()
