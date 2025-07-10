"""
Trading module for the WT3 Agent.

This module provides functionality for executing trades on the Hyperliquid exchange,
including position management, order execution, and trade signal processing.
"""

from .exceptions import (
    TradingError,
    WalletError,
    MarketDataError,
    OrderError,
    ExchangeError
)
from .exchange_client import ExchangeClient
from .market_data import MarketDataProvider
from .order_management import OrderManager
from .signal_execution import SignalExecutor


class TradeTools:
    """Trading tools for executing trades on Hyperliquid exchange.
    
    This class provides methods for managing trading positions and executing orders
    on the Hyperliquid exchange. It uses limit orders for better execution prices
    and implements stop-loss and take-profit orders for risk management.
    
    Attributes:
        exchange_client (ExchangeClient): Client for exchange operations
        market_data (MarketDataProvider): Provider for market data
        order_manager (OrderManager): Manager for order operations
        signal_executor (SignalExecutor): Executor for trading signals
    """
    
    def __init__(self):
        """Initialize trading tools with all required components."""
        self.exchange_client = ExchangeClient()
        self.market_data = MarketDataProvider(self.exchange_client)
        self.order_manager = OrderManager(self.exchange_client, self.market_data)
        self.signal_executor = SignalExecutor(self.exchange_client, self.order_manager)
        
        self.wallet = self.exchange_client.wallet
        self.exchange = self.exchange_client.exchange
        self.info = self.exchange_client.info
        self.base_url = self.exchange_client.base_url

    async def get_position_size(self, coin: str) -> float:
        """Get current position size for a given coin."""
        return await self.market_data.get_position_size(coin)
    
    async def get_current_price(self, coin: str) -> float:
        """Get current market price for a coin."""
        return await self.market_data.get_current_price(coin)
    
    async def get_price_change_1h(self, coin: str) -> float:
        """Get 1-hour price change percentage."""
        return await self.market_data.get_price_change_1h(coin)
    
    async def get_entry_price(self, coin: str) -> float:
        """Get entry price for an existing position."""
        return await self.market_data.get_entry_price(coin)
    
    async def open_position(self, coin: str, is_long: bool, size: float, 
                           stop_loss: float, take_profit: float) -> str:
        """Open a new position with stop loss and take profit orders."""
        return await self.order_manager.open_position(coin, is_long, size, stop_loss, take_profit)
    
    async def close_position(self, coin: str) -> str:
        """Close an existing position."""
        return await self.order_manager.close_position(coin)
    
    async def cancel_all_orders(self, coin: str) -> str:
        """Cancel all open orders for a given coin."""
        return await self.order_manager.cancel_all_orders(coin)
    
    async def execute_trade_signal(self, signal: dict) -> str:
        """Execute trade based on signal from signal service."""
        return await self.signal_executor.execute_trade_signal(signal)


__all__ = [
    'TradeTools',
    'TradingError',
    'WalletError',
    'MarketDataError',
    'OrderError',
    'ExchangeError'
]