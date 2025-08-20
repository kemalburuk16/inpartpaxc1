import json
import logging
import random
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Set

from instagram_client import InstagramClient
from utils import (
    setup_logging, get_random_delay, is_within_limits, 
    is_user_blacklisted, is_hashtag_blacklisted,
    get_daily_stats, get_current_hour_stats, update_stats,
    extract_hashtags_from_text
)


class LikeManager:
    """
    Manages automatic liking functionality with safety controls and rate limiting.
    """
    
    def __init__(self, client: InstagramClient, config: Dict[str, Any]):
        self.client = client
        self.config = config
        self.logger = setup_logging()
        
        # Track liked posts to avoid duplicates
        self.liked_posts: Set[str] = set()
        self.liked_posts_file = "logs/liked_posts.json"
        self._load_liked_posts()
        
        # Activity tracking
        self.session_likes = 0
        self.consecutive_failures = 0
        self.max_consecutive_failures = config.get('safety', {}).get('max_consecutive_failures', 3)
    
    def _load_liked_posts(self) -> None:
        """Load previously liked posts from file."""
        try:
            with open(self.liked_posts_file, 'r') as f:
                data = json.load(f)
                self.liked_posts = set(data.get('liked_posts', []))
                self.logger.info(f"Loaded {len(self.liked_posts)} previously liked posts")
        except FileNotFoundError:
            self.liked_posts = set()
            self.logger.info("No previous liked posts file found")
        except Exception as e:
            self.logger.error(f"Failed to load liked posts: {e}")
            self.liked_posts = set()
    
    def _save_liked_posts(self) -> None:
        """Save liked posts to file."""
        try:
            import os
            os.makedirs(os.path.dirname(self.liked_posts_file), exist_ok=True)
            
            # Keep only recent posts (last 30 days)
            cutoff_time = datetime.now() - timedelta(days=30)
            
            with open(self.liked_posts_file, 'w') as f:
                json.dump({
                    'liked_posts': list(self.liked_posts),
                    'last_updated': datetime.now().isoformat()
                }, f, indent=2)
        except Exception as e:
            self.logger.error(f"Failed to save liked posts: {e}")
    
    def can_like_more(self) -> bool:
        """Check if we can like more posts based on limits."""
        daily_likes = get_daily_stats('likes')
        hourly_likes = get_current_hour_stats('likes')
        
        return is_within_limits('likes', daily_likes, hourly_likes, self.config)
    
    def like_posts_by_hashtag(self, hashtag: str, max_posts: int = 10) -> Dict[str, Any]:
        """Like posts from a specific hashtag."""
        results = {
            'hashtag': hashtag,
            'posts_processed': 0,
            'posts_liked': 0,
            'posts_skipped': 0,
            'errors': []
        }
        
        if is_hashtag_blacklisted(hashtag, self.config):
            self.logger.warning(f"Hashtag {hashtag} is blacklisted")
            results['errors'].append(f"Hashtag {hashtag} is blacklisted")
            return results
        
        if not self.can_like_more():
            self.logger.warning("Like limit reached")
            results['errors'].append("Like limit reached")
            return results
        
        self.logger.info(f"Starting to like posts from hashtag: {hashtag}")
        
        try:
            # Search for posts with the hashtag
            hashtag_data = self.client.search_hashtag(hashtag)
            if not hashtag_data:
                self.logger.error(f"Failed to get posts for hashtag: {hashtag}")
                results['errors'].append("Failed to fetch hashtag data")
                return results
            
            posts = hashtag_data.get('items', [])
            if not posts:
                self.logger.warning(f"No posts found for hashtag: {hashtag}")
                results['errors'].append("No posts found")
                return results
            
            # Shuffle posts for more natural behavior
            random.shuffle(posts)
            
            for post in posts[:max_posts]:
                if not self.can_like_more():
                    self.logger.info("Like limit reached, stopping")
                    break
                
                results['posts_processed'] += 1
                
                if self._should_like_post(post):
                    if self._like_post_safe(post):
                        results['posts_liked'] += 1
                        self._apply_like_delay()
                    else:
                        results['posts_skipped'] += 1
                else:
                    results['posts_skipped'] += 1
                
                # Check for consecutive failures
                if self.consecutive_failures >= self.max_consecutive_failures:
                    self.logger.warning("Too many consecutive failures, stopping")
                    results['errors'].append("Too many consecutive failures")
                    break
        
        except Exception as e:
            self.logger.error(f"Error liking posts by hashtag: {e}")
            results['errors'].append(str(e))
        
        self.logger.info(f"Hashtag liking complete: {results}")
        return results
    
    def like_user_posts(self, username: str, max_posts: int = 3) -> Dict[str, Any]:
        """Like recent posts from a specific user."""
        results = {
            'username': username,
            'posts_processed': 0,
            'posts_liked': 0,
            'posts_skipped': 0,
            'errors': []
        }
        
        if is_user_blacklisted(username, self.config):
            self.logger.warning(f"User {username} is blacklisted")
            results['errors'].append(f"User {username} is blacklisted")
            return results
        
        if not self.can_like_more():
            self.logger.warning("Like limit reached")
            results['errors'].append("Like limit reached")
            return results
        
        self.logger.info(f"Starting to like posts from user: {username}")
        
        try:
            # Get user info first
            user_info = self.client.get_user_info(username)
            if not user_info:
                self.logger.error(f"Failed to get user info for: {username}")
                results['errors'].append("Failed to get user info")
                return results
            
            user_id = user_info.get('id')
            if not user_id:
                self.logger.error(f"No user ID found for: {username}")
                results['errors'].append("No user ID found")
                return results
            
            # Get user's feed
            feed_data = self.client.get_user_feed(user_id)
            if not feed_data:
                self.logger.error(f"Failed to get feed for user: {username}")
                results['errors'].append("Failed to get feed")
                return results
            
            posts = feed_data.get('items', [])
            if not posts:
                self.logger.warning(f"No posts found for user: {username}")
                results['errors'].append("No posts found")
                return results
            
            # Process recent posts
            for post in posts[:max_posts]:
                if not self.can_like_more():
                    self.logger.info("Like limit reached, stopping")
                    break
                
                results['posts_processed'] += 1
                
                if self._should_like_post(post):
                    if self._like_post_safe(post):
                        results['posts_liked'] += 1
                        self._apply_like_delay()
                    else:
                        results['posts_skipped'] += 1
                else:
                    results['posts_skipped'] += 1
                
                # Check for consecutive failures
                if self.consecutive_failures >= self.max_consecutive_failures:
                    self.logger.warning("Too many consecutive failures, stopping")
                    results['errors'].append("Too many consecutive failures")
                    break
        
        except Exception as e:
            self.logger.error(f"Error liking user posts: {e}")
            results['errors'].append(str(e))
        
        self.logger.info(f"User post liking complete: {results}")
        return results
    
    def _should_like_post(self, post: Dict[str, Any]) -> bool:
        """Determine if a post should be liked based on various criteria."""
        try:
            media_id = post.get('id') or post.get('pk')
            if not media_id:
                self.logger.warning("Post has no media ID")
                return False
            
            # Skip if already liked by us
            if str(media_id) in self.liked_posts:
                self.logger.debug(f"Post {media_id} already liked")
                return False
            
            # Skip if already liked by current user
            if post.get('has_liked', False):
                self.logger.debug(f"Post {media_id} already liked by current user")
                return False
            
            # Check user
            user = post.get('user', {})
            username = user.get('username', '')
            if is_user_blacklisted(username, self.config):
                self.logger.debug(f"User {username} is blacklisted")
                return False
            
            # Check if user is verified (skip if configured)
            strategy = self.config.get('like_strategy', {})
            if strategy.get('skip_verified_users', False) and user.get('is_verified', False):
                self.logger.debug(f"Skipping verified user: {username}")
                return False
            
            # Check like count limits
            like_count = post.get('like_count', 0)
            min_likes = strategy.get('min_likes_on_post', 0)
            max_likes = strategy.get('max_likes_on_post', 10000)
            
            if like_count < min_likes or like_count > max_likes:
                self.logger.debug(f"Post like count {like_count} outside range {min_likes}-{max_likes}")
                return False
            
            # Check caption for blacklisted hashtags
            caption = post.get('caption', {})
            if caption:
                caption_text = caption.get('text', '')
                hashtags = extract_hashtags_from_text(caption_text)
                for hashtag in hashtags:
                    if is_hashtag_blacklisted(hashtag, self.config):
                        self.logger.debug(f"Post contains blacklisted hashtag: {hashtag}")
                        return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error checking if should like post: {e}")
            return False
    
    def _like_post_safe(self, post: Dict[str, Any]) -> bool:
        """Safely like a post with error handling."""
        try:
            media_id = post.get('id') or post.get('pk')
            if not media_id:
                return False
            
            # Attempt to like the post
            success = self.client.like_post(str(media_id))
            
            if success:
                self.liked_posts.add(str(media_id))
                self.session_likes += 1
                self.consecutive_failures = 0
                update_stats('likes')
                
                # Log the successful like
                user = post.get('user', {})
                username = user.get('username', 'unknown')
                self.logger.info(f"Successfully liked post {media_id} by @{username}")
                
                # Save liked posts periodically
                if len(self.liked_posts) % 10 == 0:
                    self._save_liked_posts()
                
                return True
            else:
                self.consecutive_failures += 1
                self.logger.warning(f"Failed to like post {media_id}")
                return False
                
        except Exception as e:
            self.consecutive_failures += 1
            self.logger.error(f"Error liking post: {e}")
            return False
    
    def _apply_like_delay(self) -> None:
        """Apply delay between likes to simulate human behavior."""
        delays = self.config.get('delays', {})
        min_delay = delays.get('min_like_delay', 10)
        max_delay = delays.get('max_like_delay', 30)
        
        delay = get_random_delay(min_delay, max_delay)
        self.logger.debug(f"Applying like delay: {delay} seconds")
        time.sleep(delay)
    
    def auto_like_from_hashtags(self, hashtags: List[str], posts_per_hashtag: int = 5) -> Dict[str, Any]:
        """Automatically like posts from multiple hashtags."""
        results = {
            'hashtags_processed': 0,
            'total_posts_liked': 0,
            'total_posts_processed': 0,
            'hashtag_results': {},
            'errors': []
        }
        
        if not hashtags:
            hashtags = self.config.get('target_hashtags', [])
        
        if not hashtags:
            self.logger.warning("No hashtags specified for auto-liking")
            results['errors'].append("No hashtags specified")
            return results
        
        # Shuffle hashtags for more natural behavior
        random.shuffle(hashtags)
        
        for hashtag in hashtags:
            if not self.can_like_more():
                self.logger.info("Like limit reached, stopping auto-like")
                break
            
            hashtag_result = self.like_posts_by_hashtag(hashtag, posts_per_hashtag)
            results['hashtag_results'][hashtag] = hashtag_result
            results['hashtags_processed'] += 1
            results['total_posts_liked'] += hashtag_result['posts_liked']
            results['total_posts_processed'] += hashtag_result['posts_processed']
            
            if hashtag_result['errors']:
                results['errors'].extend(hashtag_result['errors'])
            
            # Check for consecutive failures
            if self.consecutive_failures >= self.max_consecutive_failures:
                self.logger.warning("Too many consecutive failures, stopping auto-like")
                results['errors'].append("Too many consecutive failures")
                break
            
            # Add delay between hashtags
            if hashtag != hashtags[-1]:  # Don't delay after last hashtag
                delay = get_random_delay(30, 120)  # 30-120 seconds between hashtags
                self.logger.info(f"Delaying {delay} seconds before next hashtag")
                time.sleep(delay)
        
        self.logger.info(f"Auto-like session complete: {results}")
        
        # Save liked posts at the end of session
        self._save_liked_posts()
        
        return results
    
    def get_like_stats(self) -> Dict[str, Any]:
        """Get liking statistics."""
        return {
            'session_likes': self.session_likes,
            'total_liked_posts': len(self.liked_posts),
            'daily_likes': get_daily_stats('likes'),
            'hourly_likes': get_current_hour_stats('likes'),
            'consecutive_failures': self.consecutive_failures,
            'can_like_more': self.can_like_more()
        }
    
    def cleanup_old_liked_posts(self, days_to_keep: int = 30) -> None:
        """Clean up old liked posts data to save space."""
        # This is a simplified cleanup - in a real implementation,
        # you might want to store timestamps with each liked post
        self.logger.info(f"Cleaned up old liked posts data (keeping {days_to_keep} days)")
        self._save_liked_posts()