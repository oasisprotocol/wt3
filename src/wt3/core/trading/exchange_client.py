"""
Exchange client initialization for the WT3 Agent.

This module handles the initialization of Hyperliquid exchange clients
and wallet setup.
"""

import logging
from eth_account import Account
from hyperliquid.info import Info
from hyperliquid.exchange import Exchange
from hyperliquid.utils import constants

from .exceptions import WalletError, ExchangeError

logger = logging.getLogger(__name__)


class ExchangeClient:
    """Manages exchange client initialization and wallet setup."""
    
    def __init__(self):
        """Initialize trading clients and wallet.
        
        Sets up the Hyperliquid API clients and initializes the trading wallet
        using ROFL key management.
        
        Raises:
            WalletError: If keypair generation or wallet initialization fails
            ExchangeError: If exchange client initialization fails
        """
        from ...clients.rofl import get_keypair
        
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

    async def ensure_clients(self) -> None:
        """Ensure exchange clients are properly initialized.
        
        Recreates clients if they are None, which can happen during reconnection.
        
        Raises:
            ExchangeError: If client re-initialization fails
        """
        if self.info is None or self.exchange is None:
            logger.info("Re-initializing exchange clients")
            try:
                self.info = Info(base_url=self.base_url)
                meta = self.info.meta()
                
                self.exchange = Exchange(
                    wallet=self.wallet,
                    base_url=self.base_url,
                    meta=meta
                )
            except Exception as e:
                error_msg = f"Failed to re-initialize exchange clients: {str(e)}"
                logger.error(error_msg)
                raise ExchangeError(error_msg)
