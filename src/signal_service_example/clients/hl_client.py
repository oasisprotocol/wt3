"""
Hyperliquid exchange client for WT3.

This module provides functionality for interacting with the Hyperliquid exchange.
"""

import logging
from eth_account import Account
from hyperliquid.info import Info
from hyperliquid.exchange import Exchange
from hyperliquid.utils import constants

logger = logging.getLogger(__name__)

class HyperliquidError(Exception):
    """Base exception for Hyperliquid client errors."""
    pass

class AuthenticationError(HyperliquidError):
    """Exception raised when authentication or wallet operations fail."""
    pass

class MarketDataError(HyperliquidError):
    """Exception raised when market data operations fail."""
    pass

class TradingError(HyperliquidError):
    """Exception raised when trading operations fail."""
    pass

class InitializationError(HyperliquidError):
    """Exception raised when client initialization fails."""
    pass

class HyperliquidClient:
    """
    Client for interacting with Hyperliquid exchange.
    
    This class provides functionality for:
    - Account management and balance queries
    - Market data retrieval
    - Trading operations
    - Fund transfers between accounts
    - Staking and delegation operations
    
    Attributes:
        wallet (Account): Ethereum wallet for signing transactions
        info (Info): Hyperliquid Info client for market data
        exchange (Exchange): Hyperliquid Exchange client for trading
    """
    
    def __init__(self, private_key: str) -> None:
        """Initialize Hyperliquid client with private key.
        
        Args:
            private_key (str): Private key for wallet authentication
            
        Raises:
            InitializationError: If client initialization fails
            AuthenticationError: If wallet initialization fails
            MarketDataError: If market data client initialization fails
            TradingError: If exchange client initialization fails
        """
        try:
            if not private_key:
                error_msg = "Private key is required for initialization"
                logger.error(error_msg)
                raise InitializationError(error_msg)

            try:
                self.wallet = Account.from_key(private_key)
                logger.debug(f"Wallet initialized for address: {self.wallet.address}")
            except Exception as e:
                error_msg = f"Failed to initialize wallet: {str(e)}"
                logger.error(error_msg)
                raise AuthenticationError(error_msg)

            try:
                self.info = Info(base_url=constants.MAINNET_API_URL)
                logger.debug("Market data client initialized")
            except Exception as e:
                error_msg = f"Failed to initialize market data client: {str(e)}"
                logger.error(error_msg)
                raise MarketDataError(error_msg)

            try:
                self.exchange = Exchange(
                    wallet=self.wallet,
                    base_url=constants.MAINNET_API_URL,
                    meta=self.info.meta()
                )
                logger.debug("Exchange client initialized")
            except Exception as e:
                error_msg = f"Failed to initialize exchange client: {str(e)}"
                logger.error(error_msg)
                raise TradingError(error_msg)

            logger.info(f"Successfully initialized Hyperliquid client for address: {self.wallet.address}")
        except (AuthenticationError, MarketDataError, TradingError):
            raise
        except Exception as e:
            error_msg = f"Unexpected error during client initialization: {str(e)}"
            logger.error(error_msg)
            raise InitializationError(error_msg)
        
    def get_account_balance(self) -> float:
        """Get account balance from Hyperliquid.
        
        Returns:
            float: Account balance in USD
            
        Raises:
            MarketDataError: If balance retrieval fails
        """
        try:
            user_state = self.info.user_state(self.wallet.address)
            perp_balance = float(user_state.get('withdrawable', 0))
            logger.info(f"Perp Account balance: ${perp_balance}")
            return perp_balance
        except Exception as e:
            error_msg = f"Error getting account balance: {str(e)}"
            logger.error(error_msg)
            raise MarketDataError(error_msg)

    def get_current_position(self, coin: str) -> float:
        """Get current position size for a given coin.
        
        Args:
            coin (str): Trading pair symbol (e.g., 'BTC', 'ETH')
            
        Returns:
            float: Current position size. Positive for long positions,
                  negative for short positions, 0.0 if no position exists
                  
        Raises:
            MarketDataError: If position data retrieval fails
        """
        try:
            user_state = self.info.user_state(self.wallet.address)
            positions = user_state.get('assetPositions', [])
            
            for position in positions:
                if position.get('position', {}).get('coin') == coin.upper():
                    return float(position['position']['szi'])
            
            logger.debug(f"No position found for {coin}")
            return 0.0
            
        except Exception as e:
            error_msg = f"Error getting position size for {coin}: {str(e)}"
            logger.error(error_msg)
            raise MarketDataError(error_msg)
