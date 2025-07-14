"""
Signal client for the WT3 Agent.

This module provides functionality for retrieving trading signals from the signal service,
including market predictions, confidence levels, and trade decisions.
"""

import logging
import aiohttp
import os
import asyncio
from typing import Dict, Optional, TypedDict, Literal

logger = logging.getLogger(__name__)

class StrategyData(TypedDict):
    """Trading strategy data structure."""
    position_size_coin: float
    leverage: float
    stop_loss: float
    take_profit: float

class CurrentPosition(TypedDict):
    """Current position data structure."""
    size: float
    direction: Literal['LONG', 'SHORT']
    entry_price: Optional[float]

class TradeDecision(TypedDict):
    """Trade decision data structure."""
    action: Literal['open', 'close', 'close_and_reverse']
    direction: Literal['long', 'short']
    confidence: float
    coin: str
    strategy: StrategyData

class SignalResponse(TypedDict):
    """Complete signal response structure."""
    timestamp: int
    trade_decision: Optional[TradeDecision]
    current_position: Optional[CurrentPosition]

class SignalError(Exception):
    """Base exception for signal client errors."""
    pass

class SignalValidationError(SignalError):
    """Exception raised when signal data validation fails."""
    pass

class SignalServiceError(SignalError):
    """Exception raised when signal service operations fail."""
    pass

class SignalClient:
    """Client for retrieving trading signals from the signal service."""
    
    def __init__(self):
        """Initialize the signal client.
        
        Raises:
            SignalError: If client initialization fails
        """
        try:
            self.base_url = os.getenv("SIGNAL_SERVICE_URL")
            self.fallback_url = "http://127.0.0.1:8001"
            self._session = None
            self._using_fallback = False
            logger.info(f"Signal client initialized with base URL: {self.base_url}")
        except Exception as e:
            error_msg = f"Failed to initialize signal client: {str(e)}"
            logger.error(error_msg)
            raise SignalError(error_msg)

    @property
    def session(self) -> aiohttp.ClientSession:
        """Get or create the aiohttp session.
        
        Returns:
            aiohttp.ClientSession: The client session
        """
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def check_health(self, use_fallback: bool = False) -> bool:
        """Check if the signal service is healthy.
        
        Args:
            use_fallback: Whether to check the fallback service
        
        Returns:
            bool: True if service is healthy, False otherwise
        """
        try:
            url = f"{self.fallback_url if use_fallback else self.base_url}/health"
            async with self.session.get(url, timeout=5) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("status") == "healthy"
                logger.warning(f"Health check failed with status {response.status}")
                return False
                
        except asyncio.TimeoutError:
            logger.warning("Health check timed out")
            return False
        except aiohttp.ClientError as e:
            logger.warning(f"Health check failed with client error: {e}")
            return False
        except Exception as e:
            logger.warning(f"Health check failed with unexpected error: {e}")
            return False

    async def wait_for_health(self, timeout: int = 30) -> bool:
        """Wait for the signal service to become healthy.
        
        Args:
            timeout (int): Maximum time to wait in seconds
            
        Returns:
            bool: True if service became healthy, False if timed out
        """
        start_time = asyncio.get_event_loop().time()
        current_interval = 1
        consecutive_failures = 0
        
        while True:
            if await self.check_health():
                if consecutive_failures > 0:
                    logger.info("Signal service is now healthy")
                return True
                
            consecutive_failures += 1
            elapsed_time = asyncio.get_event_loop().time() - start_time
            
            if elapsed_time > timeout:
                logger.error(f"Timed out waiting for signal service after {timeout} seconds")
                return False
                
            wait_time = min(current_interval * (2 ** (consecutive_failures - 1)), 5)
            logger.debug(f"Health check failed, retrying in {wait_time:.1f} seconds")
            await asyncio.sleep(wait_time)

    def _validate_signal_response(self, data: Dict) -> SignalResponse:
        """Validate the signal response data.
        
        Args:
            data (Dict): Raw signal response data
            
        Returns:
            SignalResponse: Validated signal response
            
        Raises:
            SignalValidationError: If validation fails
        """
        try:
            if 'timestamp' not in data or not isinstance(data['timestamp'], int):
                raise SignalValidationError("Missing or invalid timestamp field")
            
            if 'trade_decision' in data and data['trade_decision'] is not None:
                trade_decision = data['trade_decision']
                if not isinstance(trade_decision, dict):
                    raise SignalValidationError("Invalid trade_decision: must be a dictionary")
                
                required_trade_fields = {
                    'action': str,
                    'direction': str,
                    'confidence': float,
                    'coin': str,
                    'strategy': dict
                }
                
                for field, field_type in required_trade_fields.items():
                    if field not in trade_decision:
                        raise SignalValidationError(f"Missing required field in trade_decision: {field}")
                    if not isinstance(trade_decision[field], field_type):
                        raise SignalValidationError(f"Invalid type for trade_decision.{field}: expected {field_type.__name__}, got {type(trade_decision[field]).__name__}")
                
                if trade_decision['action'] not in ('open', 'close', 'close_and_reverse'):
                    raise SignalValidationError(f"Invalid trade action: {trade_decision['action']}")
                
                if trade_decision['direction'] not in ('long', 'short'):
                    raise SignalValidationError(f"Invalid trade direction: {trade_decision['direction']}")
                
                if not 0 <= trade_decision['confidence'] <= 1:
                    raise SignalValidationError(f"Invalid confidence value: {trade_decision['confidence']}")
                
                strategy = trade_decision['strategy']
                required_strategy_fields = {
                    'position_size_coin': float,
                    'leverage': float,
                    'stop_loss': float,
                    'take_profit': float
                }
                
                for field, field_type in required_strategy_fields.items():
                    if field not in strategy:
                        raise SignalValidationError(f"Missing required field in strategy: {field}")
                    if not isinstance(strategy[field], field_type):
                        raise SignalValidationError(f"Invalid type for strategy.{field}: expected {field_type.__name__}, got {type(strategy[field]).__name__}")
            
            return data
            
        except SignalValidationError:
            raise
        except Exception as e:
            error_msg = f"Error validating signal response: {str(e)}"
            logger.error(error_msg)
            raise SignalValidationError(error_msg)

    async def get_prediction(self, coin: str, max_retries: int = 3, retry_delay: float = 1.0) -> Optional[SignalResponse]:
        """Get trading signal prediction for a specific coin.
        
        Args:
            coin (str): The coin symbol (e.g., 'BTC', 'ETH')
            max_retries (int): Maximum number of retry attempts
            retry_delay (float): Delay between retries in seconds
            
        Returns:
            Optional[SignalResponse]: The validated signal response, or None if all retries failed
            
        Raises:
            SignalServiceError: If the service is unhealthy or request fails after all retries
        """
        retry_count = 0
        last_error = None
        
        while retry_count < max_retries:
            try:
                url = f"{self.base_url}/signal/{coin}"
                logger.info(f"Requesting prediction from {url} (attempt {retry_count + 1}/{max_retries})")
                
                async with self.session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"Received prediction data: {data}")
                        return self._validate_signal_response(data)
                    else:
                        error_msg = f"Signal service returned error: {response.status} - {await response.text()}"
                        logger.warning(f"Attempt {retry_count + 1} failed: {error_msg}")
                        last_error = SignalServiceError(error_msg)
                        
            except (aiohttp.ClientError, SignalValidationError) as e:
                logger.warning(f"Attempt {retry_count + 1} failed: {str(e)}")
                last_error = e
            except Exception as e:
                logger.warning(f"Attempt {retry_count + 1} failed with unexpected error: {str(e)}")
                last_error = e

            retry_count += 1
            if retry_count < max_retries:
                wait_time = retry_delay * (2 ** (retry_count - 1))
                logger.info(f"Retrying in {wait_time:.1f} seconds...")
                await asyncio.sleep(wait_time)

        logger.warning(f"All {max_retries} attempts to primary service failed. Trying fallback service...")
        
        fallback_healthy = await self.check_health(use_fallback=True)
        if not fallback_healthy:
            logger.error("Fallback signal service is also unavailable")
            return None
            
        logger.warning("Using fallback signal_service_example")
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                url = f"{self.fallback_url}/signal/{coin}"
                logger.info(f"Requesting prediction from fallback {url} (attempt {retry_count + 1}/{max_retries})")
                
                async with self.session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"Received prediction data from fallback: {data}")
                        return self._validate_signal_response(data)
                    else:
                        error_msg = f"Fallback service returned error: {response.status} - {await response.text()}"
                        logger.warning(f"Fallback attempt {retry_count + 1} failed: {error_msg}")
                        last_error = SignalServiceError(error_msg)
                        
            except (aiohttp.ClientError, SignalValidationError) as e:
                logger.warning(f"Fallback attempt {retry_count + 1} failed: {str(e)}")
                last_error = e
            except Exception as e:
                logger.warning(f"Fallback attempt {retry_count + 1} failed with unexpected error: {str(e)}")
                last_error = e

            retry_count += 1
            if retry_count < max_retries:
                wait_time = retry_delay * (2 ** (retry_count - 1))
                logger.info(f"Retrying fallback in {wait_time:.1f} seconds...")
                await asyncio.sleep(wait_time)
        
        logger.error(f"All attempts to both primary and fallback services failed. Last error: {str(last_error)}")
        return None

    async def close(self):
        """Close the client session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
            logger.info("Signal client session closed")

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
        return None
