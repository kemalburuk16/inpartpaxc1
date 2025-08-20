#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Instagram Client - Instagram API wrapper integrating with existing session infrastructure
"""

import json
import time
import random
import logging
from typing import Dict, Any, Optional, List, Tuple
import requests
import sys
import os

# Add parent directory to path to import session_pool
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from session_pool import SessionPool

logger = logging.getLogger(__name__)


class InstagramClient:
    """
    Instagram API client that uses the existing SessionPool infrastructure
    for authentication and rate limiting.
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.session_pool = SessionPool()
        self.rate_limits = config.get('instagram', {}).get('rate_limits', {})
        self.safety = config.get('instagram', {}).get('safety', {})
        
        # Rate limiting counters
        self._last_request_time = 0
        self._request_count = 0
        self._hourly_likes = 0
        self._hourly_follows = 0
        self._hour_start = time.time()
        
        logger.info("Instagram client initialized with existing session pool")
    
    def _check_rate_limits(self, action_type: str = "request") -> bool:
        """Check if we're within rate limits for the given action type"""
        current_time = time.time()
        
        # Reset hourly counters
        if current_time - self._hour_start > 3600:
            self._hourly_likes = 0
            self._hourly_follows = 0
            self._hour_start = current_time
        
        # Check hourly limits
        if action_type == "like" and self._hourly_likes >= self.rate_limits.get('likes_per_hour', 60):
            logger.warning(f"Hourly like limit reached: {self._hourly_likes}")
            return False
            
        if action_type == "follow" and self._hourly_follows >= self.rate_limits.get('follows_per_hour', 30):
            logger.warning(f"Hourly follow limit reached: {self._hourly_follows}")
            return False
        
        # Check minimum delay between requests
        min_delay = self.rate_limits.get('min_delay_seconds', 10)
        if current_time - self._last_request_time < min_delay:
            wait_time = min_delay - (current_time - self._last_request_time)
            logger.info(f"Waiting {wait_time:.1f} seconds to respect rate limits")
            time.sleep(wait_time)
        
        return True
    
    def _apply_random_delay(self):
        """Apply random delay to mimic human behavior"""
        if self.safety.get('random_delays', True):
            min_delay = self.rate_limits.get('min_delay_seconds', 10)
            max_delay = self.rate_limits.get('max_delay_seconds', 30)
            delay = random.uniform(min_delay, max_delay)
            logger.debug(f"Applying random delay: {delay:.1f} seconds")
            time.sleep(delay)
    
    def _make_request(self, method: str, url: str, **kwargs) -> Optional[requests.Response]:
        """Make HTTP request using session pool with error handling"""
        try:
            if method.upper() == 'GET':
                response = self.session_pool.http_get(url, **kwargs)
            elif method.upper() == 'POST':
                response = self.session_pool.http_post(url, **kwargs)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            self._last_request_time = time.time()
            self._request_count += 1
            
            if response.status_code == 200:
                logger.debug(f"Successful request to {url}")
                return response
            else:
                logger.warning(f"Request failed with status {response.status_code}: {url}")
                return response
                
        except Exception as e:
            logger.error(f"Request error for {url}: {e}")
            return None
    
    def search_hashtag(self, hashtag: str, count: int = 20) -> List[Dict[str, Any]]:
        """
        Search for posts by hashtag
        Returns list of post data
        """
        if not self._check_rate_limits():
            return []
        
        # Instagram hashtag search endpoint
        url = f"https://i.instagram.com/api/v1/tags/{hashtag}/recent_media/"
        params = {"count": min(count, 50)}  # Limit to avoid issues
        
        response = self._make_request('GET', url, params=params)
        if not response or response.status_code != 200:
            return []
        
        try:
            data = response.json()
            posts = []
            
            for item in data.get('items', []):
                post_data = {
                    'id': item.get('id'),
                    'media_type': item.get('media_type'),
                    'user_id': item.get('user', {}).get('pk'),
                    'username': item.get('user', {}).get('username'),
                    'caption': item.get('caption', {}).get('text', '') if item.get('caption') else '',
                    'like_count': item.get('like_count', 0),
                    'has_liked': item.get('has_liked', False),
                    'taken_at': item.get('taken_at')
                }
                posts.append(post_data)
            
            logger.info(f"Found {len(posts)} posts for hashtag #{hashtag}")
            self._apply_random_delay()
            return posts
            
        except Exception as e:
            logger.error(f"Error parsing hashtag search response: {e}")
            return []
    
    def like_post(self, media_id: str) -> bool:
        """
        Like a post by media ID
        Returns True if successful
        """
        if not self._check_rate_limits("like"):
            return False
        
        url = f"https://i.instagram.com/api/v1/media/{media_id}/like/"
        
        response = self._make_request('POST', url)
        if response and response.status_code == 200:
            self._hourly_likes += 1
            logger.info(f"Successfully liked post {media_id}")
            self._apply_random_delay()
            return True
        else:
            logger.warning(f"Failed to like post {media_id}")
            return False
    
    def unlike_post(self, media_id: str) -> bool:
        """
        Unlike a post by media ID
        Returns True if successful
        """
        if not self._check_rate_limits():
            return False
        
        url = f"https://i.instagram.com/api/v1/media/{media_id}/unlike/"
        
        response = self._make_request('POST', url)
        if response and response.status_code == 200:
            logger.info(f"Successfully unliked post {media_id}")
            self._apply_random_delay()
            return True
        else:
            logger.warning(f"Failed to unlike post {media_id}")
            return False
    
    def get_user_info(self, username: str) -> Optional[Dict[str, Any]]:
        """
        Get user information by username
        """
        if not self._check_rate_limits():
            return None
        
        url = f"https://i.instagram.com/api/v1/users/web_profile_info/"
        params = {"username": username}
        
        response = self._make_request('GET', url, params=params)
        if not response or response.status_code != 200:
            return None
        
        try:
            data = response.json()
            user = data.get('data', {}).get('user', {})
            
            user_info = {
                'id': user.get('id'),
                'username': user.get('username'),
                'full_name': user.get('full_name'),
                'follower_count': user.get('edge_followed_by', {}).get('count', 0),
                'following_count': user.get('edge_follow', {}).get('count', 0),
                'media_count': user.get('edge_owner_to_timeline_media', {}).get('count', 0),
                'is_private': user.get('is_private', False),
                'is_verified': user.get('is_verified', False),
                'biography': user.get('biography', ''),
                'external_url': user.get('external_url')
            }
            
            logger.info(f"Retrieved user info for {username}")
            self._apply_random_delay()
            return user_info
            
        except Exception as e:
            logger.error(f"Error parsing user info response: {e}")
            return None
    
    def follow_user(self, user_id: str) -> bool:
        """
        Follow a user by user ID
        Returns True if successful
        """
        if not self._check_rate_limits("follow"):
            return False
        
        url = f"https://i.instagram.com/api/v1/friendships/create/{user_id}/"
        
        response = self._make_request('POST', url)
        if response and response.status_code == 200:
            self._hourly_follows += 1
            logger.info(f"Successfully followed user {user_id}")
            self._apply_random_delay()
            return True
        else:
            logger.warning(f"Failed to follow user {user_id}")
            return False
    
    def unfollow_user(self, user_id: str) -> bool:
        """
        Unfollow a user by user ID
        Returns True if successful
        """
        if not self._check_rate_limits():
            return False
        
        url = f"https://i.instagram.com/api/v1/friendships/destroy/{user_id}/"
        
        response = self._make_request('POST', url)
        if response and response.status_code == 200:
            logger.info(f"Successfully unfollowed user {user_id}")
            self._apply_random_delay()
            return True
        else:
            logger.warning(f"Failed to unfollow user {user_id}")
            return False
    
    def get_user_followers(self, user_id: str, count: int = 50) -> List[Dict[str, Any]]:
        """
        Get followers of a user
        Returns list of follower data
        """
        if not self._check_rate_limits():
            return []
        
        url = f"https://i.instagram.com/api/v1/friendships/{user_id}/followers/"
        params = {"count": min(count, 200)}  # Reasonable limit
        
        response = self._make_request('GET', url, params=params)
        if not response or response.status_code != 200:
            return []
        
        try:
            data = response.json()
            followers = []
            
            for user in data.get('users', []):
                follower_data = {
                    'id': user.get('pk'),
                    'username': user.get('username'),
                    'full_name': user.get('full_name'),
                    'is_private': user.get('is_private', False),
                    'is_verified': user.get('is_verified', False),
                    'follower_count': user.get('follower_count', 0)
                }
                followers.append(follower_data)
            
            logger.info(f"Retrieved {len(followers)} followers for user {user_id}")
            self._apply_random_delay()
            return followers
            
        except Exception as e:
            logger.error(f"Error parsing followers response: {e}")
            return []
    
    def get_rate_limit_status(self) -> Dict[str, Any]:
        """Get current rate limit status"""
        current_time = time.time()
        return {
            'hourly_likes': self._hourly_likes,
            'hourly_follows': self._hourly_follows,
            'likes_limit': self.rate_limits.get('likes_per_hour', 60),
            'follows_limit': self.rate_limits.get('follows_per_hour', 30),
            'hour_remaining': 3600 - (current_time - self._hour_start),
            'total_requests': self._request_count,
            'last_request': self._last_request_time
        }