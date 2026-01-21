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
        stop_loss_levels: list
    ) -> str:
        """Open a new position with multiple stop loss orders.

        Uses MARKET orders for immediate execution as required by signal provider.
        Places stop-loss orders at each level, dividing the position equally.

        Args:
            coin (str): The trading pair symbol (e.g., 'BTC', 'ETH')
            is_long (bool): True for long position, False for short position
            size (float): Position size in coin units
            stop_loss_levels (list): List of stop loss price levels in USD.
                                     Position is divided equally among levels.

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

            sl_results = []
            if stop_loss_levels:
                num_levels = len(stop_loss_levels)
                size_per_level = round(size / num_levels, sz_decimals)
                remaining_size = size

                logger.info(f"Setting {num_levels} stop loss levels, {size_per_level} {coin} per level")

                for i, stop_price in enumerate(stop_loss_levels):
                    is_last = (i == num_levels - 1)
                    sl_size = remaining_size if is_last else size_per_level
                    remaining_size -= sl_size

                    rounded_stop = round(stop_price / px_step) * px_step

                    try:
                        stop_order_type = {
                            "trigger": {
                                "triggerPx": rounded_stop,
                                "isMarket": True,
                                "tpsl": "sl"
                            }
                        }

                        stop_result = self.exchange.order(
                            name=coin,
                            is_buy=not is_long,
                            sz=sl_size,
                            limit_px=rounded_stop,
                            order_type=stop_order_type,
                            reduce_only=True
                        )

                        logger.info(f"Stop loss {i+1}/{num_levels} at ${rounded_stop:.2f} for {sl_size} {coin}: {stop_result.get('status')}")
                        sl_results.append(f"${rounded_stop:.2f}")

                    except Exception as e:
                        logger.error(f"Error setting stop loss {i+1} at ${rounded_stop:.2f}: {e}")
                        sl_results.append(f"${rounded_stop:.2f} (FAILED)")

            sl_msg = ", ".join(sl_results) if sl_results else "None"
            return (
                f"Successfully opened {'LONG' if is_long else 'SHORT'} position: {size} {coin} (market order) "
                f"with SL levels: [{sl_msg}]"
            )

        except (OrderError, MarketDataError):
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
            
        except (OrderError, MarketDataError):
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

    async def close_all_positions(self) -> str:
        """Close all open positions across all coins.

        This is a one-time utility function that closes all open positions.
        Useful for emergency shutdowns or cleanup operations.

        Returns:
            str: Result message indicating number of positions closed

        Raises:
            OrderError: If position closing fails
        """
        try:
            await self.exchange_client.ensure_clients()

            all_positions = await self.market_data.get_all_positions()

            if not all_positions:
                logger.info("No open positions to close")
                return "No open positions to close"

            closed_count = 0
            failed_count = 0
            results = []

            logger.info(f"Found {len(all_positions)} open positions to close")

            for position in all_positions:
                coin = position['coin']
                size = position['size']
                direction = position['direction']

                try:
                    logger.info(f"Closing {direction} position: {abs(size)} {coin}")
                    result = await self.close_position(coin)
                    results.append(f"✓ {coin}: {result}")
                    closed_count += 1
                except Exception as e:
                    error_msg = f"✗ {coin}: Failed to close - {str(e)}"
                    logger.error(error_msg)
                    results.append(error_msg)
                    failed_count += 1

            summary = f"Closed {closed_count} positions"
            if failed_count > 0:
                summary += f", {failed_count} failed"

            logger.info(summary)
            return summary

        except Exception as e:
            error_msg = f"Error closing all positions: {str(e)}"
            logger.error(error_msg)
            raise OrderError(error_msg)
