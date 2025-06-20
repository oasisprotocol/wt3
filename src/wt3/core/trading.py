"""
Trading tools for the WT3 Agent.

This module provides functionality for executing trades on the Hyperliquid exchange,
including position management, order execution, and trade signal processing.
"""

import logging
import asyncio
from typing import Dict, Any
from eth_account import Account
from hyperliquid.info import Info
from hyperliquid.exchange import Exchange
from hyperliquid.utils import constants
import math
import aiohttp

logger = logging.getLogger(__name__)

class TradingError(Exception):
    """Base exception for trading-related errors."""
    pass

class WalletError(TradingError):
    """Exception raised when wallet operations fail."""
    pass

class MarketDataError(TradingError):
    """Exception raised when market data operations fail."""
    pass

class OrderError(TradingError):
    """Exception raised when order operations fail."""
    pass

class ExchangeError(TradingError):
    """Exception raised when exchange operations fail."""
    pass

class TradeTools:
    """Trading tools for executing trades on Hyperliquid exchange.
    
    This class provides methods for managing trading positions and executing orders
    on the Hyperliquid exchange. It uses limit orders for better execution prices
    and implements stop-loss and take-profit orders for risk management.
    
    Attributes:
        wallet (Account): Ethereum wallet for signing transactions
        base_url (str): Base URL for the Hyperliquid API
        info (Info): Hyperliquid Info client for market data
        exchange (Exchange): Hyperliquid Exchange client for order execution
    """
    
    def __init__(self):
        """Initialize trading clients and wallet.
        
        Sets up the Hyperliquid API clients and initializes the trading wallet
        using ROFL key management.
        
        Raises:
            WalletError: If keypair generation or wallet initialization fails
            ExchangeError: If exchange client initialization fails
        """
        from ..clients.rofl import get_keypair
        
        try:
            self.private_key, public_address = get_keypair()
            logger.info(f"Using wallet with address: {public_address}")
        except Exception as e:
            error_msg = f"Failed to generate keypair: {str(e)}"
            logger.error(error_msg)
            raise WalletError(error_msg)
        
        try:
            self.wallet = Account.from_key(self.private_key)
        except Exception as e:
            error_msg = f"Failed to initialize wallet: {str(e)}"
            logger.error(error_msg)
            raise WalletError(error_msg)
        
        self.base_url = constants.MAINNET_API_URL
        try:
            self.info = Info(base_url=self.base_url)
            meta = self.info.meta()
            
            self.exchange = Exchange(
                wallet=self.wallet,
                base_url=self.base_url,
                meta=meta
            )
        except Exception as e:
            error_msg = f"Failed to initialize exchange clients: {str(e)}"
            logger.error(error_msg)
            raise ExchangeError(error_msg)
        
        logger.info(f"Initialized wallet with address: {self.wallet.address}")

    async def _ensure_clients(self) -> None:
        """Ensure exchange clients are properly initialized.
        
        Raises:
            ExchangeError: If client initialization fails
        """
        try:
            if not self.info or not hasattr(self.info, 'meta'):
                self.info = Info(base_url=self.base_url)
                
            if not self.exchange or not hasattr(self.exchange, 'order'):
                meta = self.info.meta()
                self.exchange = Exchange(
                    wallet=self.wallet,
                    base_url=self.base_url,
                    meta=meta
                )
        except Exception as e:
            error_msg = f"Failed to ensure exchange clients: {str(e)}"
            logger.error(error_msg)
            raise ExchangeError(error_msg)

    async def get_position_size(self, coin: str) -> float:
        """Get current position size for a given coin.
        
        Args:
            coin (str): The trading pair symbol (e.g., 'BTC', 'ETH')
            
        Returns:
            float: Current position size in coin units. Positive for long positions,
                  negative for short positions, 0.0 if no position exists
                  
        Raises:
            MarketDataError: If position data cannot be retrieved
        """
        try:
            await self._ensure_clients()
            
            user_state = self.info.user_state(self.wallet.address)
            positions = user_state.get('assetPositions', [])
            
            for position in positions:
                if position.get('position', {}).get('coin') == coin.upper():
                    size = float(position['position']['szi'])
                    logger.debug(f"Current position size for {coin}: {size}")
                    return size
            
            logger.debug(f"No position found for {coin}")
            return 0.0
            
        except Exception as e:
            error_msg = f"Error getting position size for {coin}: {str(e)}"
            logger.error(error_msg)
            raise MarketDataError(error_msg)

    async def get_current_price(self, coin: str) -> float:
        """Get current market price for a coin.
        
        Args:
            coin (str): The trading pair symbol (e.g., 'BTC', 'ETH')
            
        Returns:
            float: Current market price in USD
            
        Raises:
            MarketDataError: If price data cannot be retrieved
        """
        try:
            await self._ensure_clients()
                
            price = float(self.info.all_mids()[self.info.name_to_coin[coin.upper()]])
            if price <= 0:
                raise MarketDataError(f"Invalid price received for {coin}: {price}")
            return price
        except Exception as e:
            error_msg = f"Error getting current price for {coin}: {str(e)}"
            logger.error(error_msg)
            raise MarketDataError(error_msg)

    async def get_price_change_1h(self, coin: str) -> float:
        """Get 1-hour price change percentage from Binance.US API.
        
        Args:
            coin (str): The trading pair symbol (e.g., 'BTC', 'ETH')
            
        Returns:
            float: 1-hour price change percentage
            
        Raises:
            MarketDataError: If price data cannot be retrieved
        """
        try:
            symbol = f"{coin.upper()}USDT"
            url = f"https://api.binance.us/api/v3/klines"
            params = {
                "symbol": symbol,
                "interval": "1h",
                "limit": 2
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        klines = await response.json()
                        if len(klines) >= 2:
                            previous_close = float(klines[-2][4])
                            current_close = float(klines[-1][4])
                            
                            if previous_close > 0:
                                price_change_pct = ((current_close - previous_close) / previous_close) * 100
                                logger.debug(f"1h price change for {coin}: {price_change_pct:.2f}%")
                                return price_change_pct
                            else:
                                logger.warning(f"Invalid previous close price for {coin}")
                                return 0.0
                        else:
                            logger.warning(f"Insufficient kline data for {coin}")
                            return 0.0
                    else:
                        logger.warning(f"Binance API returned status {response.status} for {coin}")
                        return 0.0
                        
        except Exception as e:
            logger.warning(f"Error getting 1h price change for {coin} from Binance: {str(e)}")
            return 0.0

    async def get_entry_price(self, coin: str) -> float:
        """Get entry price for an existing position.
        
        Args:
            coin (str): The trading pair symbol (e.g., 'BTC', 'ETH')
            
        Returns:
            float: Entry price in USD
            
        Raises:
            MarketDataError: If entry price data cannot be retrieved
        """
        try:
            await self._ensure_clients()
            
            user_state = self.info.user_state(self.wallet.address)
            positions = user_state.get('assetPositions', [])
            
            for position in positions:
                if position.get('position', {}).get('coin') == coin.upper():
                    entry_price = float(position['position'].get('entryPx', 0))
                    if entry_price <= 0:
                        raise MarketDataError(f"Invalid entry price for {coin}: {entry_price}")
                    logger.debug(f"Entry price for {coin}: ${entry_price}")
                    return entry_price
            
            logger.debug(f"No entry price found for {coin}")
            return 0.0
            
        except Exception as e:
            error_msg = f"Error getting entry price for {coin}: {str(e)}"
            logger.error(error_msg)
            raise MarketDataError(error_msg)

    async def _get_coin_info(self, coin: str) -> Dict[str, Any]:
        """Get coin information from exchange metadata.
        
        Args:
            coin (str): The trading pair symbol (e.g., 'BTC', 'ETH')
            
        Returns:
            Dict[str, Any]: Coin information including tick size and decimals
            
        Raises:
            MarketDataError: If coin information cannot be retrieved
        """
        try:
            await self._ensure_clients()
            
            meta = self.info.meta()
            coin_info = next((asset for asset in meta['universe'] if asset['name'] == coin.upper()), None)
            if not coin_info:
                raise MarketDataError(f"Failed to find {coin} in available markets")
                
            return coin_info
        except Exception as e:
            error_msg = f"Error getting coin info for {coin}: {str(e)}"
            logger.error(error_msg)
            raise MarketDataError(error_msg)

    async def _get_tick_size(self, coin: str) -> float:
        """Get tick size for a coin.
        
        Args:
            coin (str): The trading pair symbol (e.g., 'BTC', 'ETH')
            
        Returns:
            float: Tick size for the coin
            
        Raises:
            MarketDataError: If tick size cannot be determined
        """
        try:
            coin_info = await self._get_coin_info(coin)
            
            px_step = None
            if 'tickSize' in coin_info:
                px_step = float(coin_info['tickSize'])
            elif 'tickSz' in coin_info:
                px_step = float(coin_info['tickSz'])
            elif 'minPriceIncrement' in coin_info:
                px_step = float(coin_info['minPriceIncrement'])
            elif 'stepSize' in coin_info:
                px_step = float(coin_info['stepSize'])
            else:
                if coin.upper() == 'BTC':
                    px_step = 1.0 
                else:
                    px_step = 0.01
                logger.warning(f"Tick size not found for {coin}, using default: {px_step}")
                
            logger.info(f"Using tick size {px_step} for {coin}")
            return px_step
        except Exception as e:
            error_msg = f"Error getting tick size for {coin}: {str(e)}"
            logger.error(error_msg)
            raise MarketDataError(error_msg)

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
            await self._ensure_clients()
            
            coin_info = await self._get_coin_info(coin)
            sz_decimals = int(coin_info['szDecimals'])
            px_step = await self._get_tick_size(coin)
            
            size = round(size, sz_decimals)
            
            if size <= 0:
                raise OrderError(f"Position size too small to execute: {size} {coin}")
                        
            stop_loss = round(stop_loss / px_step) * px_step
            take_profit = round(take_profit / px_step) * px_step
            
            logger.info(f"Rounded stop loss to {stop_loss} and take profit to {take_profit}")
                                                
            current_price = await self.get_current_price(coin)
            if current_price <= 0:
                raise MarketDataError(f"Failed to get current price for {coin}")
                
            limit_price = current_price
            if is_long:
                limit_price = round((current_price * 1.001) / px_step) * px_step  # 0.1% above current price
            else:
                limit_price = round((current_price * 0.999) / px_step) * px_step  # 0.1% below current price
                                    
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
            await self._ensure_clients()
            
            position_size = await self.get_position_size(coin)
            
            if position_size == 0:
                return f"No open position in {coin} to close"
            
            is_long = position_size > 0
            size = abs(position_size)
            
            try:
                await self.cancel_all_orders(coin)
            except Exception as e:
                logger.warning(f"Error cancelling orders for {coin}: {e}")
            
            current_price = await self.get_current_price(coin)
            if current_price <= 0:
                raise MarketDataError(f"Failed to get current price for {coin}")
                
            px_step = await self._get_tick_size(coin)
            
            limit_price = current_price
            if is_long:
                limit_price = round((current_price * 0.999) / px_step) * px_step  # 0.1% below current price
            else:
                limit_price = round((current_price * 1.001) / px_step) * px_step  # 0.1% above current price
            
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
            await self._ensure_clients()
            
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
            await self.cancel_all_orders(coin)
            
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
                
                max_leverage = 5  # Max leverage allowed
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
                trade_result = await self.open_position(
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
                close_result = await self.close_position(coin)
                logger.info(f"Closed existing position: {close_result}")
                
                logger.info(f"Using strategy data: position_size={position_size_coin:.6f} {coin}, leverage={leverage:.2f}x")
                logger.info(f"Stop loss: ${stop_loss:.2f}, Take profit: ${take_profit:.2f}")
                logger.info(f"Trade direction: {direction}, Confidence: {confidence:.2%}")
                
                max_leverage = 5  # Max leverage allowed
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
                trade_result = await self.open_position(
                    coin=coin,
                    is_long=is_long,
                    size=position_size_coin,
                    stop_loss=stop_loss,
                    take_profit=take_profit
                )
                
                return f"Reversed to {direction} position in {coin}: {trade_result}"
            
            elif action == 'close':
                logger.debug(f"Closing position as instructed by signal service")
                close_result = await self.close_position(coin)
                return f"Closed position in {coin}: {close_result}"
            
            raise ValueError(f"Unknown action: {action}")
            
        except (OrderError, MarketDataError, ValueError) as e:
            raise
        except Exception as e:
            error_msg = f"Error executing trade signal: {str(e)}"
            logger.error(error_msg)
            raise OrderError(error_msg)

    async def cleanup(self):
        """Clean up any open connections and resources.
        
        This method:
        1. Closes the exchange websocket connection
        2. Closes the exchange HTTP session
        3. Closes the info client session
        4. Cancels any pending tasks
        
        This should be called when shutting down the trading system to ensure
        proper cleanup of resources.
        
        Raises:
            ExchangeError: If cleanup fails
        """
        try:
            if hasattr(self, 'exchange') and self.exchange:
                if hasattr(self.exchange, 'ws') and self.exchange.ws:
                    try:
                        logger.info("Closing exchange websocket connection")
                        await self.exchange.ws.close()
                    except Exception as e:
                        logger.error(f"Error closing exchange websocket: {e}")
                
                if hasattr(self.exchange, 'session') and self.exchange.session:
                    try:
                        logger.info("Closing exchange session")
                        if hasattr(self.exchange.session, 'close') and callable(self.exchange.session.close):
                            if asyncio.iscoroutinefunction(self.exchange.session.close):
                                await self.exchange.session.close()
                            else:
                                self.exchange.session.close()
                    except Exception as e:
                        logger.error(f"Error closing exchange session: {e}")
            
            if hasattr(self, 'info') and self.info:
                if hasattr(self.info, 'session') and self.info.session:
                    try:
                        logger.info("Closing info session")
                        if hasattr(self.info.session, 'close') and callable(self.info.session.close):
                            if asyncio.iscoroutinefunction(self.info.session.close):
                                await self.info.session.close()
                            else:
                                self.info.session.close()
                    except Exception as e:
                        logger.error(f"Error closing info session: {e}")
            
            self.exchange = None
            self.info = None
            
            for task in asyncio.all_tasks():
                if task is not asyncio.current_task():
                    task.cancel()
            
            logger.info("Cleaned up all connections and tasks")
        except Exception as e:
            error_msg = f"Error during cleanup: {str(e)}"
            logger.error(error_msg)
            raise ExchangeError(error_msg)
