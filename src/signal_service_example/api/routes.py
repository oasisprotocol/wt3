"""
REST API for the Signal Service Example.

This module provides HTTP endpoints for accessing momentum-based trading signals
and system health. It handles request validation, error handling, and response
formatting for the Signal Service Example API.
"""

import logging
from flask import Flask, jsonify
from ..core.momentum_strategy import MomentumStrategy

logger = logging.getLogger(__name__)

class APIError(Exception):
    """Base exception for API-related errors."""
    pass

class ValidationError(APIError):
    """Exception raised when request validation fails."""
    pass

class ServiceError(APIError):
    """Exception raised when service operations fail."""
    pass

app = Flask(__name__)
momentum_strategy = MomentumStrategy()

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint.
    
    This endpoint verifies that the Signal Service Example is operational.
    
    Returns:
        JSON response with service status:
        {
            "status": "healthy"
        }
        
    Raises:
        APIError: If health check fails
    """
    try:
        return jsonify({"status": "healthy"})
    except Exception as e:
        error_msg = f"Health check failed: {str(e)}"
        logger.error(error_msg)
        raise APIError(error_msg)

@app.route('/signal/<coin>', methods=['GET'])
def get_signal(coin):
    """
    Get trading signal for a specific coin.
    
    This endpoint retrieves momentum-based trading signals for the specified coin,
    including market direction, confidence levels, and trading decisions.
    
    Args:
        coin (str): The coin symbol (e.g., 'BTC', 'ETH')
        
    Returns:
        JSON response with signal data:
        {
            "timestamp": int,  # unix timestamp
            "trade_decision": {  # optional, null if no trade is needed
                "action": str,  # 'open', 'close', or 'close_and_reverse'
                "direction": str,  # 'long' or 'short'
                "confidence": float,  # between 0 and 1
                "coin": str,
                "strategy": {
                    "position_size_coin": float,  # Position size in coin units
                    "leverage": float,  # Leverage to use
                    "stop_loss": float,  # Stop loss price level
                    "take_profit": float  # Take profit price level
                }
            },
            "current_position": {  # optional, null if no position
                "size": float,  # Position size
                "direction": str,  # 'LONG' or 'SHORT' (uppercase)
                "entry_price": float  # Entry price, can be null
            }
        }
        
    Raises:
        ValidationError: If coin parameter is invalid
        ServiceError: If signal service operations fail
        APIError: For unexpected errors
    """
    try:
        if not coin or not isinstance(coin, str):
            error_msg = f"Invalid coin parameter: {coin}"
            logger.error(error_msg)
            raise ValidationError(error_msg)
            
        logger.info(f"Received signal request for {coin}")
        import asyncio
        import time
        prediction = asyncio.run(momentum_strategy.get_signal(coin))
        
        if not prediction:
            error_msg = f"No prediction available for {coin}"
            logger.warning(error_msg)
            return jsonify({"error": error_msg}), 404
        
        prediction['timestamp'] = int(time.time())
        return jsonify(prediction)
        
    except ValidationError as e:
        logger.error(f"Validation error for {coin}: {str(e)}")
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        error_msg = f"Unexpected error getting signal for {coin}: {str(e)}"
        logger.error(error_msg)
        return jsonify({"error": error_msg}), 500

def start_api_server(host='0.0.0.0', port=8001):
    """Start the Flask API server.
    
    This function initializes and starts the Flask web server for the Signal Service Example API.
    It configures the server with the specified host and port settings.
    
    Args:
        host (str, optional): Server host address. Defaults to '0.0.0.0'
        port (int, optional): Server port number. Defaults to 8000
        
    Raises:
        APIError: If server startup fails
    """
    try:
        logger.info(f"Starting Signal Service Example API on {host}:{port}")
        app.run(host=host, port=port)
    except Exception as e:
        error_msg = f"Failed to start API server: {str(e)}"
        logger.error(error_msg)
        raise APIError(error_msg)