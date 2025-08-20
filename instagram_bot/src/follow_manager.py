import json
import logging
import random
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Set

from instagram_client import InstagramClient
from utils import (
    setup_logging, get_random_delay, is_within_limits,
    is_user_blacklisted, get_daily_stats, get_current_hour_stats, 
    update_stats, format_username
)


class FollowManager:
    """
    Manages automatic following and unfollowing functionality with safety controls.
    """
    
    def __init__(self, client: InstagramClient, config: Dict[str, Any]):
        self.client = client
        self.config = config
        self.logger = setup_logging()
        
        # Track follow/unfollow activity
        self.followed_users_file = "logs/followed_users.json"
        self.following_data = {}
        self._load_following_data()
        
        # Activity tracking
        self.session_follows = 0
        self.session_unfollows = 0
        self.consecutive_failures = 0
        self.max_consecutive_failures = config.get('safety', {}).get('max_consecutive_failures', 3)
        
        # Follow strategy settings
        self.follow_strategy = config.get('follow_strategy', {})
        self.unfollow_after_days = self.follow_strategy.get('unfollow_after_days', 7)
        self.follow_ratio_limit = self.follow_strategy.get('follow_ratio_limit', 1.2)
    
    def _load_following_data(self) -> None:
        """Load following data from file."""
        try:
            with open(self.followed_users_file, 'r') as f:
                self.following_data = json.load(f)
                self.logger.info(f"Loaded following data for {len(self.following_data)} users")
        except FileNotFoundError:
            self.following_data = {}
            self.logger.info("No previous following data file found")
        except Exception as e:
            self.logger.error(f"Failed to load following data: {e}")
            self.following_data = {}
    
    def _save_following_data(self) -> None:
        """Save following data to file."""
        try:
            import os
            os.makedirs(os.path.dirname(self.followed_users_file), exist_ok=True)
            
            with open(self.followed_users_file, 'w') as f:
                json.dump(self.following_data, f, indent=2)
        except Exception as e:
            self.logger.error(f"Failed to save following data: {e}")
    
    def can_follow_more(self) -> bool:
        """Check if we can follow more users based on limits."""
        daily_follows = get_daily_stats('follows')
        hourly_follows = get_current_hour_stats('follows')
        
        return is_within_limits('follows', daily_follows, hourly_follows, self.config)
    
    def can_unfollow_more(self) -> bool:
        """Check if we can unfollow more users based on limits."""
        daily_unfollows = get_daily_stats('unfollows')
        hourly_unfollows = get_current_hour_stats('unfollows')
        
        return is_within_limits('unfollows', daily_unfollows, hourly_unfollows, self.config)
    
    def follow_user(self, username: str, reason: str = "targeted") -> bool:
        """Follow a specific user."""
        username = format_username(username)
        
        if is_user_blacklisted(username, self.config):
            self.logger.warning(f"User {username} is blacklisted")
            return False
        
        if not self.can_follow_more():
            self.logger.warning("Follow limit reached")
            return False
        
        try:
            # Get user info first
            user_info = self.client.get_user_info(username)
            if not user_info:
                self.logger.error(f"Failed to get user info for: {username}")
                self.consecutive_failures += 1
                return False
            
            user_id = user_info.get('id')
            if not user_id:
                self.logger.error(f"No user ID found for: {username}")
                return False
            
            # Check if already following
            friendship_status = self.client.check_friendship_status(user_id)
            if friendship_status and friendship_status.get('following', False):
                self.logger.info(f"Already following {username}")
                return True
            
            # Check follow strategy constraints
            if not self._should_follow_user(user_info):
                self.logger.debug(f"User {username} doesn't meet follow criteria")
                return False
            
            # Follow the user
            success = self.client.follow_user(user_id)
            
            if success:
                # Record the follow
                self.following_data[user_id] = {
                    'username': username,
                    'followed_at': datetime.now().isoformat(),
                    'reason': reason,
                    'user_info': {
                        'followers': user_info.get('edge_followed_by', {}).get('count', 0),
                        'following': user_info.get('edge_follow', {}).get('count', 0),
                        'is_verified': user_info.get('is_verified', False),
                        'is_private': user_info.get('is_private', False)
                    }
                }
                
                self.session_follows += 1
                self.consecutive_failures = 0
                update_stats('follows')
                
                self.logger.info(f"Successfully followed @{username} (reason: {reason})")
                
                # Save data periodically
                if len(self.following_data) % 5 == 0:
                    self._save_following_data()
                
                return True
            else:
                self.consecutive_failures += 1
                self.logger.warning(f"Failed to follow {username}")
                return False
                
        except Exception as e:
            self.consecutive_failures += 1
            self.logger.error(f"Error following user {username}: {e}")
            return False
    
    def unfollow_user(self, username: str, reason: str = "cleanup") -> bool:
        """Unfollow a specific user."""
        username = format_username(username)
        
        if not self.can_unfollow_more():
            self.logger.warning("Unfollow limit reached")
            return False
        
        try:
            # Get user info
            user_info = self.client.get_user_info(username)
            if not user_info:
                self.logger.error(f"Failed to get user info for: {username}")
                return False
            
            user_id = user_info.get('id')
            if not user_id:
                self.logger.error(f"No user ID found for: {username}")
                return False
            
            # Check if actually following
            friendship_status = self.client.check_friendship_status(user_id)
            if not (friendship_status and friendship_status.get('following', False)):
                self.logger.info(f"Not following {username}")
                # Remove from our data if exists
                if user_id in self.following_data:
                    del self.following_data[user_id]
                    self._save_following_data()
                return True
            
            # Unfollow the user
            success = self.client.unfollow_user(user_id)
            
            if success:
                # Remove from following data
                if user_id in self.following_data:
                    del self.following_data[user_id]
                
                self.session_unfollows += 1
                self.consecutive_failures = 0
                update_stats('unfollows')
                
                self.logger.info(f"Successfully unfollowed @{username} (reason: {reason})")
                
                # Save data
                self._save_following_data()
                
                return True
            else:
                self.consecutive_failures += 1
                self.logger.warning(f"Failed to unfollow {username}")
                return False
                
        except Exception as e:
            self.consecutive_failures += 1
            self.logger.error(f"Error unfollowing user {username}: {e}")
            return False
    
    def _should_follow_user(self, user_info: Dict[str, Any]) -> bool:
        """Determine if a user should be followed based on strategy."""
        try:
            # Skip if verified and configured to skip
            if (self.follow_strategy.get('skip_verified_users', False) and 
                user_info.get('is_verified', False)):
                return False
            
            # Skip if private and configured to skip
            if (self.follow_strategy.get('skip_private_users', True) and 
                user_info.get('is_private', False)):
                return False
            
            # Check follow ratio
            followers = user_info.get('edge_followed_by', {}).get('count', 0)
            following = user_info.get('edge_follow', {}).get('count', 0)
            
            if following > 0 and followers > 0:
                ratio = following / followers
                if ratio > self.follow_ratio_limit:
                    return False
            
            # Additional criteria can be added here
            # e.g., minimum/maximum follower count, activity level, etc.
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error checking follow criteria: {e}")
            return False
    
    def follow_followers_of_user(self, target_username: str, max_follows: int = 20) -> Dict[str, Any]:
        """Follow followers of a target user."""
        results = {
            'target_user': target_username,
            'users_processed': 0,
            'users_followed': 0,
            'users_skipped': 0,
            'errors': []
        }
        
        target_username = format_username(target_username)
        
        if not self.can_follow_more():
            self.logger.warning("Follow limit reached")
            results['errors'].append("Follow limit reached")
            return results
        
        self.logger.info(f"Starting to follow followers of: {target_username}")
        
        try:
            # Get target user info
            target_user_info = self.client.get_user_info(target_username)
            if not target_user_info:
                self.logger.error(f"Failed to get info for target user: {target_username}")
                results['errors'].append("Failed to get target user info")
                return results
            
            target_user_id = target_user_info.get('id')
            if not target_user_id:
                self.logger.error(f"No user ID for target user: {target_username}")
                results['errors'].append("No target user ID")
                return results
            
            # Get followers of target user
            followers_data = self.client.get_user_followers(target_user_id)
            if not followers_data:
                self.logger.error(f"Failed to get followers for: {target_username}")
                results['errors'].append("Failed to get followers")
                return results
            
            followers = followers_data.get('users', [])
            if not followers:
                self.logger.warning(f"No followers found for: {target_username}")
                results['errors'].append("No followers found")
                return results
            
            # Shuffle followers for more natural behavior
            random.shuffle(followers)
            
            followed_count = 0
            for follower in followers:
                if not self.can_follow_more() or followed_count >= max_follows:
                    break
                
                results['users_processed'] += 1
                follower_username = follower.get('username', '')
                
                if not follower_username:
                    results['users_skipped'] += 1
                    continue
                
                if is_user_blacklisted(follower_username, self.config):
                    results['users_skipped'] += 1
                    continue
                
                if self.follow_user(follower_username, f"follower_of_{target_username}"):
                    results['users_followed'] += 1
                    followed_count += 1
                    self._apply_follow_delay()
                else:
                    results['users_skipped'] += 1
                
                # Check for consecutive failures
                if self.consecutive_failures >= self.max_consecutive_failures:
                    self.logger.warning("Too many consecutive failures, stopping")
                    results['errors'].append("Too many consecutive failures")
                    break
        
        except Exception as e:
            self.logger.error(f"Error following followers: {e}")
            results['errors'].append(str(e))
        
        self.logger.info(f"Follow followers session complete: {results}")
        return results
    
    def auto_unfollow_old(self) -> Dict[str, Any]:
        """Automatically unfollow users that were followed a certain time ago."""
        results = {
            'users_processed': 0,
            'users_unfollowed': 0,
            'users_skipped': 0,
            'errors': []
        }
        
        if not self.can_unfollow_more():
            self.logger.warning("Unfollow limit reached")
            results['errors'].append("Unfollow limit reached")
            return results
        
        cutoff_date = datetime.now() - timedelta(days=self.unfollow_after_days)
        users_to_unfollow = []
        
        # Find users to unfollow
        for user_id, data in self.following_data.items():
            try:
                followed_at = datetime.fromisoformat(data['followed_at'])
                if followed_at < cutoff_date:
                    users_to_unfollow.append((user_id, data))
            except:
                # Invalid date format, consider for unfollowing
                users_to_unfollow.append((user_id, data))
        
        if not users_to_unfollow:
            self.logger.info("No users to unfollow")
            return results
        
        self.logger.info(f"Found {len(users_to_unfollow)} users to unfollow")
        
        # Shuffle for more natural behavior
        random.shuffle(users_to_unfollow)
        
        for user_id, data in users_to_unfollow:
            if not self.can_unfollow_more():
                break
            
            results['users_processed'] += 1
            username = data.get('username', '')
            
            if self.unfollow_user(username, "auto_cleanup"):
                results['users_unfollowed'] += 1
                self._apply_unfollow_delay()
            else:
                results['users_skipped'] += 1
            
            # Check for consecutive failures
            if self.consecutive_failures >= self.max_consecutive_failures:
                self.logger.warning("Too many consecutive failures, stopping")
                results['errors'].append("Too many consecutive failures")
                break
        
        self.logger.info(f"Auto unfollow session complete: {results}")
        return results
    
    def _apply_follow_delay(self) -> None:
        """Apply delay between follows to simulate human behavior."""
        delays = self.config.get('delays', {})
        min_delay = delays.get('min_follow_delay', 20)
        max_delay = delays.get('max_follow_delay', 60)
        
        delay = get_random_delay(min_delay, max_delay)
        self.logger.debug(f"Applying follow delay: {delay} seconds")
        time.sleep(delay)
    
    def _apply_unfollow_delay(self) -> None:
        """Apply delay between unfollows to simulate human behavior."""
        delays = self.config.get('delays', {})
        min_delay = delays.get('min_unfollow_delay', 15)
        max_delay = delays.get('max_unfollow_delay', 45)
        
        delay = get_random_delay(min_delay, max_delay)
        self.logger.debug(f"Applying unfollow delay: {delay} seconds")
        time.sleep(delay)
    
    def auto_follow_strategy(self, max_follows: int = 20) -> Dict[str, Any]:
        """Execute automatic following strategy."""
        results = {
            'total_followed': 0,
            'strategies_executed': [],
            'errors': []
        }
        
        if not self.can_follow_more():
            self.logger.warning("Follow limit reached")
            results['errors'].append("Follow limit reached")
            return results
        
        # Strategy 1: Follow followers of target users
        target_users = self.follow_strategy.get('target_users', [])
        if target_users and self.follow_strategy.get('follow_followers_of_target', True):
            for target_user in target_users:
                if not self.can_follow_more():
                    break
                
                follows_for_this_target = min(max_follows // len(target_users), 10)
                result = self.follow_followers_of_user(target_user, follows_for_this_target)
                
                results['total_followed'] += result['users_followed']
                results['strategies_executed'].append({
                    'strategy': 'follow_followers',
                    'target': target_user,
                    'result': result
                })
                
                if result['errors']:
                    results['errors'].extend(result['errors'])
                
                # Delay between target users
                if target_user != target_users[-1]:
                    delay = get_random_delay(60, 180)
                    self.logger.info(f"Delaying {delay} seconds before next target user")
                    time.sleep(delay)
        
        self.logger.info(f"Auto follow strategy complete: {results}")
        return results
    
    def get_follow_stats(self) -> Dict[str, Any]:
        """Get following statistics."""
        current_following = len(self.following_data)
        
        # Calculate users ready for unfollow
        cutoff_date = datetime.now() - timedelta(days=self.unfollow_after_days)
        ready_for_unfollow = 0
        
        for data in self.following_data.values():
            try:
                followed_at = datetime.fromisoformat(data['followed_at'])
                if followed_at < cutoff_date:
                    ready_for_unfollow += 1
            except:
                ready_for_unfollow += 1
        
        return {
            'session_follows': self.session_follows,
            'session_unfollows': self.session_unfollows,
            'current_following': current_following,
            'ready_for_unfollow': ready_for_unfollow,
            'daily_follows': get_daily_stats('follows'),
            'hourly_follows': get_current_hour_stats('follows'),
            'daily_unfollows': get_daily_stats('unfollows'),
            'hourly_unfollows': get_current_hour_stats('unfollows'),
            'consecutive_failures': self.consecutive_failures,
            'can_follow_more': self.can_follow_more(),
            'can_unfollow_more': self.can_unfollow_more()
        }
    
    def cleanup_following_data(self) -> None:
        """Clean up following data and save."""
        # Remove old entries that are no longer being followed
        # This would require checking actual follow status, which is expensive
        # For now, just save current data
        self._save_following_data()
        self.logger.info("Following data cleaned up")
    
    def get_users_to_unfollow(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get list of users that are ready to be unfollowed."""
        cutoff_date = datetime.now() - timedelta(days=self.unfollow_after_days)
        users_to_unfollow = []
        
        for user_id, data in self.following_data.items():
            try:
                followed_at = datetime.fromisoformat(data['followed_at'])
                if followed_at < cutoff_date:
                    users_to_unfollow.append({
                        'user_id': user_id,
                        'username': data.get('username', ''),
                        'followed_at': data['followed_at'],
                        'reason': data.get('reason', ''),
                        'days_since_follow': (datetime.now() - followed_at).days
                    })
            except:
                # Invalid date, add to unfollow list
                users_to_unfollow.append({
                    'user_id': user_id,
                    'username': data.get('username', ''),
                    'followed_at': data.get('followed_at', ''),
                    'reason': data.get('reason', ''),
                    'days_since_follow': 999
                })
        
        # Sort by days since follow (oldest first)
        users_to_unfollow.sort(key=lambda x: x['days_since_follow'], reverse=True)
        
        return users_to_unfollow[:limit]