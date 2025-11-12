"""
PnL client for fetching portfolio performance data from Hyperliquid.

This module provides functionality for retrieving profit and loss data
from the Hyperliquid exchange API.
"""

import httpx
import logging
from typing import Dict, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class PnLClientError(Exception):
    """Base exception for PnL Client errors."""
    pass


class PnLClient:
    """Client for fetching portfolio performance data from Hyperliquid.

    This class handles retrieving PnL and account value data from the
    Hyperliquid API for a specific wallet address.

    Attributes:
        api_url (str): The Hyperliquid API endpoint
        user_address (str): The wallet address to fetch data for
    """

    API_URL = "https://api-ui.hyperliquid.xyz/info"

    def __init__(self, user_address: str):
        """Initialize the PnL client.

        Args:
            user_address (str): The wallet address to fetch PnL data for
        """
        self.user_address = user_address
        logger.info(f"Initialized PnL client for address: {user_address}")

    async def get_portfolio_data(self) -> Dict[str, Any]:
        """Fetch complete portfolio data from Hyperliquid API.

        Returns:
            Dict[str, Any]: Portfolio data containing day, week, month, and allTime stats

        Raises:
            PnLClientError: If API request fails
        """
        try:
            payload = {
                "type": "portfolio",
                "user": self.user_address
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.API_URL,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=30.0
                )
                response.raise_for_status()

            data = response.json()

            portfolio = {
                "day": None,
                "week": None,
                "month": None
            }

            perp_mapping = {
                "perpDay": "day",
                "perpWeek": "week",
                "perpMonth": "month"
            }

            for item in data:
                if isinstance(item, list) and len(item) == 2:
                    period_name = item[0]
                    period_data = item[1]

                    if period_name in perp_mapping:
                        portfolio[perp_mapping[period_name]] = period_data

            logger.info("Successfully fetched perps portfolio data")
            return portfolio

        except httpx.HTTPError as e:
            error_msg = f"HTTP error fetching portfolio data: {str(e)}"
            logger.error(error_msg)
            raise PnLClientError(error_msg)
        except Exception as e:
            error_msg = f"Error fetching portfolio data: {str(e)}"
            logger.error(error_msg)
            raise PnLClientError(error_msg)

    def _get_latest_value(self, history: list) -> Optional[float]:
        """Extract the latest value from a history array.

        Args:
            history (list): Array of [timestamp, value] pairs

        Returns:
            Optional[float]: The latest value, or None if history is empty
        """
        if not history:
            return None
        return float(history[-1][1])

    async def get_pnl_summary(self) -> Dict[str, Any]:
        """Get a summary of PnL across different time periods.

        Returns:
            Dict[str, Any]: Summary containing PnL and account values for each period

        Raises:
            PnLClientError: If data fetching fails
        """
        try:
            portfolio = await self.get_portfolio_data()

            summary = {
                "timestamp": datetime.utcnow().isoformat(),
                "user_address": self.user_address,
                "periods": {}
            }

            for period_name in ["day", "week", "month", "allTime"]:
                period_data = portfolio.get(period_name)

                if period_data:
                    pnl_history = period_data.get("pnlHistory", [])
                    account_history = period_data.get("accountValueHistory", [])
                    volume = period_data.get("vlm", "0")

                    current_pnl = self._get_latest_value(pnl_history)
                    current_value = self._get_latest_value(account_history)

                    start_value = None
                    if account_history:
                        start_value = float(account_history[0][1])

                    pnl_percent = None
                    if start_value and start_value != 0 and current_pnl is not None:
                        pnl_percent = (current_pnl / start_value) * 100

                    summary["periods"][period_name] = {
                        "pnl": current_pnl,
                        "pnl_percent": pnl_percent,
                        "account_value": current_value,
                        "start_value": start_value,
                        "volume": float(volume)
                    }

            logger.info(f"Generated PnL summary: {summary['periods']}")
            return summary

        except PnLClientError:
            raise
        except Exception as e:
            error_msg = f"Error generating PnL summary: {str(e)}"
            logger.error(error_msg)
            raise PnLClientError(error_msg)
