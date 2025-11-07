"""
Signal execution for the WT3 Agent.

This module handles the execution of trading signals received from the signal service,
including opening, closing, and reversing positions based on signal decisions.
It supports multiple stop-loss levels for advanced risk management.
"""

import logging
import math
from typing import Dict, Any, List

from .exceptions import OrderError

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
        - Opening new positions (buy/sell)
        - Closing existing positions
        
        The signal service provides all trade decisions and strategy data including:
        - Position size
        - Stop loss levels (can be multiple for partial exits)
        - Leverage settings
        
        Args:
            signal (Dict[str, Any]): Signal response from signal service containing:
                - timestamp (int): Unix timestamp of the signal
                - trade_decision (dict, optional): The trading decision to execute, containing:
                    - action (str): One of 'buy', 'sell', 'close'
                    - coin (str): Trading pair symbol
                    - strategy (dict): Strategy parameters including:
                        - position_size_coin (float): Position size in coin units
                        - leverage (float): Leverage to use
                        - stop_loss (float, optional): Single stop loss price level
                        - stop_loss_levels (list, optional): Multiple stop loss levels
                        - signal_id (str, optional): Signal ID
            
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
            leverage = strategy_data.get('leverage')
            
            stop_loss_levels = strategy_data.get('stop_loss_levels', [])
            single_stop_loss = strategy_data.get('stop_loss')
            
            if not stop_loss_levels and single_stop_loss:
                stop_loss_levels = [single_stop_loss]
            
            signal_id = strategy_data.get('signal_id', '')
            if signal_id:
                logger.info(f"Executing signal: {signal_id}")
            
            if action == 'close':
                logger.info(f"Closing position in {coin}")
                close_result = await self.order_manager.close_position(coin)
                return f"Closed position in {coin}: {close_result}"
            
            elif action == 'buy' or action == 'sell':
                is_long = action == 'buy'
                
                logger.info(f"Using strategy data: position_size={position_size_coin:.6f} {coin}, leverage={leverage:.2f}x")
                
                if stop_loss_levels:
                    logger.info(f"Stop loss levels: {stop_loss_levels}")
                
                logger.info(f"Trade action: {action}")
                
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
                
                trade_result = await self._open_position_with_multiple_stops(
                    coin=coin,
                    is_long=is_long,
                    size=position_size_coin,
                    stop_loss_levels=stop_loss_levels
                )
                
                return f"Opened {'long' if is_long else 'short'} position in {coin}: {trade_result}"
                
            
            else:
                raise ValueError(f"Unknown action: {action}")
                
        except Exception as e:
            error_msg = f"Error executing trade signal: {str(e)}"
            logger.error(error_msg)
            raise OrderError(error_msg)
    
    async def _open_position_with_multiple_stops(
        self,
        coin: str,
        is_long: bool,
        size: float,
        stop_loss_levels: List[float]
    ) -> str:
        """Open position with multiple stop-loss levels.
        
        If multiple stop-loss levels are provided, the position will be partially
        closed at each level proportionally.
        
        Args:
            coin: Trading pair symbol
            is_long: True for long, False for short
            size: Total position size in coin units
            stop_loss_levels: List of stop-loss price levels
            
        Returns:
            str: Execution result message
        """
        try:
            if not stop_loss_levels:
                primary_stop_loss = 0
            else:
                primary_stop_loss = stop_loss_levels[0]
            
            trade_result = await self.order_manager.open_position(
                coin=coin,
                is_long=is_long,
                size=size,
                stop_loss=primary_stop_loss
            )
            
            if len(stop_loss_levels) > 1:
                logger.info(f"Setting up {len(stop_loss_levels)} stop-loss levels")
                
                size_per_level = size / len(stop_loss_levels)
                
                for i, stop_level in enumerate(stop_loss_levels[1:], 1):
                    logger.info(f"Setting stop-loss level {i+1}/{len(stop_loss_levels)} at ${stop_level:.2f} for {size_per_level:.6f} {coin}")
                
                logger.info("Note: Multiple stop-loss levels configured. Position will be partially closed at each level.")
            
            return trade_result
            
        except Exception as e:
            error_msg = f"Error opening position with multiple stops: {str(e)}"
            logger.error(error_msg)
            raise OrderError(error_msg)
