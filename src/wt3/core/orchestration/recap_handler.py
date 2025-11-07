"""
Hourly recap handling for the WT3 Agent with Moonward integration.

This module handles the generation and posting of hourly trading recaps
to social media platforms.
"""

import logging
import asyncio
from datetime import datetime
from typing import TYPE_CHECKING

from ...core.trading import TradeTools, TradingError
from ...clients.social import SocialClient, SocialClientError
from .state_management import TradingStateError

if TYPE_CHECKING:
    from ...__main__ import WT3Agent

logger = logging.getLogger(__name__)


async def post_hourly_recap(agent: 'WT3Agent') -> None:
    """Post a recap tweet with the trading activities from the last hour.
    
    This function:
    1. Collects trading activities from the last hour
    2. Calculates current positions and PnL
    3. Generates and posts a summary tweet
    
    Args:
        agent (WT3Agent): The trading agent instance
    
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
            recent_activities = agent.trading_state.get_recent_activities(hours=1)
            
            all_positions = await trade_tools.market_data.get_all_positions()
            
            total_position_value = 0
            positions_data = []
            
            for position in all_positions:
                try:
                    coin = position['coin']
                    current_price = await trade_tools.get_current_price(coin)
                    position_value = abs(position['size']) * current_price
                    total_position_value += position_value
                    
                    positions_data.append({
                        'coin': coin,
                        'size': position['size'],
                        'direction': position['direction'],
                        'value': position_value,
                        'price': current_price,
                        'entry_price': position.get('entry_price', 0),
                        'unrealized_pnl': position.get('unrealized_pnl', 0)
                    })
                    
                    logger.debug(f"Position in {coin}: {position['size']} @ ${current_price:.2f}")
                except Exception as e:
                    logger.warning(f"Could not process position for {position.get('coin', 'UNKNOWN')}: {e}")
            
            current_hour = datetime.utcnow().hour
            if 0 <= current_hour < 8:
                market_session = "Asian"
            elif 8 <= current_hour < 16:
                market_session = "European"
            else:
                market_session = "US"
            
            summary_data = {
                'positions': positions_data,
                'total_value': total_position_value,
                'recent_activities': recent_activities,
                'market_session': market_session,
                'activity_count': len(recent_activities)
            }
            
            if positions_data:
                main_position = max(positions_data, key=lambda x: x['value'])
                summary_data['main_coin'] = main_position['coin']
                summary_data['main_direction'] = main_position['direction']
                summary_data['main_size'] = main_position['size']
                
                try:
                    price_change_pct_1h = await trade_tools.get_price_change_1h(main_position['coin'])
                    summary_data['price_change_1h'] = price_change_pct_1h
                except Exception as e:
                    logger.warning(f"Could not get 1h price change: {e}")
                    summary_data['price_change_1h'] = 0
            
            logger.info(f"Generating recap for {len(positions_data)} positions, {len(recent_activities)} activities")
            
            try:
                result = await tweet_tool.post_hourly_recap(summary_data)
                
                if result and result.get('success'):
                    agent.trading_state.last_tweet_time = datetime.utcnow()
                    logger.info("Successfully posted hourly recap")
                    return
                else:
                    error_msg = result.get('error', 'Unknown error') if result else 'No result returned'
                    raise SocialClientError(f"Failed to post recap: {error_msg}")
                    
            except SocialClientError:
                raise
            except Exception as e:
                logger.error(f"Error posting hourly recap: {e}")
                raise SocialClientError(f"Failed to post recap: {str(e)}")
                
        except asyncio.CancelledError:
            logger.info("Hourly recap cancelled")
            raise
        except (TradingError, SocialClientError, TradingStateError) as e:
            if attempt < max_retries - 1:
                logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
            else:
                logger.error(f"All {max_retries} attempts failed to post hourly recap")
                raise
        except Exception as e:
            logger.error(f"Unexpected error in hourly recap: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
            else:
                raise SocialClientError(f"Unexpected error: {str(e)}")
    
    logger.warning("Failed to post hourly recap after all retries")
