"""Tests for HWM state load/save and reconstruction."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from wt3.core.performance_fee.fee_ledger import FeeTransfer
from wt3.core.performance_fee.hwm_state import (
    HwmState,
    PeriodRecord,
    StateReconciliationError,
    load_state,
    reconstruct_from_hyperliquid,
    save_state,
)
from wt3.core.performance_fee.periods import period_for_index


def _series_for_period(period, values: list[str]) -> list[tuple[int, Decimal]]:
    base = period.start_ms
    step = (period.end_ms - period.start_ms) // max(len(values) - 1, 1)
    return [(base + i * step, Decimal(v)) for i, v in enumerate(values)]


class TestLoadSaveRoundtrip:

    def test_save_then_load_preserves_fields(self, tmp_path: Path):
        path = str(tmp_path / "state.json")
        state = HwmState(
            hwm="21400",
            last_processed_period_index=0,
            history=[
                PeriodRecord(
                    period_index=0,
                    period_start="2026-05-01T00:00:00+00:00",
                    period_end="2026-07-31T23:59:59+00:00",
                    start_nav="20000",
                    end_nav="22000",
                    peak_nav="22500",
                    hwm_in="20000",
                    hurdle_floor="20250",
                    hurdle_cleared=True,
                    fee_owed="600",
                    fee_paid="600",
                    hwm_out="21400",
                    tx_hash="0xabc",
                    computed_at="2026-08-01T01:00:00+00:00",
                )
            ],
        )
        save_state(state, path)
        loaded = load_state(path)
        assert loaded is not None
        assert loaded.hwm == "21400"
        assert loaded.last_processed_period_index == 0
        assert len(loaded.history) == 1
        assert loaded.history[0].fee_owed == "600"
        assert loaded.history[0].tx_hash == "0xabc"

    def test_load_missing_returns_none(self, tmp_path: Path):
        assert load_state(str(tmp_path / "does-not-exist.json")) is None

    def test_load_corrupt_returns_none(self, tmp_path: Path):
        path = tmp_path / "state.json"
        path.write_text("not valid json {{{")
        assert load_state(str(path)) is None


class TestReconstruction:

    def test_no_closed_periods_returns_initial_state(self):
        async def nav_fetcher(addr, s, e):
            return []

        async def ledger_fetcher(addr, since_ms):
            return []

        now = datetime(2026, 5, 1, tzinfo=timezone.utc)
        state = asyncio.run(
            reconstruct_from_hyperliquid(
                "0xabc", nav_fetcher, ledger_fetcher, now
            )
        )
        assert state.hwm == "20000"
        assert state.last_processed_period_index == -1
        assert state.history == []

    def test_replays_losing_period_no_fee_no_ledger_entry(self):
        p0 = period_for_index(0)

        async def nav_fetcher(addr, s, e):
            return _series_for_period(p0, ["20000", "19000", "19500"])

        async def ledger_fetcher(addr, since_ms):
            return []

        now = datetime(2026, 8, 1, 1, 0, 0, tzinfo=timezone.utc)
        state = asyncio.run(
            reconstruct_from_hyperliquid(
                "0xabc", nav_fetcher, ledger_fetcher, now
            )
        )
        assert state.last_processed_period_index == 0
        assert len(state.history) == 1
        assert state.history[0].fee_owed == "0"
        assert state.history[0].fee_paid == "0"
        assert Decimal(state.hwm) == Decimal("20250")

    def test_replays_winning_period_with_matching_ledger_entry(self):
        p0 = period_for_index(0)

        async def nav_fetcher(addr, s, e):
            return _series_for_period(p0, ["20000", "22000", "22000"])

        matched_transfer = FeeTransfer(
            timestamp_ms=p0.end_ms + 1000,
            amount=Decimal("600"),
            tx_hash="0xfee01",
            destination="0xbf5f64d05e36a34bf43ea95e99657b09e4c7a1bb",
            sender="0xabc",
        )

        async def ledger_fetcher(addr, since_ms):
            return [matched_transfer]

        now = datetime(2026, 8, 2, tzinfo=timezone.utc)
        state = asyncio.run(
            reconstruct_from_hyperliquid(
                "0xabc", nav_fetcher, ledger_fetcher, now
            )
        )
        assert state.last_processed_period_index == 0
        assert Decimal(state.history[0].fee_owed) == Decimal("600")
        assert Decimal(state.history[0].fee_paid) == Decimal("600")
        assert state.history[0].tx_hash == "0xfee01"
        assert Decimal(state.hwm) == Decimal("21400")

    def test_fee_owed_but_no_transfer_raises(self):
        p0 = period_for_index(0)

        async def nav_fetcher(addr, s, e):
            return _series_for_period(p0, ["20000", "22000", "22000"])

        async def ledger_fetcher(addr, since_ms):
            return []

        now = datetime(2026, 8, 2, tzinfo=timezone.utc)
        with pytest.raises(StateReconciliationError, match="no matching outbound"):
            asyncio.run(
                reconstruct_from_hyperliquid(
                    "0xabc", nav_fetcher, ledger_fetcher, now
                )
            )

    def test_transfer_but_no_fee_owed_raises(self):
        p0 = period_for_index(0)

        async def nav_fetcher(addr, s, e):
            return _series_for_period(p0, ["20000", "19500"])

        async def ledger_fetcher(addr, since_ms):
            return [
                FeeTransfer(
                    timestamp_ms=p0.end_ms + 1000,
                    amount=Decimal("500"),
                    tx_hash="0xbad",
                    destination="0xbf5f64d05e36a34bf43ea95e99657b09e4c7a1bb",
                    sender="0xabc",
                )
            ]

        now = datetime(2026, 8, 2, tzinfo=timezone.utc)
        with pytest.raises(StateReconciliationError, match="chain shows"):
            asyncio.run(
                reconstruct_from_hyperliquid(
                    "0xabc", nav_fetcher, ledger_fetcher, now
                )
            )

    def test_two_period_replay(self):
        p0 = period_for_index(0)
        p1 = period_for_index(1)

        async def nav_fetcher(addr, start_ms, end_ms):
            if start_ms == p0.start_ms:
                return _series_for_period(p0, ["20000", "22000"])
            if start_ms == p1.start_ms:
                return _series_for_period(p1, ["21400", "21000"])
            return []

        async def ledger_fetcher(addr, since_ms):
            return [
                FeeTransfer(
                    timestamp_ms=p0.end_ms + 1000,
                    amount=Decimal("600"),
                    tx_hash="0xp0",
                    destination="0xbf5f64d05e36a34bf43ea95e99657b09e4c7a1bb",
                    sender="0xabc",
                )
            ]

        now = datetime(2026, 11, 1, 1, 0, 0, tzinfo=timezone.utc)
        state = asyncio.run(
            reconstruct_from_hyperliquid(
                "0xabc", nav_fetcher, ledger_fetcher, now
            )
        )
        assert state.last_processed_period_index == 1
        assert len(state.history) == 2
        assert Decimal(state.history[0].fee_owed) == Decimal("600")
        assert Decimal(state.history[1].fee_owed) == Decimal("0")
        expected = Decimal("21400") * (Decimal("1") + (Decimal("0.05") / Decimal("4")))
        assert Decimal(state.hwm) == expected
