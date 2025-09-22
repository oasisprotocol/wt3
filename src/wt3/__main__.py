"""
Main entry point for running the WT3 trading agent with Moonward Capital integration.

This module implements the main trading loop with 15-second polling for Moonward signals
and hourly social media recaps.
"""

import asyncio
import logging
import sys
import os
from datetime import datetime, timedelta

from .core.trading import TradeTools
from .clients.signal import SignalClient
from .core.orchestration import (
    TradingState,
    trading_cycle,
    post_hourly_recap,
    run_social_tasks
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)


class WT3Agent:
    """Trading agent that coordinates signal processing and trade execution."""
    
    def __init__(self):
        """Initialize the trading agent with required clients and tools."""
        self.signal_client = SignalClient()
        self.trading_tools = TradeTools()
        self.trading_state = TradingState()


async def main() -> bool:
    """Main function that runs the trading agent in a loop.
    
    This function:
    - Executes a trading cycle every 15 seconds (polling Moonward signals)
    - Posts a recap tweet every hour
    - Runs social media tasks (check mentions, monitor whitelist accounts) every 30 minutes
    - Ensures social tasks run independently and don't interfere with trading cycles
    - Handles graceful shutdown on system signals
    
    Returns:
        bool: True if the agent completed successfully, False otherwise
    """
    logger.debug("Initializing main trading loop")
    logger.info("Starting WT3 trading agent")
    logger.info("Polling interval: 15 seconds | Hourly recaps: Enabled")
    
    agent = WT3Agent()
    if agent.trading_state.last_tweet_time is None:
        agent.trading_state.last_tweet_time = datetime.utcnow() - timedelta(minutes=55)
    
    last_trading_time = datetime.utcnow()
    last_social_tasks_time = datetime.utcnow() - timedelta(minutes=25)
    
    try:
        while agent.trading_state.is_running:
            current_time = datetime.utcnow()
            time_since_last_social = current_time - last_social_tasks_time
            run_social = time_since_last_social.total_seconds() >= 1800  # 30 minutes
            
            time_since_last_trading = current_time - last_trading_time
            run_trading = time_since_last_trading.total_seconds() >= 15  # 15 seconds for Moonward polling
            
            time_since_last_tweet = current_time - (agent.trading_state.last_tweet_time or (current_time - timedelta(hours=1)))
            run_recap = time_since_last_tweet.total_seconds() >= 3600  # 1 hour
            
            if run_trading:
                logger.debug("Polling for signals")
                try:
                    await trading_cycle(agent)
                    last_trading_time = current_time
                except Exception as e:
                    logger.error(f"Error in trading cycle: {str(e)}")
                    logger.warning("Will retry in next interval")
            
            if run_recap:
                logger.info("Time for hourly recap")
                try:
                    await post_hourly_recap(agent)
                except Exception as e:
                    logger.error(f"Error posting hourly recap: {str(e)}")
                    logger.warning("Will retry in next interval")
            
            if run_social:
                logger.info("Running social media tasks (30-minute cycle)")
                try:
                    await run_social_tasks()
                    last_social_tasks_time = current_time
                except Exception as e:
                    logger.error(f"Error in social media tasks: {str(e)}")
                    logger.warning("Will retry in next interval")
            
            next_social_check = max(0, 1800 - time_since_last_social.total_seconds())
            next_trading_check = max(0, 15 - time_since_last_trading.total_seconds())
            next_recap_check = max(0, 3600 - time_since_last_tweet.total_seconds())

            sleep_time = min(15, max(5, min(next_social_check, next_trading_check, next_recap_check)))
            await asyncio.sleep(sleep_time)
            
        return True
    except KeyboardInterrupt:
        logger.info("Trading agent interrupted by user")
        return True
    except Exception as e:
        error_msg = f"Unexpected error in main loop: {str(e)}"
        logger.error(error_msg)
        return False


if __name__ == "__main__":
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        result = loop.run_until_complete(main())
        
        loop.close()
        
        logger.info("Trading agent completed successfully" if result else "Trading agent completed with errors")
        
        logger.debug("Preparing for clean exit")
        logger.info("Forcing script to exit...")
        try:
            os.kill(os.getpid(), 15)
        except OSError as e:
            logger.error(f"Failed to force exit: {str(e)}")
            raise
        
    except KeyboardInterrupt:
        logger.info("Trading agent interrupted by user")
        sys.exit(130)
    except Exception as e:
        error_msg = f"Unhandled exception: {str(e)}"
        logger.error(error_msg)
        sys.exit(1)
