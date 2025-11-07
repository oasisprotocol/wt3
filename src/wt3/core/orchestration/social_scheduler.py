"""
Social media task scheduling for the WT3 Agent.

This module handles the scheduling and execution of social media tasks
including mention checking and whitelist account monitoring.
"""

import logging
from datetime import datetime
from typing import Dict, Any

from ...clients.social import SocialClient, SocialClientError

logger = logging.getLogger(__name__)


async def run_social_tasks() -> Dict[str, Any]:
    """Run social media tasks like checking mentions and monitoring whitelist accounts.
    
    This function:
    1. Creates a SocialClient instance
    2. Calls the run_periodic_tasks method to check mentions and monitor whitelist accounts
    3. Runs every 10 minutes independently of the trading cycle
    4. Ensures isolation from trading cycles to prevent interference
    
    Returns:
        Dict[str, Any]: Summary of tasks performed
        
    Raises:
        SocialClientError: If social media operations fail
    """
    start_time = datetime.now()
    logger.info("🔔 Initiating 10-minute social media cycle")
    
    try:
        social_client = SocialClient()
        result = await social_client.run_periodic_tasks(hours=0.1667)
        
        execution_time = (datetime.now() - start_time).total_seconds()
        
        if result.get('skipped'):
            logger.info(f"⏭️ Social tasks skipped: {result.get('reason')} (checked in {execution_time:.1f}s)")
        else:
            mentions_count = result.get('mentions_processed', 0)
            logger.info(f"📱 Social media cycle completed: {mentions_count} mentions processed in {execution_time:.1f}s")
        
        return result
    except Exception as e:
        error_msg = f"Error in social media cycle after {(datetime.now() - start_time).total_seconds():.1f}s: {str(e)}"
        logger.error(error_msg)
        raise SocialClientError(error_msg) from e
