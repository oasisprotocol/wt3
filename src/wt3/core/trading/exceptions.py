"""
Trading exceptions for the WT3 Agent.

This module defines all trading-related exceptions used throughout
the trading system.
"""


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