"""
Signal execution for the WT3 Agent.

This module handles the execution of trading signals received from the signal service,
including opening, closing, and reversing positions based on signal decisions.
"""

import logging
import math
from typing import Dict, Any

from .exceptions import OrderError, MarketDataError

logger = logging.getLogger(__name__)


class SignalExecutor:
    """Executes trading signals from the signal service."""
    
    def __init__(self, exchange_client, order_manager):
        """Initialize with exchange client and order manager.
        
        Args:
            exchange_client: The ExchangeClient instance
            order_manager: The OrderManager instance
        """
        self.exchange_client = exchange_client
        self.exchange = exchange_client.exchange
        self.order_manager = order_manager

    async def execute_trade_signal(self, signal: Dict[str, Any]) -> str:
        """Execute trade based on signal from signal service.
        
        This method processes trading signals and executes the appropriate actions:
        - Opening new positions
        - Closing existing positions
        - Reversing positions (close and open opposite)
        
        The signal service provides all trade decisions and strategy data including:
        - Position size
        - Stop loss and take profit levels
        - Leverage settings
        - Trade direction
        
        Args:
            signal (Dict[str, Any]): Signal response from signal service containing:
                - timestamp (int): Unix timestamp of the signal
                - trade_decision (dict, optional): The trading decision to execute, containing:
                    - action (str): One of 'open', 'close', 'close_and_reverse'
                    - coin (str): Trading pair symbol
                    - direction (str): 'long' or 'short'
                    - confidence (float): Confidence level between 0 and 1
                    - strategy (dict): Strategy parameters including:
                        - position_size_coin (float): Position size in coin units
                        - leverage (float): Leverage to use
                        - stop_loss (float): Stop loss price level
                        - take_profit (float): Take profit price level
            
        Returns:
            str: Result message indicating success or failure
            
        Raises:
            OrderError: If trade execution fails
            MarketDataError: If market data cannot be retrieved
            ValueError: If signal data is invalid
        """
        if not signal:
            raise ValueError("No signal to execute")
            
        try:
            trade_decision = signal.get('trade_decision')
            if not trade_decision:
                logger.info("No trade decision in signal - no action needed")
                return "No trade action needed"
            
            action = trade_decision.get('action')
            coin = trade_decision.get('coin')
            strategy_data = trade_decision.get('strategy')
            
            if not strategy_data:
                raise ValueError("No strategy data in trade decision")
            
            logger.debug(f"Preparing to execute {action} for {coin}")
            await self.order_manager.cancel_all_orders(coin)
            
            position_size_coin = strategy_data.get('position_size_coin')
            stop_loss = strategy_data.get('stop_loss')
            take_profit = strategy_data.get('take_profit')
            leverage = strategy_data.get('leverage')
            
            if action == 'open':
                direction = trade_decision.get('direction')
                confidence = trade_decision.get('confidence', 0.0)
                is_long = direction == 'long'
                
                logger.info(f"Using strategy data: position_size={position_size_coin:.6f} {coin}, leverage={leverage:.2f}x")
                logger.info(f"Stop loss: ${stop_loss:.2f}, Take profit: ${take_profit:.2f}")
                logger.info(f"Trade direction: {direction}, Confidence: {confidence:.2%}")
                
                max_leverage = 5
                leverage_to_use = min(math.ceil(leverage), max_leverage)
                
                try:
                    leverage_result = self.exchange.update_leverage(
                        leverage=leverage_to_use,
                        name=coin,
                        is_cross=True
                    )
                    logger.info(f"Leverage result: {leverage_result}")
                    logger.info(f"Set leverage to {leverage_to_use}x (calculated: {leverage:.2f}x)")
                except Exception as e:
                    logger.warning(f"Error setting leverage: {e}")
                
                logger.debug(f"Executing trade with size {position_size_coin} {coin}")
                trade_result = await self.order_manager.open_position(
                    coin=coin,
                    is_long=is_long,
                    size=position_size_coin,
                    stop_loss=stop_loss,
                    take_profit=take_profit
                )
                
                return f"Opened {direction} position in {coin}: {trade_result}"
                
            elif action == 'close_and_reverse':
                direction = trade_decision.get('direction')
                confidence = trade_decision.get('confidence', 0.0)
                is_long = direction == 'long'
                
                logger.debug(f"Closing existing position before reversing")
                close_result = await self.order_manager.close_position(coin)
                logger.info(f"Closed existing position: {close_result}")
                
                logger.info(f"Using strategy data: position_size={position_size_coin:.6f} {coin}, leverage={leverage:.2f}x")
                logger.info(f"Stop loss: ${stop_loss:.2f}, Take profit: ${take_profit:.2f}")
                logger.info(f"Trade direction: {direction}, Confidence: {confidence:.2%}")
                
                max_leverage = 5
                leverage_to_use = min(math.ceil(leverage), max_leverage)
                
                try:
                    leverage_result = self.exchange.update_leverage(
                        leverage=leverage_to_use,
                        name=coin,
                        is_cross=True
                    )
                    logger.info(f"Leverage result: {leverage_result}")
                    logger.info(f"Set leverage to {leverage_to_use}x (calculated: {leverage:.2f}x)")
                except Exception as e:
                    logger.warning(f"Error setting leverage: {e}")
                
                logger.debug(f"Opening new {direction} position with size {position_size_coin} {coin}")
                trade_result = await self.order_manager.open_position(
                    coin=coin,
                    is_long=is_long,
                    size=position_size_coin,
                    stop_loss=stop_loss,
                    take_profit=take_profit
                )
                
                return f"Reversed to {direction} position in {coin}: {trade_result}"
            
            elif action == 'close':
                logger.debug(f"Closing position as instructed by signal service")
                close_result = await self.order_manager.close_position(coin)
                return f"Closed position in {coin}: {close_result}"
            
            raise ValueError(f"Unknown action: {action}")
            
        except (OrderError, MarketDataError, ValueError) as e:
            raise
        except Exception as e:
            error_msg = f"Error executing trade signal: {str(e)}"
            logger.error(error_msg)
            raise OrderError(error_msg)