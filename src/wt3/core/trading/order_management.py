"""
Order management for the WT3 Agent.

This module provides functionality for executing orders, managing positions,
and handling stop-loss/take-profit orders on the exchange.
"""

import logging
import math
from typing import Dict, Any

from .exceptions import OrderError, MarketDataError

logger = logging.getLogger(__name__)


class OrderManager:
    """Manages order execution and position management."""
    
    def __init__(self, exchange_client, market_data_provider):
        """Initialize with exchange client and market data provider.
        
        Args:
            exchange_client: The ExchangeClient instance
            market_data_provider: The MarketDataProvider instance
        """
        self.exchange_client = exchange_client
        self.exchange = exchange_client.exchange
        self.info = exchange_client.info
        self.wallet = exchange_client.wallet
        self.market_data = market_data_provider

    async def open_position(
        self,
        coin: str,
        is_long: bool,
        size: float,
        stop_loss: float,
        take_profit: float
    ) -> str:
        """Open a new position with stop loss and take profit orders.
        
        Uses limit orders for better execution prices and automatically places
        stop-loss and take-profit orders for risk management.
        
        Args:
            coin (str): The trading pair symbol (e.g., 'BTC', 'ETH')
            is_long (bool): True for long position, False for short position
            size (float): Position size in coin units
            stop_loss (float): Stop loss price level in USD
            take_profit (float): Take profit price level in USD
            
        Returns:
            str: Result message indicating success or failure
            
        Raises:
            OrderError: If order execution fails
            MarketDataError: If market data cannot be retrieved
        """
        try:
            await self.exchange_client.ensure_clients()
            
            coin_info = await self.market_data.get_coin_info(coin)
            sz_decimals = int(coin_info['szDecimals'])
            px_step = await self.market_data.get_tick_size(coin)
            
            size = round(size, sz_decimals)
            
            if size <= 0:
                raise OrderError(f"Position size too small to execute: {size} {coin}")
                        
            stop_loss = round(stop_loss / px_step) * px_step
            take_profit = round(take_profit / px_step) * px_step
            
            logger.info(f"Rounded stop loss to {stop_loss} and take profit to {take_profit}")
                                                
            current_price = await self.market_data.get_current_price(coin)
            if current_price <= 0:
                raise MarketDataError(f"Failed to get current price for {coin}")
                
            limit_price = current_price
            if is_long:
                limit_price = round((current_price * 1.001) / px_step) * px_step
            else:
                limit_price = round((current_price * 0.999) / px_step) * px_step
                                    
            logger.info(f"Opening {'LONG' if is_long else 'SHORT'} position: {size} {coin} (limit order at ${limit_price})")
            
            order_result = self.exchange.order(
                name=coin,
                is_buy=is_long,
                sz=size,
                limit_px=limit_price,
                order_type={"limit": {"tif": "Gtc"}}
            )
            
            logger.info(f"Limit order result: {order_result}")
            
            if order_result.get('status') != 'ok':
                raise OrderError(f"Failed to open position: {order_result}")
                
            response_data = order_result.get('response', {}).get('data', {})
            statuses = response_data.get('statuses', [{}])
            
            if statuses and 'error' in statuses[0]:
                error_msg = statuses[0]['error']
                logger.error(f"Order error: {error_msg}")
                raise OrderError(f"Failed to open position: {error_msg}")
            
            try:
                stop_order_type = {
                    "trigger": {
                        "triggerPx": stop_loss,
                        "isMarket": True,
                        "tpsl": "sl"
                    }
                }
                
                stop_result = self.exchange.order(
                    name=coin,
                    is_buy=not is_long,
                    sz=size,
                    limit_px=stop_loss,
                    order_type=stop_order_type,
                    reduce_only=True
                )
                
                logger.info(f"Stop loss market order result: {stop_result}")
                
                tp_order_type = {
                    "trigger": {
                        "triggerPx": take_profit,
                        "isMarket": True,
                        "tpsl": "tp"
                    }
                }
                
                tp_result = self.exchange.order(
                    name=coin,
                    is_buy=not is_long,
                    sz=size,
                    limit_px=take_profit,
                    order_type=tp_order_type,
                    reduce_only=True
                )
                
                logger.info(f"Take profit market order result: {tp_result}")
            except Exception as e:
                logger.error(f"Error setting stop loss/take profit: {e}")
                raise OrderError(f"Failed to set stop loss/take profit: {str(e)}")
            
            return (
                f"Successfully opened {'LONG' if is_long else 'SHORT'} position: {size} {coin} (limit order) "
                f"with SL: ${stop_loss:.2f}, TP: ${take_profit:.2f}"
            )
            
        except (OrderError, MarketDataError) as e:
            raise
        except Exception as e:
            error_msg = f"Error opening position: {str(e)}"
            logger.error(error_msg)
            raise OrderError(error_msg)

    async def close_position(self, coin: str) -> str:
        """Close an existing position using limit orders for better execution prices.
        
        This method:
        1. Cancels any existing open orders for the coin
        2. Places a limit order to close the position at a slightly better price
        3. Handles both long and short positions appropriately
        
        Args:
            coin (str): The trading pair symbol (e.g., 'BTC', 'ETH')
            
        Returns:
            str: Result message indicating success or failure
            
        Raises:
            OrderError: If position closing fails
            MarketDataError: If market data cannot be retrieved
        """
        try:
            await self.exchange_client.ensure_clients()
            
            position_size = await self.market_data.get_position_size(coin)
            
            if position_size == 0:
                return f"No open position in {coin} to close"
            
            is_long = position_size > 0
            size = abs(position_size)
            
            try:
                await self.cancel_all_orders(coin)
            except Exception as e:
                logger.warning(f"Error cancelling orders for {coin}: {e}")
            
            current_price = await self.market_data.get_current_price(coin)
            if current_price <= 0:
                raise MarketDataError(f"Failed to get current price for {coin}")
                
            px_step = await self.market_data.get_tick_size(coin)
            
            limit_price = current_price
            if is_long:
                limit_price = round((current_price * 0.999) / px_step) * px_step
            else:
                limit_price = round((current_price * 1.001) / px_step) * px_step
            
            logger.info(f"Closing {'LONG' if is_long else 'SHORT'} position: {size} {coin} (limit order at ${limit_price})")
            
            order_result = self.exchange.order(
                name=coin.upper(),
                is_buy=not is_long,
                sz=size,
                limit_px=limit_price,
                order_type={"limit": {"tif": "Gtc"}},
                reduce_only=True
            )
            
            logger.info(f"Limit close order result: {order_result}")
            
            if order_result.get('status') != 'ok':
                raise OrderError(f"Failed to close position: {order_result}")
            
            return f"Successfully placed order to close {'LONG' if is_long else 'SHORT'} position: {size} {coin} (limit order at ${limit_price})"
            
        except (OrderError, MarketDataError) as e:
            raise
        except Exception as e:
            error_msg = f"Error closing position: {str(e)}"
            logger.error(error_msg)
            raise OrderError(error_msg)

    async def cancel_all_orders(self, coin: str) -> str:
        """Cancel all open orders for a given coin.
        
        This method cancels both regular limit orders and trigger orders (stop-loss,
        take-profit) for the specified coin.
        
        Args:
            coin (str): The trading pair symbol (e.g., 'BTC', 'ETH')
            
        Returns:
            str: Result message indicating number of orders cancelled or error message
            
        Raises:
            OrderError: If order cancellation fails
            MarketDataError: If market data cannot be retrieved
        """
        try:
            await self.exchange_client.ensure_clients()
            
            orders_cancelled = 0
            trigger_orders_cancelled = 0
            
            try:
                open_orders = self.info.open_orders(self.wallet.address)
                coin_orders = [order for order in open_orders if order.get('coin') == coin.upper()]
                
                for order in coin_orders:
                    if 'oid' in order:
                        try:
                            cancel_result = self.exchange.cancel(coin.upper(), order['oid'])
                            logger.info(f"Cancelled order {order['oid']} for {coin}: {cancel_result}")
                            orders_cancelled += 1
                        except Exception as e:
                            logger.warning(f"Error cancelling order {order['oid']} for {coin}: {e}")
                
                if coin_orders:
                    logger.info(f"Cancelled {orders_cancelled} open orders for {coin}")
                else:
                    logger.info(f"No open orders found for {coin}")
            except Exception as e:
                logger.warning(f"Error getting open orders: {e}")
            
            try:
                user_state = self.info.user_state(self.wallet.address)
                
                if 'triggerOrders' in user_state:
                    trigger_orders = user_state['triggerOrders']
                    coin_trigger_orders = [order for order in trigger_orders if order.get('coin') == coin.upper()]
                    
                    for order in coin_trigger_orders:
                        if 'oid' in order:
                            try:
                                cancel_result = self.exchange.cancel(coin.upper(), order['oid'])
                                logger.info(f"Cancelled trigger order {order['oid']} for {coin}: {cancel_result}")
                                trigger_orders_cancelled += 1
                            except Exception as e:
                                logger.warning(f"Error cancelling trigger order {order['oid']} for {coin}: {e}")
                    
                    if coin_trigger_orders:
                        logger.info(f"Cancelled {trigger_orders_cancelled} trigger orders for {coin}")
            except Exception as e:
                logger.warning(f"Error checking for trigger orders: {e}")
            
            total_cancelled = orders_cancelled + trigger_orders_cancelled
            if total_cancelled > 0:
                return f"Successfully cancelled {total_cancelled} orders for {coin}"
            else:
                return f"No orders found to cancel for {coin}"
                
        except Exception as e:
            error_msg = f"Error cancelling orders: {str(e)}"
            logger.error(error_msg)
            raise OrderError(error_msg)