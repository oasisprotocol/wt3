"""
Hourly recap handling for the WT3 Agent.

This module handles the generation and posting of hourly trading recaps
to social media platforms.
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from ...core.trading import TradeTools, TradingError
from ...clients.social import SocialClient, SocialClientError
from .state_management import TradingStateError

if TYPE_CHECKING:
    from ...__main__ import WT3Agent

logger = logging.getLogger(__name__)


async def post_hourly_recap(agent: 'WT3Agent', coin: str) -> None:
    """Post a recap tweet with the trading activities from the last hour.
    
    This function:
    1. Collects trading activities from the last hour
    2. Calculates current position and PnL
    3. Generates and posts a summary tweet
    
    Args:
        agent (WT3Agent): The trading agent instance
        coin (str): The trading pair symbol
    
    Raises:
        TradingError: If trade data retrieval fails
        SocialClientError: If social media operations fail
        TradingStateError: If state management fails
    """
    logger.debug("Starting hourly recap process")
    logger.debug(f"Number of trade activities: {len(agent.trading_state.trade_activities)}")
    logger.debug(f"Last tweet time: {agent.trading_state.last_tweet_time}")
    
    tweet_tool = SocialClient()
    trade_tools = TradeTools()
    
    max_retries = 3
    retry_delay = 60
    
    for attempt in range(max_retries):
        try:
            position_size = await trade_tools.get_position_size(coin)
            current_price = await trade_tools.get_current_price(coin)
            
            logger.debug(f"Current position size: {position_size} {coin}")
            try:
                price_change_pct_1h = await trade_tools.get_price_change_1h(coin)
            except Exception as e:
                logger.warning(f"Could not get 1h price change: {e}")
                price_change_pct_1h = 0
            
            current_hour = datetime.now().hour
            if 0 <= current_hour < 8:
                market_session = "Asian"
            elif 8 <= current_hour < 16:
                market_session = "European"
            else:
                market_session = "US"
            
            if position_size != 0:
                is_long = position_size > 0
                position_type = "LONG" if is_long else "SHORT"
                entry_price = await trade_tools.get_entry_price(coin)
                position_value = abs(position_size) * current_price
                
                if is_long:
                    pnl_percent = (current_price - entry_price) / entry_price * 100
                else:
                    pnl_percent = (entry_price - current_price) / entry_price * 100
                
                position_age_hours = 1
                
                position_info = {
                    "has_position": True,
                    "coin": coin.upper(),
                    "direction": position_type,
                    "position_size": abs(position_size),
                    "position_value": position_value,
                    "entry_price": entry_price,
                    "current_price": current_price,
                    "pnl_percent": pnl_percent,
                    "price_change_1h": price_change_pct_1h,
                    "market_session": market_session,
                    "position_age_hours": position_age_hours
                }
            else:
                position_info = {
                    "has_position": False,
                    "coin": coin.upper(),
                    "current_price": current_price,
                    "price_change_1h": price_change_pct_1h,
                    "market_session": market_session
                }
            
            activity_counts = {
                "open_order_placed": 0,
                "reverse": 0,
                "hold": 0,
                "no_action": 0,
                "failed": 0,
                "error": 0,
                "close": 0,
                "executed": 0
            }
            
            if position_size != 0:
                activity_counts["hold"] = 1
                logger.info(f"Adding hold activity for current {position_type} position")
            
            if agent.trading_state.trade_activities:
                oldest_timestamp = min([activity["timestamp"] for activity in agent.trading_state.trade_activities])
                time_span = datetime.now() - oldest_timestamp
                
                for activity in agent.trading_state.trade_activities:
                    action = activity.get("action", "unknown")
                    if action in activity_counts:
                        activity_counts[action] += 1
            else:
                time_span = timedelta(hours=1)
            
            activities_summary = {
                "counts": activity_counts,
                "time_span": time_span,
                "total": sum(activity_counts.values())
            }
            
            logger.info("Generating and posting hourly recap tweet")
            tweet_result = await tweet_tool.generate_hourly_recap(
                position_info=position_info,
                activities_summary=activities_summary
            )
            
            logger.info(f"Hourly recap tweet posted: {tweet_result}")
            
            logger.debug("Trade activities cleared after posting recap")
            agent.trading_state.clear_activities()
            agent.trading_state.last_tweet_time = datetime.now()
            return
            
        except (TradingError, SocialClientError, TradingStateError) as e:
            if attempt < max_retries - 1:
                logger.warning(f"Error posting hourly recap (attempt {attempt + 1}/{max_retries}): {str(e)}")
                logger.info(f"Retrying in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
            else:
                error_msg = f"Failed to post hourly recap after all retries: {str(e)}"
                logger.error(error_msg)
                raise