"""
Order management for the WT3 Agent.

This module provides functionality for executing orders, managing positions,
and handling stop-loss/take-profit orders on the exchange.
"""

import logging

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
        stop_loss: float
    ) -> str:
        """Open a new position with stop loss order.
        
        Uses MARKET orders for immediate execution as required by signal provider.
        Automatically places stop-loss order for risk management.
        
        Args:
            coin (str): The trading pair symbol (e.g., 'BTC', 'ETH')
            is_long (bool): True for long position, False for short position
            size (float): Position size in coin units
            stop_loss (float): Stop loss price level in USD
            
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
            
            logger.info(f"Rounded stop loss to {stop_loss}")
                                                
            current_price = await self.market_data.get_current_price(coin)
            if current_price <= 0:
                raise MarketDataError(f"Failed to get current price for {coin}")
                                    
            logger.info(f"Opening {'LONG' if is_long else 'SHORT'} position: {size} {coin} (MARKET order)")
            
            order_result = self.exchange.market_open(coin, is_long, size, None, 0.01)
            
            logger.info(f"Market order result: {order_result}")
            
            if order_result.get('status') != 'ok':
                raise OrderError(f"Failed to open position: {order_result}")
                
            response_data = order_result.get('response', {}).get('data', {})
            statuses = response_data.get('statuses', [{}])
            
            if statuses and 'error' in statuses[0]:
                error_msg = statuses[0]['error']
                logger.error(f"Order error: {error_msg}")
                raise OrderError(f"Failed to open position: {error_msg}")
            
            try:
                if stop_loss and stop_loss > 0:
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
            except Exception as e:
                logger.error(f"Error setting stop loss: {e}")
                raise OrderError(f"Failed to set stop loss: {str(e)}")
            
            sl_msg = f"${stop_loss:.2f}" if stop_loss is not None and stop_loss > 0 else "None"
            return (
                f"Successfully opened {'LONG' if is_long else 'SHORT'} position: {size} {coin} (market order) "
                f"with SL: {sl_msg}"
            )
            
        except (OrderError, MarketDataError) as e:
            raise
        except Exception as e:
            import traceback
            error_msg = f"Error opening position: {str(e)}"
            logger.error(error_msg)
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise OrderError(error_msg)

    async def close_position(self, coin: str) -> str:
        """Close an existing position using MARKET orders for immediate execution.
        
        This method:
        1. Cancels any existing open orders for the coin
        2. Places a MARKET order to close the position immediately
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
            
            logger.info(f"Closing {'LONG' if is_long else 'SHORT'} position: {size} {coin} (MARKET order)")
            
            order_result = self.exchange.market_close(coin)
            
            logger.info(f"Market close order result: {order_result}")
            
            if order_result.get('status') != 'ok':
                raise OrderError(f"Failed to close position: {order_result}")
            
            return f"Successfully closed {'LONG' if is_long else 'SHORT'} position: {size} {coin} (MARKET order)"
            
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
