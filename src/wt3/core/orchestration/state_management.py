"""
State management for the WT3 Agent.

This module manages the trading state including activity tracking
and social media update timestamps.
"""

import logging
from datetime import datetime
from collections import deque
from typing import Dict, Optional, List, Any, Deque

logger = logging.getLogger(__name__)


class TradingStateError(Exception):
    """Base exception for trading state errors."""
    pass


class TradingState:
    """Maintains the state of trading activities and social media updates."""
    
    def __init__(self, max_activities: int = 20):
        """Initialize trading state.
        
        Args:
            max_activities (int, optional): Maximum number of activities to store. Defaults to 20.
            
        Raises:
            TradingStateError: If state initialization fails
        """
        try:
            self.trade_activities: Deque[Dict[str, Any]] = deque(maxlen=max_activities)
            self.last_tweet_time: Optional[datetime] = None
            self.is_running = True
        except Exception as e:
            error_msg = f"Failed to initialize trading state: {str(e)}"
            logger.error(error_msg)
            raise TradingStateError(error_msg)
        
    def add_activity(self, coin: str, action: str, details: Optional[Dict[str, Any]] = None) -> None:
        """Add a trading activity to the state.
        
        Args:
            coin (str): The trading pair symbol
            action (str): The action taken (e.g., "no_signal", "executed", "closed")
            details (Optional[Dict[str, Any]], optional): Additional details about the action. Defaults to None.
            
        Raises:
            TradingStateError: If activity cannot be added
        """
        try:
            activity = {
                "timestamp": datetime.now(),
                "coin": coin,
                "action": action
            }
            
            if details:
                activity.update(details)
                
            self.trade_activities.append(activity)
        except Exception as e:
            error_msg = f"Failed to add activity to state: {str(e)}"
            logger.error(error_msg)
            raise TradingStateError(error_msg)
        
    def get_activities(self) -> List[Dict[str, Any]]:
        """Get all current trading activities.
        
        Returns:
            List[Dict[str, Any]]: List of current activities
            
        Raises:
            TradingStateError: If activities cannot be retrieved
        """
        try:
            return list(self.trade_activities)
        except Exception as e:
            error_msg = f"Failed to get activities from state: {str(e)}"
            logger.error(error_msg)
            raise TradingStateError(error_msg)
        
    def clear_activities(self) -> None:
        """Clear all trading activities.

        Raises:
            TradingStateError: If activities cannot be cleared
        """
        try:
            self.trade_activities.clear()
        except Exception as e:
            error_msg = f"Failed to clear activities: {str(e)}"
            logger.error(error_msg)
            raise TradingStateError(error_msg)

    def get_recent_activities(self, hours: int = 1) -> List[Dict[str, Any]]:
        """Get trading activities from the last N hours.

        Args:
            hours (int, optional): Number of hours to look back. Defaults to 1.

        Returns:
            List[Dict[str, Any]]: List of activities from the specified time period

        Raises:
            TradingStateError: If activities cannot be retrieved
        """
        try:
            from datetime import timedelta
            cutoff_time = datetime.now() - timedelta(hours=hours)
            recent_activities = [
                activity for activity in self.trade_activities
                if activity.get('timestamp', datetime.min) > cutoff_time
            ]
            return recent_activities
        except Exception as e:
            error_msg = f"Failed to get recent activities from state: {str(e)}"
            logger.error(error_msg)
            raise TradingStateError(error_msg)
