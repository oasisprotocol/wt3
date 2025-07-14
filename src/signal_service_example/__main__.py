"""Main entry point for running the Signal Service Example."""

import logging
import sys
import os
import signal
from .api.routes import start_api_server

logger = logging.getLogger(__name__)

def force_exit():
    """Force the script to exit by sending SIGTERM to itself."""
    logger.info("Forcing script to exit...")
    os.kill(os.getpid(), signal.SIGTERM)

def main():
    """Main function that runs the signal service example."""
    logger.info("Starting Signal Service Example")
    
    try:
        start_api_server(host='0.0.0.0', port=8001)
        return True
        
    except KeyboardInterrupt:
        logger.info("Signal Service Example interrupted by user")
    except Exception as e:
        logger.error(f"Unhandled exception in main: {e}")
        return False
    
    return True

if __name__ == "__main__":
    try:
        result = main()
        
        logger.info("Signal Service Example completed successfully" if result else "Signal Service Example completed with errors")
        
        force_exit()
        
    except KeyboardInterrupt:
        logger.info("Signal Service Example interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Unhandled exception: {e}")
        sys.exit(1)