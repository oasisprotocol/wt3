"""
Market data retrieval for the WT3 Agent.

This module provides functionality for retrieving market data from the exchange,
including prices, positions, and coin information.
"""

import logging
import aiohttp
from typing import Dict, Any

from .exceptions import MarketDataError

logger = logging.getLogger(__name__)


class MarketDataProvider:
    """Provides market data retrieval functionality."""
    
    def __init__(self, exchange_client):
        """Initialize with exchange client reference.
        
        Args:
            exchange_client: The ExchangeClient instance
        """
        self.exchange_client = exchange_client
        self.info = exchange_client.info
        self.wallet = exchange_client.wallet

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
            await self.exchange_client.ensure_clients()
            
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
            await self.exchange_client.ensure_clients()
                
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
            await self.exchange_client.ensure_clients()
            
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

    async def get_coin_info(self, coin: str) -> Dict[str, Any]:
        """Get coin information from exchange metadata.
        
        Args:
            coin (str): The trading pair symbol (e.g., 'BTC', 'ETH')
            
        Returns:
            Dict[str, Any]: Coin information including tick size and decimals
            
        Raises:
            MarketDataError: If coin information cannot be retrieved
        """
        try:
            await self.exchange_client.ensure_clients()
            
            meta = self.info.meta()
            coin_info = next((asset for asset in meta['universe'] if asset['name'] == coin.upper()), None)
            if not coin_info:
                raise MarketDataError(f"Failed to find {coin} in available markets")
                
            return coin_info
        except Exception as e:
            error_msg = f"Error getting coin info for {coin}: {str(e)}"
            logger.error(error_msg)
            raise MarketDataError(error_msg)

    async def get_tick_size(self, coin: str) -> float:
        """Get tick size for a coin.
        
        Args:
            coin (str): The trading pair symbol (e.g., 'BTC', 'ETH')
            
        Returns:
            float: Tick size for the coin
            
        Raises:
            MarketDataError: If tick size cannot be determined
        """
        try:
            coin_info = await self.get_coin_info(coin)
            
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