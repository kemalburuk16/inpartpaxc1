#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Like Manager - Handles automatic liking of posts based on hashtags
"""

import json
import time
import random
import logging
from typing import Dict, Any, List, Set, Tuple
from datetime import datetime, timedelta
from src.instagram_client import InstagramClient
from src.utils import save_action_log, load_action_log

logger = logging.getLogger(__name__)


class LikeManager:
    """
    Manages automatic liking of posts based on hashtag targeting
    with safety measures and intelligent filtering
    """
    
    def __init__(self, client: InstagramClient, config: Dict[str, Any]):
        self.client = client
        self.config = config
        self.hashtag_config = config.get('instagram', {}).get('hashtags', {})
        self.safety_config = config.get('instagram', {}).get('safety', {})
        
        # Track liked posts to avoid duplicates
        self.liked_posts: Set[str] = set()
        self.failed_posts: Set[str] = set()
        
        # Statistics
        self.stats = {
            'total_likes': 0,
            'successful_likes': 0,
            'failed_likes': 0,
            'skipped_posts': 0,
            'hashtags_processed': 0,
            'session_start': datetime.now().isoformat()
        }
        
        # Load previous session data
        self._load_session_data()
        
        logger.info("LikeManager initialized")
    
    def _load_session_data(self):
        """Load previously liked posts and statistics"""
        try:
            log_data = load_action_log('likes')
            if log_data:
                # Load recent liked posts (last 24 hours)
                cutoff_time = datetime.now() - timedelta(hours=24)
                for entry in log_data:
                    if datetime.fromisoformat(entry.get('timestamp', '')) > cutoff_time:
                        self.liked_posts.add(entry.get('media_id', ''))
                
                logger.info(f"Loaded {len(self.liked_posts)} recent liked posts")
        except Exception as e:
            logger.warning(f"Could not load session data: {e}")
    
    def _should_like_post(self, post: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Determine if a post should be liked based on various criteria
        Returns (should_like, reason)
        """
        media_id = post.get('id')
        
        # Already liked this post
        if media_id in self.liked_posts:
            return False, "already_liked"
        
        # Already failed to like this post
        if media_id in self.failed_posts:
            return False, "previously_failed"
        
        # Already liked by this account
        if post.get('has_liked', False):
            return False, "already_liked_by_account"
        
        # Check like probability
        like_probability = self.hashtag_config.get('like_probability', 0.8)
        if random.random() > like_probability:
            return False, "probability_skip"
        
        # Check minimum engagement (avoid spam/low quality posts)
        min_likes = self.hashtag_config.get('min_likes_threshold', 1)
        if post.get('like_count', 0) < min_likes:
            return False, "low_engagement"
        
        # Check maximum engagement (avoid very popular posts that might be spam targets)
        max_likes = self.hashtag_config.get('max_likes_threshold', 10000)
        if post.get('like_count', 0) > max_likes:
            return False, "too_popular"
        
        # Check post age (don't like very old posts)
        taken_at = post.get('taken_at')
        if taken_at:
            post_age = time.time() - taken_at
            max_age_hours = self.hashtag_config.get('max_post_age_hours', 72)
            if post_age > (max_age_hours * 3600):
                return False, "too_old"
        
        # Check caption for spam indicators
        caption = post.get('caption', '').lower()
        spam_keywords = self.hashtag_config.get('spam_keywords', [
            'follow for follow', 'f4f', 'l4l', 'like for like', 
            'dm me', 'check my bio', 'link in bio for'
        ])
        
        for keyword in spam_keywords:
            if keyword in caption:
                return False, f"spam_keyword: {keyword}"
        
        return True, "approved"
    
    def _process_hashtag(self, hashtag: str) -> Dict[str, Any]:
        """
        Process a single hashtag and like relevant posts
        Returns statistics for this hashtag
        """
        logger.info(f"Processing hashtag: #{hashtag}")
        
        hashtag_stats = {
            'hashtag': hashtag,
            'posts_found': 0,
            'posts_liked': 0,
            'posts_skipped': 0,
            'errors': 0,
            'start_time': datetime.now().isoformat()
        }
        
        try:
            # Get posts for this hashtag
            posts_per_tag = self.hashtag_config.get('posts_per_tag', 10)
            posts = self.client.search_hashtag(hashtag, count=posts_per_tag * 2)  # Get extra in case of filtering
            
            if not posts:
                logger.warning(f"No posts found for hashtag #{hashtag}")
                return hashtag_stats
            
            hashtag_stats['posts_found'] = len(posts)
            logger.info(f"Found {len(posts)} posts for #{hashtag}")
            
            liked_count = 0
            target_likes = min(posts_per_tag, len(posts))
            
            # Shuffle posts to avoid predictable patterns
            random.shuffle(posts)
            
            for post in posts:
                if liked_count >= target_likes:
                    break
                
                should_like, reason = self._should_like_post(post)
                
                if should_like:
                    success = self._like_post_with_logging(post, hashtag)
                    if success:
                        liked_count += 1
                        hashtag_stats['posts_liked'] += 1
                        
                        # Add delay between likes
                        delay = random.uniform(15, 45)  # 15-45 seconds between likes
                        logger.info(f"Waiting {delay:.1f} seconds before next like")
                        time.sleep(delay)
                    else:
                        hashtag_stats['errors'] += 1
                else:
                    hashtag_stats['posts_skipped'] += 1
                    logger.debug(f"Skipped post {post.get('id')}: {reason}")
            
            hashtag_stats['end_time'] = datetime.now().isoformat()
            logger.info(f"Hashtag #{hashtag} processed: {liked_count} likes, {hashtag_stats['posts_skipped']} skipped")
            
        except Exception as e:
            logger.error(f"Error processing hashtag #{hashtag}: {e}")
            hashtag_stats['errors'] += 1
        
        return hashtag_stats
    
    def _like_post_with_logging(self, post: Dict[str, Any], hashtag: str) -> bool:
        """
        Like a post and log the action
        Returns True if successful
        """
        media_id = post.get('id')
        username = post.get('username', 'unknown')
        
        try:
            success = self.client.like_post(media_id)
            
            # Log the action
            log_entry = {
                'timestamp': datetime.now().isoformat(),
                'action': 'like',
                'media_id': media_id,
                'username': username,
                'hashtag': hashtag,
                'success': success,
                'like_count': post.get('like_count', 0),
                'caption_preview': post.get('caption', '')[:100]
            }
            
            save_action_log('likes', log_entry)
            
            if success:
                self.liked_posts.add(media_id)
                self.stats['successful_likes'] += 1
                logger.info(f"✅ Liked post by @{username} (#{hashtag}) - {post.get('like_count', 0)} likes")
            else:
                self.failed_posts.add(media_id)
                self.stats['failed_likes'] += 1
                logger.warning(f"❌ Failed to like post by @{username} (#{hashtag})")
            
            self.stats['total_likes'] += 1
            return success
            
        except Exception as e:
            logger.error(f"Error liking post {media_id}: {e}")
            self.failed_posts.add(media_id)
            self.stats['failed_likes'] += 1
            return False
    
    def run_hashtag_liking_session(self) -> Dict[str, Any]:
        """
        Run a complete hashtag liking session
        Returns session statistics
        """
        logger.info("Starting hashtag liking session")
        
        session_stats = {
            'start_time': datetime.now().isoformat(),
            'hashtags_processed': [],
            'total_likes': 0,
            'total_errors': 0,
            'rate_limit_status': {}
        }
        
        try:
            target_hashtags = self.hashtag_config.get('target_tags', [])
            
            if not target_hashtags:
                logger.warning("No target hashtags configured")
                return session_stats
            
            # Shuffle hashtags to avoid predictable patterns
            random.shuffle(target_hashtags)
            
            for hashtag in target_hashtags:
                # Check rate limits before processing each hashtag
                rate_status = self.client.get_rate_limit_status()
                if rate_status['hourly_likes'] >= rate_status['likes_limit']:
                    logger.warning("Hourly like limit reached, stopping session")
                    break
                
                hashtag_result = self._process_hashtag(hashtag)
                session_stats['hashtags_processed'].append(hashtag_result)
                session_stats['total_likes'] += hashtag_result['posts_liked']
                session_stats['total_errors'] += hashtag_result['errors']
                
                self.stats['hashtags_processed'] += 1
                
                # Add delay between hashtags
                if hashtag != target_hashtags[-1]:  # Don't delay after the last hashtag
                    delay = random.uniform(60, 180)  # 1-3 minutes between hashtags
                    logger.info(f"Waiting {delay:.1f} seconds before next hashtag")
                    time.sleep(delay)
            
            session_stats['rate_limit_status'] = self.client.get_rate_limit_status()
            session_stats['end_time'] = datetime.now().isoformat()
            
            logger.info(f"Hashtag liking session completed: {session_stats['total_likes']} total likes")
            
        except Exception as e:
            logger.error(f"Error in hashtag liking session: {e}")
            session_stats['error'] = str(e)
        
        return session_stats
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get current statistics"""
        return {
            **self.stats,
            'liked_posts_count': len(self.liked_posts),
            'failed_posts_count': len(self.failed_posts),
            'rate_limit_status': self.client.get_rate_limit_status()
        }
    
    def reset_session_data(self):
        """Reset session data (for testing or new sessions)"""
        self.liked_posts.clear()
        self.failed_posts.clear()
        self.stats = {
            'total_likes': 0,
            'successful_likes': 0,
            'failed_likes': 0,
            'skipped_posts': 0,
            'hashtags_processed': 0,
            'session_start': datetime.now().isoformat()
        }
        logger.info("Session data reset")