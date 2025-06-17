"""
Initialize the prompts module and handle loading of social prompts.
"""

import logging

logger = logging.getLogger(__name__)

def load_social_prompts():
    """
    Load social prompts from either the actual file or template.
    Returns the prompts module.
    """
    try:
        from . import social_prompts
        return social_prompts
    except ImportError:
        logger.warning("social_prompts.py not found, using template. Please copy social_prompts_template.py to social_prompts.py and fill in your prompts.")
        from . import social_prompts_template as social_prompts
        return social_prompts

prompts = load_social_prompts() 