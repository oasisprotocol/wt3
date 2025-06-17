"""
Social media client for the WT3 Agent.

This module provides functionality for generating and posting trading-related content
to social media platforms, primarily Twitter/X. It includes tools for creating
hourly recaps, individual trade updates, replying to mentions, and quote retweeting.
"""

import os
import logging
import time
import json
from typing import Annotated, Dict, Optional, Tuple, Any
from datetime import datetime, timedelta
from pathlib import Path
from emp_agents import AgentBase
from emp_agents.providers import GrokProvider, GrokModelType
from typing_extensions import Doc
import tweepy

from ..prompts import prompts

logger = logging.getLogger(__name__)

CONVERSATION_HISTORY_FILE = "/storage/data/conversation_history.json"

class SocialClientError(Exception):
    """Base exception for Social Client errors."""
    pass

class TwitterAPIError(SocialClientError):
    """Exception raised when Twitter API operations fail."""
    pass

class ContentGenerationError(SocialClientError):
    """Exception raised when content generation fails."""
    pass

class RateLimitError(SocialClientError):
    """Exception raised when Twitter API rate limits are exceeded."""
    pass

class ConversationError(SocialClientError):
    """Exception raised when conversation operations fail."""
    pass

class SocialClient:
    """Social media tools for posting trading updates and recaps.
    
    This class handles the generation and posting of trading-related content to
    social media platforms. It uses AI to generate engaging content and manages
    the connection to social media APIs.
    
    Attributes:
        twitter (tweepy.Client): Twitter API client for posting tweets
        agent (AgentBase): AI agent for generating tweet content
        last_mention_id (str): ID of the last processed mention
        conversation_history (Dict): Dictionary storing conversation history
        whitelist_accounts (Set[str]): Set of account usernames to monitor for quote retweets
        last_mention_check (datetime): Timestamp of the last mention check
        last_whitelist_check (datetime): Timestamp of the last whitelist account check
    """
    
    def __init__(self):
        """Initialize social media clients and AI agent.
        
        Sets up the Twitter API client and AI agent for generating content.
        Requires environment variables for API authentication.
        
        Raises:
            TwitterAPIError: If Twitter API client initialization fails
            ContentGenerationError: If AI agent initialization fails
            ValueError: If required environment variables are missing
        """
        required_env_vars = {
            "TWITTER_BEARER_TOKEN",
            "TWITTER_API_KEY",
            "TWITTER_API_SECRET",
            "TWITTER_ACCESS_TOKEN",
            "TWITTER_ACCESS_TOKEN_SECRET",
            "GROK_API_KEY"
        }
        
        missing_vars = [var for var in required_env_vars if not os.getenv(var)]
        if missing_vars:
            raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")
        
        logger.info("Initializing Twitter API client...")
        try:
            self.twitter = tweepy.Client(
                bearer_token=os.getenv("TWITTER_BEARER_TOKEN"),
                consumer_key=os.getenv("TWITTER_API_KEY"),
                consumer_secret=os.getenv("TWITTER_API_SECRET"),
                access_token=os.getenv("TWITTER_ACCESS_TOKEN"),
                access_token_secret=os.getenv("TWITTER_ACCESS_TOKEN_SECRET"),
                wait_on_rate_limit=False
            )
            logger.info("Twitter API client initialized successfully")
            
            self.twitter_me_id = self.twitter.get_me()[0].id
            logger.info(f"Successfully got Twitter user ID: {self.twitter_me_id}")
            
        except Exception as e:
            error_msg = f"Failed to initialize Twitter API client: {str(e)}"
            logger.error(error_msg)
            raise TwitterAPIError(error_msg)
        
        try:
            self.agent = AgentBase(
                prompt=prompts.SYSTEM_PROMPT,
                provider=GrokProvider(
                    api_key=os.getenv("GROK_API_KEY"),
                    default_model=GrokModelType.grok_3
                ),
                tools=[],
                temperature=1
            )
        except Exception as e:
            error_msg = f"Failed to initialize AI agent: {str(e)}"
            logger.error(error_msg)
            raise ContentGenerationError(error_msg)
        
        self.last_mention_id = None
        self.conversation_history = {}
        self._load_conversation_history()
        
        self.whitelist_accounts = {
            "OasisProtocol",
            "HyperliquidX",
        }
        
        self.last_mention_check = datetime.now() - timedelta(minutes=9)
        self.last_whitelist_check = datetime.now() - timedelta(minutes=9)
    
    def _load_conversation_history(self) -> None:
        """Load conversation history and last mention ID from file.
        
        If the file doesn't exist, initializes with empty values.
        
        Raises:
            ConversationError: If conversation history file is corrupted
        """
        try:
            history_path = Path(CONVERSATION_HISTORY_FILE)
            if not history_path.exists():
                logger.info("No conversation history file found, starting fresh")
                self.conversation_history = {}
                self.last_mention_id = None
                return
            
            data = json.loads(history_path.read_text())
            self.conversation_history = data.get('conversations', {})
            self.last_mention_id = data.get('last_mention_id')
            logger.info(f"Loaded conversation history with {len(self.conversation_history)} conversations")
            logger.info(f"Last processed mention ID: {self.last_mention_id}")
        except json.JSONDecodeError as e:
            error_msg = f"Error parsing conversation history file: {str(e)}"
            logger.error(error_msg)
            raise ConversationError(error_msg)
        except Exception as e:
            error_msg = f"Error loading conversation history: {str(e)}"
            logger.error(error_msg)
            raise ConversationError(error_msg)
    
    def _save_conversation_history(self) -> None:
        """Save conversation history and last mention ID to file.
        
        Raises:
            ConversationError: If conversation history cannot be saved
        """
        try:
            history_path = Path(CONVERSATION_HISTORY_FILE)
            history_path.parent.mkdir(parents=True, exist_ok=True)
            
            data = {
                'conversations': self.conversation_history,
                'last_mention_id': self.last_mention_id
            }
            
            history_path.write_text(json.dumps(data, indent=2))
            logger.info(f"Saved conversation history with {len(self.conversation_history)} conversations")
        except Exception as e:
            error_msg = f"Error saving conversation history: {str(e)}"
            logger.error(error_msg)
            raise ConversationError(error_msg)

    async def generate_hourly_recap(
        self,
        position_info: Dict,
        activities_summary: Dict
    ) -> str:
        """Generate and post an hourly recap tweet summarizing trading activities.
        
        Args:
            position_info (Dict): Dictionary containing current position details
            activities_summary (Dict): Summary of trading activities in the past hour
            
        Returns:
            str: The result of posting the tweet or error message if failed
            
        Raises:
            ContentGenerationError: If content generation fails
            TwitterAPIError: If tweet posting fails
        """
        try:
            tweet_content = await self._generate_recap_content(
                position_info=position_info,
                activities_summary=activities_summary
            )
            return self._tweet(tweet_content)
            
        except ContentGenerationError as e:
            logger.error(f"Error generating recap content: {str(e)}")
            raise
        except TwitterAPIError as e:
            logger.error(f"Error posting recap tweet: {str(e)}")
            raise
        except Exception as e:
            error_msg = f"Unexpected error in generate_hourly_recap: {str(e)}"
            logger.error(error_msg)
            raise SocialClientError(error_msg)
    
    async def _generate_recap_content(
        self,
        position_info: Dict,
        activities_summary: Dict
    ) -> str:
        """Generate content for an hourly recap tweet.
        
        Args:
            position_info (Dict): Current position information
            activities_summary (Dict): Summary of trading activities
            
        Returns:
            str: Generated tweet content
            
        Raises:
            ContentGenerationError: If content generation fails
        """
        try:
            has_position = position_info.get("has_position", False)
            
            counts = activities_summary.get("counts", {})
            time_span = activities_summary.get("time_span", timedelta(hours=1))
            
            hours = time_span.total_seconds() / 3600
            time_str = f"{hours:.1f} hours" if hours >= 1 else f"{int(time_span.total_seconds() / 60)} minutes"
            
            if has_position:
                coin = position_info.get("coin", "BTC")
                direction = position_info.get("direction", "UNKNOWN")
                position_size = position_info.get("position_size", 0)
                position_value = position_info.get("position_value", 0)
                entry_price = position_info.get("entry_price", 0)
                current_price = position_info.get("current_price", 0)
                pnl_percent = position_info.get("pnl_percent", 0)
                
                position_str = (
                    f"Current position: {direction} {coin}\n"
                    f"Size: {position_size:.4f} ({position_value:.2f} USD)\n"
                    f"Entry: ${entry_price:.2f}, Current: ${current_price:.2f}\n"
                    f"Unrealized P&L: {pnl_percent:.2f}%"
                )
            else:
                position_str = "No active positions"
            
            activity_str = (
                f"Last {time_str} activity:\n"
                f"- New orders placed: {counts.get('open_order_placed', 0)}\n"
                f"- Position reversals: {counts.get('reverse', 0)}\n"
                f"- Positions held: {counts.get('hold', 0)}\n"
                f"- No actions taken: {counts.get('no_action', 0)}\n"
                f"- Failed operations: {counts.get('failed', 0) + counts.get('error', 0)}"
            )
            
            user_prompt = prompts.HOURLY_RECAP_PROMPT.format(
                position_str=position_str,
                activity_str=activity_str
            )
            
            tweet_content = await self.agent.answer(user_prompt)
            logger.info(f"Generated hourly recap tweet content: {tweet_content}")
            
            return tweet_content.strip()
            
        except Exception as e:
            error_msg = f"Error generating recap tweet content: {str(e)}"
            logger.error(error_msg)
            raise ContentGenerationError(error_msg)

    def _tweet(
        self,
        message: Annotated[str, Doc("The message to tweet (max 280 characters)")]
    ) -> str:
        """Posts a tweet to Twitter using the authenticated account.

        Args:
            message (str): The message to tweet (max 280 characters)

        Returns:
            str: A message indicating success or failure of the tweet
            
        Raises:
            TwitterAPIError: If tweet posting fails
            RateLimitError: If Twitter API rate limit is exceeded
        """
        logger.info(f"Attempting to tweet: {message}")
        
        try:
            response = self.twitter.create_tweet(text=message)
            tweet_id = response.data['id']
            logger.info(f"Tweet posted successfully with ID: {tweet_id}")
            return f"Successfully posted tweet with ID: {tweet_id}"
        except tweepy.TooManyRequests as e:
            error_msg = "Tweet rate limit exceeded"
            logger.warning(error_msg)
            raise RateLimitError(error_msg)
        except Exception as e:
            error_msg = f"Failed to post tweet: {str(e)}"
            logger.error(error_msg)
            raise TwitterAPIError(error_msg)
    
    def _reply_to_tweet(
        self,
        tweet_id: str,
        message: str
    ) -> Tuple[bool, Optional[str]]:
        """Reply to a specific tweet.
        
        Args:
            tweet_id (str): ID of the tweet to reply to
            message (str): Reply message content
            
        Returns:
            Tuple[bool, Optional[str]]: Success status and tweet ID if successful
            
        Raises:
            TwitterAPIError: If reply posting fails
            RateLimitError: If Twitter API rate limit is exceeded
        """
        logger.info(f"Attempting to reply to tweet {tweet_id} with: {message}")
        
        try:
            response = self.twitter.create_tweet(
                text=message,
                in_reply_to_tweet_id=tweet_id
            )
            reply_id = response.data['id']
            logger.info(f"Reply posted successfully with ID: {reply_id}")
            return True, reply_id
        except tweepy.TooManyRequests as e:
            error_msg = "Reply rate limit exceeded"
            logger.warning(error_msg)
            raise RateLimitError(error_msg)
        except Exception as e:
            error_msg = f"Failed to post reply: {str(e)}"
            logger.error(error_msg)
            raise TwitterAPIError(error_msg)
    
    def _quote_retweet(
        self,
        tweet_id: str,
        message: str
    ) -> Tuple[bool, Optional[str]]:
        """Quote retweet a specific tweet.
        
        Args:
            tweet_id (str): ID of the tweet to quote
            message (str): Quote message content
            
        Returns:
            Tuple[bool, Optional[str]]: Success status and tweet ID if successful
            
        Raises:
            TwitterAPIError: If quote retweet posting fails
            RateLimitError: If Twitter API rate limit is exceeded
        """
        logger.info(f"Attempting to quote retweet {tweet_id} with: {message}")
        
        try:
            tweet_url = f"https://twitter.com/twitter/status/{tweet_id}"
            
            response = self.twitter.create_tweet(
                text=f".{message}\n\n{tweet_url}"
            )
            quote_id = response.data['id']
            logger.info(f"Quote retweet posted successfully with ID: {quote_id}")
            return True, quote_id
        except tweepy.TooManyRequests as e:
            error_msg = "Quote retweet rate limit exceeded"
            logger.warning(error_msg)
            raise RateLimitError(error_msg)
        except Exception as e:
            error_msg = f"Failed to post quote retweet: {str(e)}"
            logger.error(error_msg)
            raise TwitterAPIError(error_msg)
    
    async def check_and_reply_to_mentions(self, hours: int = 1) -> int:
        """Check for new mentions and reply to them with context.
        
        This method:
        1. Fetches recent mentions from the specified time window
        2. For each mention, generates a contextual reply
        3. Posts the reply or quote retweet based on whitelist status
        4. Updates conversation history
        
        Args:
            hours (int, optional): Number of hours to look back for mentions. Defaults to 1.
        
        Returns:
            int: Number of mentions processed
            
        Raises:
            TwitterAPIError: If Twitter API operations fail
            ContentGenerationError: If content generation fails
            ConversationError: If conversation history operations fail
        """
        logger.info(f"Checking for new mentions (looking back {hours} hours)")
        
        current_time = datetime.now()
        self.last_mention_check = current_time
        
        try:
            start_time = current_time - timedelta(hours=hours)
            start_time_str = start_time.strftime("%Y-%m-%dT%H:%M:%SZ")
            
            logger.info(f"Fetching mentions since {start_time_str} with since_id: {self.last_mention_id}")
            
            try:
                mentions = self.twitter.get_users_mentions(
                    id=self.twitter_me_id,
                    start_time=start_time_str,
                    tweet_fields=["author_id", "conversation_id", "created_at", "in_reply_to_user_id", "referenced_tweets"],
                    expansions=["author_id", "referenced_tweets.id"],
                    user_fields=["username", "name"],
                    max_results=100
                )
            except tweepy.TooManyRequests as e:
                error_msg = "Twitter API rate limit exceeded"
                logger.warning(error_msg)
                raise RateLimitError(error_msg)
            except tweepy.TwitterServerError as e:
                error_msg = f"Twitter server error: {str(e)}"
                logger.warning(error_msg)
                raise TwitterAPIError(error_msg)
            
            if not mentions or mentions.data is None:
                logger.info("No new mentions found")
                return 0
                
            mentions_list = list(mentions.data)
            mentions_list.reverse()
            
            if not mentions_list:
                logger.info("No mentions to process after filtering")
                return 0
                
            self.last_mention_id = mentions_list[-1].id
            
            processed_count = 0
            quote_retweet_count = 0
            
            for mention in mentions_list:
                if mention.author_id == self.twitter_me_id:
                    continue
                
                conversation_id = mention.conversation_id
                conversation_context = self._get_conversation_context(conversation_id)
                
                original_tweet_text = ""
                if mention.referenced_tweets:
                    for ref in mention.referenced_tweets:
                        if ref.type == "replied_to":
                            try:
                                original_tweet = self.twitter.get_tweet(
                                    id=ref.id,
                                    tweet_fields=["text"]
                                ).data
                                original_tweet_text = original_tweet.text
                            except Exception as e:
                                error_msg = f"Error fetching original tweet {ref.id}: {str(e)}"
                                logger.error(error_msg)
                                raise TwitterAPIError(error_msg)
                
                try:
                    author = self.twitter.get_user(id=mention.author_id).data
                    author_username = author.username if author else "user"
                except Exception as e:
                    error_msg = f"Error fetching author info for {mention.author_id}: {str(e)}"
                    logger.error(error_msg)
                    raise TwitterAPIError(error_msg)
                
                reply = await self._generate_mention_reply(
                    mention_text=mention.text,
                    original_tweet=original_tweet_text,
                    conversation_context=conversation_context,
                    author_username=author_username
                )
                
                should_quote_retweet = author_username.lower() in [name.lower() for name in self.whitelist_accounts]
                
                success = False
                reply_id = None
                
                if should_quote_retweet:
                    logger.info(f"Author @{author_username} is in whitelist - using quote retweet")
                    success, reply_id = self._quote_retweet(mention.id, reply)
                    if success:
                        quote_retweet_count += 1
                else:
                    success, reply_id = self._reply_to_tweet(mention.id, reply)
                
                if success:
                    self._update_conversation_history(
                        conversation_id=conversation_id,
                        tweet_id=mention.id,
                        author=author_username,
                        content=mention.text,
                        is_mention=True
                    )
                    
                    self._update_conversation_history(
                        conversation_id=conversation_id,
                        tweet_id=reply_id,
                        author="WT3",
                        content=reply,
                        is_mention=False
                    )
                    
                    processed_count += 1
                
                time.sleep(2)
            
            self._save_conversation_history()
            
            logger.info(f"Processed {processed_count} mentions (including {quote_retweet_count} quote retweets)")
            return processed_count
            
        except (TwitterAPIError, ContentGenerationError, ConversationError) as e:
            raise
        except Exception as e:
            error_msg = f"Error checking mentions: {str(e)}"
            logger.error(error_msg)
            raise SocialClientError(error_msg)
    
    async def _generate_mention_reply(
        self,
        mention_text: str,
        original_tweet: str,
        conversation_context: str,
        author_username: str
    ) -> str:
        """Generate a reply to a mention with context.
        
        Args:
            mention_text (str): The text of the mention
            original_tweet (str): The text of the original tweet being replied to
            conversation_context (str): Previous conversation context
            author_username (str): Username of the author of the mention
            
        Returns:
            str: Generated reply content
            
        Raises:
            ContentGenerationError: If content generation fails
        """
        try:
            user_prompt = prompts.MENTION_REPLY_PROMPT.format(
                original_tweet=original_tweet,
                mention_text=mention_text,
                conversation_context=conversation_context
            )
            
            reply_content = await self.agent.answer(user_prompt)
            
            if not reply_content.startswith(f"@{author_username}"):
                reply_content = f"@{author_username} {reply_content}"
            
            logger.info(f"Generated mention reply: {reply_content}")
            
            return reply_content.strip()
            
        except Exception as e:
            error_msg = f"Error generating mention reply: {str(e)}"
            logger.error(error_msg)
            raise ContentGenerationError(error_msg)
    
    def _get_conversation_context(self, conversation_id: str) -> str:
        """Get the context of a conversation from history.
        
        Args:
            conversation_id (str): ID of the conversation
            
        Returns:
            str: Formatted conversation context
        """
        if conversation_id not in self.conversation_history:
            return "No previous conversation"
        
        conversation = self.conversation_history[conversation_id]
        
        context_parts = []
        for tweet in conversation:
            author = tweet.get("author", "Unknown")
            content = tweet.get("content", "")
            context_parts.append(f"{author}: {content}")
        
        # Limit to the last 5 tweets to keep context manageable
        if len(context_parts) > 5:
            context_parts = context_parts[-5:]
            
        return "\n".join(context_parts)
    
    def _update_conversation_history(
        self,
        conversation_id: str,
        tweet_id: str,
        author: str,
        content: str,
        is_mention: bool
    ):
        """Update the conversation history with a new tweet.
        
        Args:
            conversation_id (str): ID of the conversation
            tweet_id (str): ID of the tweet
            author (str): Author of the tweet
            content (str): Content of the tweet
            is_mention (bool): Whether the tweet is a mention
        """
        if conversation_id not in self.conversation_history:
            self.conversation_history[conversation_id] = []
        
        self.conversation_history[conversation_id].append({
            "id": tweet_id,
            "author": author,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "is_mention": is_mention
        })
        
        if len(self.conversation_history[conversation_id]) > 20:
            self.conversation_history[conversation_id] = self.conversation_history[conversation_id][-20:]
    
    async def _generate_quote_retweet(
        self,
        tweet_text: str,
        author_username: str
    ) -> str:
        """Generate a quote retweet comment.
        
        Args:
            tweet_text (str): The text of the tweet to quote
            author_username (str): Username of the author of the tweet
            
        Returns:
            str: Generated quote retweet content
            
        Raises:
            ContentGenerationError: If content generation fails
        """
        try:
            user_prompt = prompts.QUOTE_RETWEET_PROMPT.format(
                author_username=author_username,
                tweet_text=tweet_text
            )
            
            quote_content = await self.agent.answer(user_prompt)
            
            logger.info(f"Generated quote retweet: {quote_content}")
            
            return quote_content.strip()
            
        except Exception as e:
            error_msg = f"Error generating quote retweet: {str(e)}"
            logger.error(error_msg)
            raise ContentGenerationError(error_msg)
    
    async def run_periodic_tasks(self, hours: float = 0.1667) -> Dict[str, Any]:
        """Run periodic social media tasks.
        
        This method:
        1. Checks for new mentions and replies to them
        2. If the mention author is in the whitelist, it will quote retweet instead of replying
        3. Runs every 10 minutes independently of the trading cycle
        4. Includes timing protection to ensure consistent 10-minute intervals
        
        Args:
            hours (float, optional): Number of hours to look back for mentions. Defaults to 0.1667 (10 minutes).
        
        Returns:
            Dict[str, Any]: Summary of tasks performed
            
        Raises:
            SocialClientError: If task execution fails
        """
        start_time = datetime.now()
        logger.info(f"🔄 Starting periodic social media tasks (looking back {hours} hours)")
        
        try:
            current_time = datetime.now()
            time_since_last_check = current_time - self.last_mention_check
            
            if time_since_last_check.total_seconds() < 500:
                logger.info(f"Social tasks called too soon. Last run was {time_since_last_check.total_seconds()/60:.1f} minutes ago. Skipping.")
                return {
                    "mentions_processed": 0,
                    "skipped": True,
                    "reason": "Too soon since last run"
                }
            
            mentions_processed = await self.check_and_reply_to_mentions(hours=hours)
            
            execution_time = (datetime.now() - start_time).total_seconds()
            logger.info(f"✅ Social media tasks completed in {execution_time:.1f}s")
            
            return {
                "mentions_processed": mentions_processed,
                "quote_retweets": "Included in mentions_processed count",
                "execution_time_seconds": execution_time,
                "completed_at": current_time.isoformat()
            }
            
        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()
            error_msg = f"Error running periodic social media tasks after {execution_time:.1f}s: {str(e)}"
            logger.error(error_msg)
            raise SocialClientError(error_msg)
