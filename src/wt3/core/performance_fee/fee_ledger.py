"""On-chain fee-transfer ledger.

Reads historical outbound USDC transfers from the trading wallet to the
FEE_WALLET directly from Hyperliquid — the authoritative record.

Used for:
  1. Double-pay guard — before sending a fee, check no prior transfer for
     this period already exists on chain.
  2. State reconstruction — if /storage/data is lost, the ledger tells us
     which periods were already paid and how much, so HWM can be replayed
     deterministically.

Shape of delta entries relevant to us:
  { "time": <ms>, "hash": "0x...",
    "delta": {
      "type": "internalTransfer",
      "usdc": "<amount>",            # string
      "user": "0x...",               # sender, lowercase
      "destination": "0x...",        # recipient, lowercase
      "fee": "<amount>"
    } }
"""

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx

from .config import FEE_WALLET

logger = logging.getLogger(__name__)

HYPERLIQUID_INFO_URL = "https://api-ui.hyperliquid.xyz/info"


class FeeLedgerError(Exception):
    pass


@dataclass(frozen=True)
class FeeTransfer:
    timestamp_ms: int
    amount: Decimal
    tx_hash: str
    destination: str
    sender: str


async def get_outbound_transfers(
    trading_address: str,
    since_ms: int,
    to_address: str = FEE_WALLET,
) -> list[FeeTransfer]:
    """Return outbound internalTransfer entries from trading_address to to_address since since_ms."""
    payload = {
        "type": "userNonFundingLedgerUpdates",
        "user": trading_address,
        "startTime": since_ms,
    }
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                HYPERLIQUID_INFO_URL,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        raise FeeLedgerError(f"HTTP error fetching ledger: {exc}") from exc

    return _filter_outbound(data, trading_address, to_address)


def _filter_outbound(
    entries: list[Any],
    trading_address: str,
    to_address: str,
) -> list[FeeTransfer]:
    trading_lc = trading_address.lower()
    to_lc = to_address.lower()
    transfers: list[FeeTransfer] = []
    for entry in entries:
        delta = entry.get("delta", {})
        if delta.get("type") != "internalTransfer":
            continue
        if delta.get("user", "").lower() != trading_lc:
            continue
        if delta.get("destination", "").lower() != to_lc:
            continue
        try:
            amount = Decimal(str(delta.get("usdc", "0")))
        except Exception:
            logger.warning("Could not parse usdc amount in %s; skipping", entry)
            continue
        transfers.append(
            FeeTransfer(
                timestamp_ms=int(entry["time"]),
                amount=amount,
                tx_hash=str(entry.get("hash", "")),
                destination=to_lc,
                sender=trading_lc,
            )
        )
    return transfers


def transfers_in_window(
    transfers: list[FeeTransfer],
    start_ms: int,
    end_ms: int,
) -> list[FeeTransfer]:
    """Filter a transfer list to [start_ms, end_ms] inclusive."""
    return [t for t in transfers if start_ms <= t.timestamp_ms <= end_ms]
