"""
Main entry point for running the WT3 trading agent.

This module implements the main trading loop and coordination between different
components of the trading system, including signal processing, trade execution,
and social media updates.
"""

import asyncio
import logging
import sys
import os
import signal
from datetime import datetime, timedelta
from collections import deque
from typing import Dict, Optional, List, Any, Deque

from .core.trading import TradeTools, TradingError
from .clients.social import SocialClient, SocialClientError
from .clients.signal import SignalClient

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)
coin = "BTC"

class TradingStateError(Exception):
    """Base exception for trading state errors."""
    pass

class TradingState:
    """Maintains the state of trading activities and social media updates."""
    
    def __init__(self, max_activities: int = 20):
        """Initialize trading state.
        
        Args:
            max_activities (int, optional): Maximum number of activities to store. Defaults to 20.
            
        Raises:
            TradingStateError: If state initialization fails
        """
        try:
            self.trade_activities: Deque[Dict[str, Any]] = deque(maxlen=max_activities)
            self.last_tweet_time: Optional[datetime] = None
            self.is_running = True
        except Exception as e:
            error_msg = f"Failed to initialize trading state: {str(e)}"
            logger.error(error_msg)
            raise TradingStateError(error_msg)
        
    def add_activity(self, coin: str, action: str, details: Optional[Dict[str, Any]] = None) -> None:
        """Add a trading activity to the state.
        
        Args:
            coin (str): The trading pair symbol
            action (str): The action taken (e.g., "no_signal", "executed", "closed")
            details (Optional[Dict[str, Any]], optional): Additional details about the action. Defaults to None.
            
        Raises:
            TradingStateError: If activity cannot be added
        """
        try:
            activity = {
                "timestamp": datetime.now(),
                "coin": coin,
                "action": action
            }
            
            if details:
                activity.update(details)
                
            self.trade_activities.append(activity)
        except Exception as e:
            error_msg = f"Failed to add activity to state: {str(e)}"
            logger.error(error_msg)
            raise TradingStateError(error_msg)
        
    def get_activities(self) -> List[Dict[str, Any]]:
        """Get all current trading activities.
        
        Returns:
            List[Dict[str, Any]]: List of current activities
            
        Raises:
            TradingStateError: If activities cannot be retrieved
        """
        try:
            return list(self.trade_activities)
        except Exception as e:
            error_msg = f"Failed to get activities from state: {str(e)}"
            logger.error(error_msg)
            raise TradingStateError(error_msg)
        
    def clear_activities(self) -> None:
        """Clear all trading activities.
        
        Raises:
            TradingStateError: If activities cannot be cleared
        """
        try:
            self.trade_activities.clear()
        except Exception as e:
            error_msg = f"Failed to clear activities: {str(e)}"
            logger.error(error_msg)
            raise TradingStateError(error_msg)

trading_state = TradingState()

class WT3Agent:
    """Trading agent that coordinates signal processing and trade execution."""
    
    def __init__(self):
        """Initialize the trading agent with required clients and tools."""
        self.signal_client = SignalClient()
        self.trading_tools = TradeTools()
        self.trading_state = TradingState()

async def trading_cycle(agent: WT3Agent, coin: str):
    """Execute a single trading cycle.
    
    This function:
    1. Gets the latest signal from the signal service
    2. Executes the trade if a decision is made
    3. Updates the trading state with the result
    
    Args:
        agent (WT3Agent): The trading agent instance
        coin (str): The trading pair symbol
    """
    try:
        try:
            current_price = await agent.trading_tools.get_current_price(coin)
            position_size = await agent.trading_tools.get_position_size(coin)
            position_direction = "LONG" if position_size > 0 else "SHORT" if position_size < 0 else "NONE"
            
            position_value = abs(position_size) * current_price if position_size != 0 else 0
            
            entry_price = await agent.trading_tools.get_entry_price(coin) if position_size != 0 else None
            
            pnl_percent = None
            if position_size != 0 and entry_price:
                if position_direction == "LONG":
                    pnl_percent = (current_price - entry_price) / entry_price * 100
                else:
                    pnl_percent = (entry_price - current_price) / entry_price * 100
            
            market_data = {
                "current_price": current_price,
                "position_size": position_size,
                "position_direction": position_direction,
                "position_value": position_value
            }
            
            if entry_price:
                market_data["entry_price"] = entry_price
            if pnl_percent is not None:
                market_data["pnl_percent"] = pnl_percent
                
        except Exception as e:
            logger.warning(f"Could not retrieve all market data: {e}")
            market_data = {}
        
        prediction = await agent.signal_client.get_prediction(coin)
        if not prediction:
            logger.warning("No prediction received from signal service")
            agent.trading_state.add_activity(coin, "no_signal", market_data)
            return
            
        logger.info(f"Received prediction: {prediction}")
        
        signal_data = {}
        if "timestamp" in prediction:
            signal_data["signal_timestamp"] = prediction["timestamp"]
        
        if "current_position" in prediction and prediction["current_position"]:
            position_info = prediction["current_position"]
            signal_data.update({
                "position_size_from_signal": position_info["size"],
                "position_direction_from_signal": position_info["direction"]
            })
            if "entry_price" in position_info:
                signal_data["entry_price_from_signal"] = position_info["entry_price"]
            logger.info(f"Current position from signal: {position_info['direction']} {position_info['size']} {coin}")
        
        activity_data = {**market_data, **signal_data}
        
        trade_decision = prediction.get('trade_decision')
        if not trade_decision:
            signal_position_direction = signal_data.get("position_direction_from_signal")
            
            if signal_position_direction:
                logger.info(f"No trade decision in signal - holding current {signal_position_direction} position (from signal)")
                hold_data = {**activity_data, 'direction': signal_position_direction}
                agent.trading_state.add_activity(coin, "hold", hold_data)
            elif position_size != 0:
                logger.info(f"No trade decision in signal - holding current {position_direction} position")
                hold_data = {**activity_data, 'direction': position_direction}
                agent.trading_state.add_activity(coin, "hold", hold_data)
            else:
                logger.info("No trade decision in signal - no action needed")
                agent.trading_state.add_activity(coin, "no_action", activity_data)
            return
            
        try:
            result = await agent.trading_tools.execute_trade_signal(prediction)
            logger.info(f"Trade execution result: {result}")
            
            action = trade_decision.get('action', 'unknown')
            direction = trade_decision.get('direction', 'unknown')
            confidence = trade_decision.get('confidence', 0.0)
            
            trade_data = {
                'direction': direction,
                'confidence': confidence,
                'action_type': action
            }
            
            if isinstance(result, dict):
                if 'execution_price' in result:
                    trade_data['execution_price'] = result['execution_price']
                if 'fee' in result:
                    trade_data['fee'] = result['fee']
                if 'order_id' in result:
                    trade_data['order_id'] = result['order_id']
            
            combined_data = {**activity_data, **trade_data}
            
            if action == 'open':
                agent.trading_state.add_activity(coin, "executed", combined_data)
            elif action == 'close':
                agent.trading_state.add_activity(coin, "closed", combined_data)
            elif action == 'close_and_reverse':
                agent.trading_state.add_activity(coin, "reversed", combined_data)
                
        except Exception as e:
            logger.error(f"Error executing trade: {e}")
            error_data = {**activity_data, 'error': str(e)}
            agent.trading_state.add_activity(coin, "failed", error_data)
            
    except Exception as e:
        logger.error(f"Error in trading cycle: {e}")
        agent.trading_state.add_activity(coin, "error", {'error': str(e)})

async def post_hourly_recap() -> None:
    """Post a recap tweet with the trading activities from the last hour.
    
    This function:
    1. Collects trading activities from the last hour
    2. Calculates current position and PnL
    3. Generates and posts a summary tweet
    
    Raises:
        TradingError: If trade data retrieval fails
        SocialClientError: If social media operations fail
        TradingStateError: If state management fails
    """
    global trading_state
    
    logger.debug("Starting hourly recap process")
    logger.debug(f"Number of trade activities: {len(trading_state.trade_activities)}")
    logger.debug(f"Last tweet time: {trading_state.last_tweet_time}")
    
    tweet_tool = SocialClient()
    trade_tools = TradeTools()
    
    max_retries = 3
    retry_delay = 60  # seconds
    
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
            
            if trading_state.trade_activities:
                oldest_timestamp = min([activity["timestamp"] for activity in trading_state.trade_activities])
                time_span = datetime.now() - oldest_timestamp
                
                for activity in trading_state.trade_activities:
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
            trading_state.clear_activities()
            trading_state.last_tweet_time = datetime.now()
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
        finally:
            await trade_tools.cleanup()

async def run_social_tasks() -> Dict[str, Any]:
    """Run social media tasks like checking mentions and monitoring whitelist accounts.
    
    This function:
    1. Creates a SocialClient instance
    2. Calls the run_periodic_tasks method to check mentions and monitor whitelist accounts
    3. Runs every 10 minutes independently of the trading cycle
    4. Ensures isolation from trading cycles to prevent interference
    
    Returns:
        Dict[str, Any]: Summary of tasks performed
        
    Raises:
        SocialClientError: If social media operations fail
    """
    start_time = datetime.now()
    logger.info("🔔 Initiating 10-minute social media cycle")
    
    try:
        social_client = SocialClient()
        result = await social_client.run_periodic_tasks(hours=0.1667)
        
        execution_time = (datetime.now() - start_time).total_seconds()
        
        if result.get('skipped'):
            logger.info(f"⏭️ Social tasks skipped: {result.get('reason')} (checked in {execution_time:.1f}s)")
        else:
            mentions_count = result.get('mentions_processed', 0)
            logger.info(f"📱 Social media cycle completed: {mentions_count} mentions processed in {execution_time:.1f}s")
        
        return result
    except Exception as e:
        error_msg = f"Error in social media cycle after {(datetime.now() - start_time).total_seconds():.1f}s: {str(e)}"
        logger.error(error_msg)
        raise SocialClientError(error_msg) from e

async def main() -> bool:
    """Main function that runs the trading agent in a loop.
    
    This function:
    - Executes a trading cycle every 1 hour
    - Posts a recap tweet every hour
    - Runs social media tasks (check mentions, monitor whitelist accounts) every 30 minutes
    - Ensures social tasks run independently and don't interfere with trading cycles
    - Handles graceful shutdown on system signals
    
    Returns:
        bool: True if the agent completed successfully, False otherwise
    """
    global trading_state
    
    logger.debug("Initializing main trading loop")
    if trading_state.last_tweet_time is None:
        trading_state.last_tweet_time = datetime.now() - timedelta(minutes=55)
    
    logger.info("Starting WT3 trading agent")
    
    agent = WT3Agent()
    last_trading_time = datetime.now() - timedelta(minutes=60)
    last_social_tasks_time = datetime.now() - timedelta(minutes=9)
    
    try:
        while trading_state.is_running:
            current_time = datetime.now()
            
            time_since_last_social = current_time - last_social_tasks_time
            run_social = time_since_last_social.total_seconds() >= 600
            
            time_since_last_trading = current_time - last_trading_time
            run_trading = time_since_last_trading.total_seconds() >= 3600
            
            time_since_last_tweet = current_time - (trading_state.last_tweet_time or (current_time - timedelta(hours=1)))
            run_recap = time_since_last_tweet.total_seconds() >= 3600
            
            if run_trading:
                logger.info("Starting trading cycle - Priority execution")
                try:
                    await trading_cycle(agent, coin)
                    last_trading_time = current_time
                except Exception as e:
                    logger.error(f"Error in trading cycle: {str(e)}")
                    logger.warning("Will retry in next interval")
                
                if run_social:
                    logger.info("Brief pause before social media tasks")
                    await asyncio.sleep(2)
            
            if run_recap:
                logger.info("Time for hourly recap")
                try:
                    await post_hourly_recap()
                except Exception as e:
                    logger.error(f"Error posting hourly recap: {str(e)}")
                    logger.warning("Will retry in next interval")
            
            if run_social:
                logger.info("Running social media tasks (10-minute cycle)")
                try:
                    await run_social_tasks()
                    last_social_tasks_time = current_time
                except Exception as e:
                    logger.error(f"Error in social media tasks: {str(e)}")
                    logger.warning("Will retry in next interval")
            
            next_social_check = max(0, 600 - time_since_last_social.total_seconds())
            next_trading_check = max(0, 3600 - time_since_last_trading.total_seconds())
            next_recap_check = max(0, 3600 - time_since_last_tweet.total_seconds())

            sleep_time = min(300, max(60, min(next_social_check, next_trading_check, next_recap_check)))
            logger.info(f"Next social check in {next_social_check/60:.1f}min, trading check in {next_trading_check/60:.1f}min, recap in {next_recap_check/60:.1f}min")
            logger.info(f"Waiting {sleep_time}s before next check")
            await asyncio.sleep(sleep_time)
            
        return True
    except KeyboardInterrupt:
        logger.info("Trading agent interrupted by user")
        return True
    except Exception as e:
        error_msg = f"Unexpected error in main loop: {str(e)}"
        logger.error(error_msg)
        return False

def force_exit() -> None:
    """Force the script to exit by sending SIGTERM to itself.
    
    Raises:
        OSError: If the signal cannot be sent
    """
    try:
        logger.info("Forcing script to exit...")
        os.kill(os.getpid(), signal.SIGTERM)
    except OSError as e:
        error_msg = f"Failed to force exit: {str(e)}"
        logger.error(error_msg)
        raise

if __name__ == "__main__":
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        result = loop.run_until_complete(main())
        
        loop.close()
        
        logger.info("Trading agent completed successfully" if result else "Trading agent completed with errors")
        
        logger.debug("Preparing for clean exit")
        force_exit()
        
    except KeyboardInterrupt:
        logger.info("Trading agent interrupted by user")
        sys.exit(130)
    except Exception as e:
        error_msg = f"Unhandled exception: {str(e)}"
        logger.error(error_msg)
        sys.exit(1)
