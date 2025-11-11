"""
PnL recap handling for the WT3 Agent.

This module handles the generation and posting of PnL performance recaps
to social media platforms on a daily, weekly, and monthly basis.
"""

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Dict, Any

from ...clients.pnl import PnLClient, PnLClientError
from ...clients.social import SocialClient, SocialClientError
from ...clients.rofl import get_keypair, WT3_TRADING_KEY

if TYPE_CHECKING:
    from ...__main__ import WT3Agent

logger = logging.getLogger(__name__)


async def post_pnl_recap(agent: 'WT3Agent', period: str) -> None:
    """Post a PnL recap tweet for the specified time period.

    This function:
    1. Fetches PnL data from Hyperliquid for the specified period
    2. Formats the data into a tweet-worthy summary
    3. Posts the recap to social media

    Args:
        agent (WT3Agent): The trading agent instance
        period (str): The time period ("day", "week", or "month")

    Raises:
        PnLClientError: If PnL data retrieval fails
        SocialClientError: If social media operations fail
    """
    logger.info(f"Starting {period}ly PnL recap process")

    try:
        _, wallet_address = get_keypair(WT3_TRADING_KEY)

        pnl_client = PnLClient(wallet_address)

        pnl_summary = await pnl_client.get_pnl_summary()

        period_data = pnl_summary["periods"].get(period)

        if not period_data:
            logger.warning(f"No {period}ly PnL data available")
            return

        tweet_content = await _generate_pnl_tweet(period, period_data)

        social_client = SocialClient()
        result = social_client._tweet(tweet_content)

        if period == "day":
            agent.trading_state.last_daily_pnl_time = datetime.utcnow()
        elif period == "week":
            agent.trading_state.last_weekly_pnl_time = datetime.utcnow()
        elif period == "month":
            agent.trading_state.last_monthly_pnl_time = datetime.utcnow()

        logger.info(f"Successfully posted {period}ly PnL recap: {result}")

    except (PnLClientError, SocialClientError) as e:
        logger.error(f"Error posting {period}ly PnL recap: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in {period}ly PnL recap: {str(e)}")
        raise


async def _generate_pnl_tweet(period: str, period_data: Dict[str, Any]) -> str:
    """Generate a tweet about PnL performance.

    Args:
        period (str): The time period ("day", "week", or "month")
        period_data (Dict[str, Any]): PnL data for the period

    Returns:
        str: Generated tweet content

    Raises:
        ValueError: If period data is invalid
    """
    pnl = period_data.get("pnl", 0)
    pnl_percent = period_data.get("pnl_percent", 0)
    account_value = period_data.get("account_value", 0)
    volume = period_data.get("volume", 0)

    period_label = {
        "day": "Daily",
        "week": "Weekly",
        "month": "Monthly"
    }

    label = period_label.get(period, period.title())
    pnl_sign = "+" if pnl >= 0 else ""

    tweet = (
        f"{label} PnL Report:\n"
        f"  - P&L: {pnl_sign}${pnl:,.2f} ({pnl_sign}{pnl_percent:.2f}%)\n"
        f"  - Perps Value: ${account_value:,.2f}\n"
        f"  - Volume: ${volume:,.2f}"
    )

    logger.info(f"Generated {period}ly PnL tweet: {tweet}")
    return tweet
