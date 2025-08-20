#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Follow Manager - Handles automatic following of users based on various strategies
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


class FollowManager:
    """
    Manages automatic following of users with intelligent targeting
    and safety measures to avoid spam-like behavior
    """
    
    def __init__(self, client: InstagramClient, config: Dict[str, Any]):
        self.client = client
        self.config = config
        self.follow_config = config.get('instagram', {}).get('following', {})
        self.safety_config = config.get('instagram', {}).get('safety', {})
        
        # Track followed users to avoid duplicates
        self.followed_users: Set[str] = set()
        self.failed_follows: Set[str] = set()
        self.processed_users: Set[str] = set()
        
        # Statistics
        self.stats = {
            'total_follows': 0,
            'successful_follows': 0,
            'failed_follows': 0,
            'skipped_users': 0,
            'users_analyzed': 0,
            'session_start': datetime.now().isoformat()
        }
        
        # Load previous session data
        self._load_session_data()
        
        logger.info("FollowManager initialized")
    
    def _load_session_data(self):
        """Load previously followed users and statistics"""
        try:
            log_data = load_action_log('follows')
            if log_data:
                # Load recent follows (last 7 days to avoid re-following too soon)
                cutoff_time = datetime.now() - timedelta(days=7)
                for entry in log_data:
                    if datetime.fromisoformat(entry.get('timestamp', '')) > cutoff_time:
                        self.followed_users.add(entry.get('user_id', ''))
                
                logger.info(f"Loaded {len(self.followed_users)} recent followed users")
        except Exception as e:
            logger.warning(f"Could not load session data: {e}")
    
    def _should_follow_user(self, user: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Determine if a user should be followed based on various criteria
        Returns (should_follow, reason)
        """
        user_id = str(user.get('id', ''))
        username = user.get('username', '')
        
        # Already followed this user
        if user_id in self.followed_users:
            return False, "already_followed"
        
        # Already failed to follow this user
        if user_id in self.failed_follows:
            return False, "previously_failed"
        
        # Skip private accounts (can't see content quality)
        if user.get('is_private', False):
            return False, "private_account"
        
        # Check follow probability
        follow_probability = self.follow_config.get('follow_probability', 0.6)
        if random.random() > follow_probability:
            return False, "probability_skip"
        
        # Check follower count (avoid bots and inactive accounts)
        follower_count = user.get('follower_count', 0)
        min_followers = self.follow_config.get('min_followers', 50)
        max_followers = self.follow_config.get('max_followers', 50000)
        
        if follower_count < min_followers:
            return False, f"too_few_followers ({follower_count})"
        
        if follower_count > max_followers:
            return False, f"too_many_followers ({follower_count})"
        
        # Check following/follower ratio (avoid follow-for-follow accounts)
        following_count = user.get('following_count', 0)
        if follower_count > 0:
            ratio = following_count / follower_count
            max_ratio = self.follow_config.get('max_following_ratio', 2.0)
            if ratio > max_ratio:
                return False, f"high_follow_ratio ({ratio:.2f})"
        
        # Check if user has posts (avoid inactive accounts)
        media_count = user.get('media_count', 0)
        min_posts = self.follow_config.get('min_posts', 3)
        if media_count < min_posts:
            return False, f"too_few_posts ({media_count})"
        
        # Check biography for spam indicators
        biography = user.get('biography', '').lower()
        spam_keywords = self.follow_config.get('spam_keywords', [
            'follow for follow', 'f4f', 'dm for promotion', 'buy followers',
            'get followers fast', 'instagram growth', 'follow back guaranteed'
        ])
        
        for keyword in spam_keywords:
            if keyword in biography:
                return False, f"spam_keyword: {keyword}"
        
        # Check if username looks like spam/bot
        username_lower = username.lower()
        if any(pattern in username_lower for pattern in ['_official', 'real_', '_verified']):
            if not user.get('is_verified', False):
                return False, "suspicious_username"
        
        return True, "approved"
    
    def _follow_user_with_logging(self, user: Dict[str, Any], source: str = "unknown") -> bool:
        """
        Follow a user and log the action
        Returns True if successful
        """
        user_id = str(user.get('id', ''))
        username = user.get('username', 'unknown')
        
        try:
            success = self.client.follow_user(user_id)
            
            # Log the action
            log_entry = {
                'timestamp': datetime.now().isoformat(),
                'action': 'follow',
                'user_id': user_id,
                'username': username,
                'source': source,
                'success': success,
                'follower_count': user.get('follower_count', 0),
                'following_count': user.get('following_count', 0),
                'media_count': user.get('media_count', 0),
                'is_verified': user.get('is_verified', False),
                'biography_preview': user.get('biography', '')[:100]
            }
            
            save_action_log('follows', log_entry)
            
            if success:
                self.followed_users.add(user_id)
                self.stats['successful_follows'] += 1
                logger.info(f"✅ Followed @{username} ({user.get('follower_count', 0)} followers) - Source: {source}")
            else:
                self.failed_follows.add(user_id)
                self.stats['failed_follows'] += 1
                logger.warning(f"❌ Failed to follow @{username} - Source: {source}")
            
            self.stats['total_follows'] += 1
            return success
            
        except Exception as e:
            logger.error(f"Error following user {username}: {e}")
            self.failed_follows.add(user_id)
            self.stats['failed_follows'] += 1
            return False
    
    def follow_target_users(self) -> Dict[str, Any]:
        """
        Follow users from the target_users list in config
        Returns statistics
        """
        logger.info("Starting target users following")
        
        stats = {
            'start_time': datetime.now().isoformat(),
            'users_processed': 0,
            'users_followed': 0,
            'errors': 0
        }
        
        target_users = self.follow_config.get('target_users', [])
        
        if not target_users:
            logger.info("No target users configured")
            return stats
        
        for username in target_users:
            try:
                # Check rate limits
                rate_status = self.client.get_rate_limit_status()
                if rate_status['hourly_follows'] >= rate_status['follows_limit']:
                    logger.warning("Hourly follow limit reached")
                    break
                
                # Get user info
                user_info = self.client.get_user_info(username)
                if not user_info:
                    logger.warning(f"Could not get info for user @{username}")
                    stats['errors'] += 1
                    continue
                
                stats['users_processed'] += 1
                self.stats['users_analyzed'] += 1
                
                should_follow, reason = self._should_follow_user(user_info)
                
                if should_follow:
                    success = self._follow_user_with_logging(user_info, "target_user")
                    if success:
                        stats['users_followed'] += 1
                        
                        # Add delay between follows
                        delay = random.uniform(30, 90)  # 30-90 seconds between follows
                        logger.info(f"Waiting {delay:.1f} seconds before next follow")
                        time.sleep(delay)
                else:
                    self.stats['skipped_users'] += 1
                    logger.debug(f"Skipped @{username}: {reason}")
                
            except Exception as e:
                logger.error(f"Error processing target user @{username}: {e}")
                stats['errors'] += 1
        
        stats['end_time'] = datetime.now().isoformat()
        return stats
    
    def follow_users_followers(self, target_username: str, max_follows: int = None) -> Dict[str, Any]:
        """
        Follow followers of a specific user
        Returns statistics
        """
        logger.info(f"Starting to follow followers of @{target_username}")
        
        if max_follows is None:
            max_follows = self.follow_config.get('max_follows_per_user', 50)
        
        stats = {
            'start_time': datetime.now().isoformat(),
            'target_username': target_username,
            'followers_found': 0,
            'users_processed': 0,
            'users_followed': 0,
            'errors': 0
        }
        
        try:
            # Get target user info first
            target_user = self.client.get_user_info(target_username)
            if not target_user:
                logger.error(f"Could not find user @{target_username}")
                stats['error'] = "target_user_not_found"
                return stats
            
            target_user_id = target_user.get('id')
            
            # Get followers
            followers = self.client.get_user_followers(target_user_id, count=max_follows * 2)
            if not followers:
                logger.warning(f"Could not get followers for @{target_username}")
                stats['error'] = "could_not_get_followers"
                return stats
            
            stats['followers_found'] = len(followers)
            logger.info(f"Found {len(followers)} followers of @{target_username}")
            
            # Shuffle to avoid predictable patterns
            random.shuffle(followers)
            
            follows_made = 0
            
            for follower in followers:
                if follows_made >= max_follows:
                    break
                
                # Check rate limits
                rate_status = self.client.get_rate_limit_status()
                if rate_status['hourly_follows'] >= rate_status['follows_limit']:
                    logger.warning("Hourly follow limit reached")
                    break
                
                stats['users_processed'] += 1
                self.stats['users_analyzed'] += 1
                
                should_follow, reason = self._should_follow_user(follower)
                
                if should_follow:
                    success = self._follow_user_with_logging(follower, f"follower_of_{target_username}")
                    if success:
                        follows_made += 1
                        stats['users_followed'] += 1
                        
                        # Add delay between follows
                        delay = random.uniform(45, 120)  # 45-120 seconds between follows
                        logger.info(f"Waiting {delay:.1f} seconds before next follow")
                        time.sleep(delay)
                else:
                    self.stats['skipped_users'] += 1
                    logger.debug(f"Skipped @{follower.get('username')}: {reason}")
            
        except Exception as e:
            logger.error(f"Error following followers of @{target_username}: {e}")
            stats['error'] = str(e)
            stats['errors'] += 1
        
        stats['end_time'] = datetime.now().isoformat()
        return stats
    
    def run_following_session(self) -> Dict[str, Any]:
        """
        Run a complete following session using all configured strategies
        Returns session statistics
        """
        logger.info("Starting following session")
        
        session_stats = {
            'start_time': datetime.now().isoformat(),
            'strategies_used': [],
            'total_follows': 0,
            'total_errors': 0,
            'rate_limit_status': {}
        }
        
        try:
            # Strategy 1: Follow target users
            target_users = self.follow_config.get('target_users', [])
            if target_users:
                logger.info("Executing strategy: Target users")
                target_stats = self.follow_target_users()
                session_stats['strategies_used'].append({
                    'strategy': 'target_users',
                    'stats': target_stats
                })
                session_stats['total_follows'] += target_stats['users_followed']
                session_stats['total_errors'] += target_stats['errors']
            
            # Strategy 2: Follow followers of specific users
            follow_followers_of = self.follow_config.get('follow_followers_of', [])
            for target_user in follow_followers_of:
                # Check if we've reached limits
                rate_status = self.client.get_rate_limit_status()
                if rate_status['hourly_follows'] >= rate_status['follows_limit']:
                    logger.warning("Hourly follow limit reached, stopping session")
                    break
                
                logger.info(f"Executing strategy: Following followers of @{target_user}")
                followers_stats = self.follow_users_followers(target_user)
                session_stats['strategies_used'].append({
                    'strategy': f'followers_of_{target_user}',
                    'stats': followers_stats
                })
                session_stats['total_follows'] += followers_stats['users_followed']
                session_stats['total_errors'] += followers_stats['errors']
                
                # Add delay between different target users
                if target_user != follow_followers_of[-1]:
                    delay = random.uniform(180, 300)  # 3-5 minutes between different targets
                    logger.info(f"Waiting {delay:.1f} seconds before next target")
                    time.sleep(delay)
            
            session_stats['rate_limit_status'] = self.client.get_rate_limit_status()
            session_stats['end_time'] = datetime.now().isoformat()
            
            logger.info(f"Following session completed: {session_stats['total_follows']} total follows")
            
        except Exception as e:
            logger.error(f"Error in following session: {e}")
            session_stats['error'] = str(e)
        
        return session_stats
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get current statistics"""
        return {
            **self.stats,
            'followed_users_count': len(self.followed_users),
            'failed_follows_count': len(self.failed_follows),
            'processed_users_count': len(self.processed_users),
            'rate_limit_status': self.client.get_rate_limit_status()
        }
    
    def reset_session_data(self):
        """Reset session data (for testing or new sessions)"""
        self.followed_users.clear()
        self.failed_follows.clear()
        self.processed_users.clear()
        self.stats = {
            'total_follows': 0,
            'successful_follows': 0,
            'failed_follows': 0,
            'skipped_users': 0,
            'users_analyzed': 0,
            'session_start': datetime.now().isoformat()
        }
        logger.info("Session data reset")