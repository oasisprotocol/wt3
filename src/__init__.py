"""WT3 (Wolf of Trading Tokens in TEE) - Automated Trading and Social Media Agent."""

import logging
import os
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
)

logger = logging.getLogger(__name__)
logger.info("Environment variables loaded from .env file")

if os.getenv('DEBUG', 'false').lower() == 'true':
    logging.getLogger().setLevel(logging.DEBUG)
    logger.debug("Debug logging enabled")
