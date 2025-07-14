"""
Market data client for Signal Service Example.

This module provides functionality for fetching cryptocurrency market data
from Binance API, including historical price data and current prices.
"""

import aiohttp
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

class MarketDataError(Exception):
    """Base exception for market data operations."""
    pass

class APIError(MarketDataError):
    """Exception raised when API requests fail."""
    pass

class MarketDataClient:
    """Client for fetching market data from Binance."""
    
    def __init__(self):
        self.base_url = "https://api.binance.us/api/v3"
        self._session = None
        
    async def get_klines(self, symbol: str, interval: str, limit: int = 100) -> List[Dict]:
        """
        Fetch kline/candlestick data.
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTCUSDT')
            interval: Kline interval (e.g., '1h', '4h', '1d')
            limit: Number of klines to fetch
            
        Returns:
            List of kline data dictionaries
        """
        try:
            binance_symbol = f"{symbol}USDT" if not symbol.endswith('USDT') else symbol
            
            url = f"{self.base_url}/klines"
            params = {
                'symbol': binance_symbol,
                'interval': interval,
                'limit': limit
            }
            
            async with self._session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    klines = []
                    for k in data:
                        klines.append({
                            'timestamp': k[0],
                            'open': float(k[1]),
                            'high': float(k[2]),
                            'low': float(k[3]),
                            'close': float(k[4]),
                            'volume': float(k[5])
                        })
                    
                    return klines
                else:
                    error_msg = f"Failed to fetch klines: {response.status}"
                    logger.error(error_msg)
                    raise APIError(error_msg)
                    
        except aiohttp.ClientError as e:
            error_msg = f"Network error fetching klines for {symbol}: {e}"
            logger.error(error_msg)
            raise APIError(error_msg)
        except Exception as e:
            error_msg = f"Unexpected error fetching klines for {symbol}: {e}"
            logger.error(error_msg)
            raise MarketDataError(error_msg)
    
    async def get_current_price(self, symbol: str) -> float:
        """
        Get current price for a symbol.
        
        Args:
            symbol: Trading pair symbol
            
        Returns:
            Current price
        """
        try:
            binance_symbol = f"{symbol}USDT" if not symbol.endswith('USDT') else symbol
            
            url = f"{self.base_url}/ticker/price"
            params = {'symbol': binance_symbol}
            
            async with self._session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return float(data['price'])
                else:
                    error_msg = f"Failed to fetch price: {response.status}"
                    logger.error(error_msg)
                    raise APIError(error_msg)
                    
        except aiohttp.ClientError as e:
            error_msg = f"Network error fetching price for {symbol}: {e}"
            logger.error(error_msg)
            raise APIError(error_msg)
        except Exception as e:
            error_msg = f"Unexpected error fetching price for {symbol}: {e}"
            logger.error(error_msg)
            raise MarketDataError(error_msg)