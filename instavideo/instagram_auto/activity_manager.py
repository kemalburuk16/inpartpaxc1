#!/usr/bin/env python3
"""
Instagram Automation Activity Manager
Handles Instagram activities like liking, following, browsing, etc.
"""

import json
import time
import random
import requests
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path

try:
    from .session_manager import AutoSessionManager
except ImportError:
    from session_manager import AutoSessionManager

class InstagramActivityManager:
    """Manages Instagram automation activities"""
    
    def __init__(self, session_manager: Optional[AutoSessionManager] = None):
        self.session_manager = session_manager or AutoSessionManager()
        self.config = self.session_manager.config
        self.base_headers = {
            "accept": "*/*",
            "accept-language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
            "cache-control": "no-cache",
            "pragma": "no-cache",
            "sec-ch-ua": '"Chromium";v="123", "Google Chrome";v="123", ";Not A Brand";v="99"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "x-asbd-id": "129477",
            "x-ig-app-id": "1217981644879628",
        }
    
    def _get_session_cookies(self, session: Dict[str, Any]) -> Dict[str, str]:
        """Extract cookies from session object"""
        cookies = {}
        
        # Try to get cookies from 'cookies' field first
        if 'cookies' in session and isinstance(session['cookies'], dict):
            cookies = session['cookies'].copy()
        
        # Ensure essential cookies are present
        essential_keys = ['sessionid', 'ds_user_id', 'csrftoken']
        for key in essential_keys:
            if key in session and (key not in cookies or not cookies[key]):
                cookies[key] = session[key]
        
        return cookies
    
    def _get_session_headers(self, session: Dict[str, Any]) -> Dict[str, str]:
        """Get headers for session including fingerprint data"""
        headers = self.base_headers.copy()
        
        # Add fingerprint data if available
        if 'fingerprint' in session:
            fp = session['fingerprint']
            headers.update({
                "user-agent": fp.get('user_agent', headers.get('user-agent', '')),
                "accept-language": fp.get('accept_language', headers.get('accept-language', '')),
                "sec-ch-ua": fp.get('sec_ch_ua', headers.get('sec-ch-ua', '')),
                "sec-ch-ua-mobile": fp.get('sec_ch_ua_mobile', headers.get('sec-ch-ua-mobile', '')),
                "sec-ch-ua-platform": fp.get('sec_ch_ua_platform', headers.get('sec-ch-ua-platform', '')),
                "referer": fp.get('referer', 'https://www.instagram.com/'),
                "x-ig-app-id": fp.get('x_ig_app_id', headers.get('x-ig-app-id', '')),
                "x-asbd-id": fp.get('x_asbd_id', headers.get('x-asbd-id', '')),
            })
        
        return headers
    
    def _make_request(self, session: Dict[str, Any], method: str, url: str, 
                     data: Optional[Dict] = None, json_data: Optional[Dict] = None) -> Tuple[bool, Optional[Dict]]:
        """Make HTTP request with session"""
        try:
            cookies = self._get_session_cookies(session)
            headers = self._get_session_headers(session)
            
            # Add CSRF token to headers for POST requests
            if method.upper() == 'POST' and 'csrftoken' in cookies:
                headers['x-csrftoken'] = cookies['csrftoken']
            
            # Setup proxy if available
            proxies = None
            if session.get('proxy'):
                proxies = {
                    'http': session['proxy'],
                    'https': session['proxy']
                }
            
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                cookies=cookies,
                data=data,
                json=json_data,
                proxies=proxies,
                timeout=15,
                allow_redirects=True
            )
            
            if response.status_code == 200:
                try:
                    return True, response.json()
                except ValueError:
                    return True, {"text": response.text}
            elif response.status_code in [401, 403, 429]:
                # Session might be blocked or rate limited
                self.session_manager.mark_session_blocked(session, duration_minutes=60)
                return False, {"error": f"HTTP {response.status_code}", "blocked": True}
            else:
                return False, {"error": f"HTTP {response.status_code}"}
                
        except requests.RequestException as e:
            return False, {"error": str(e)}
    
    def like_post(self, session: Dict[str, Any], media_id: str) -> bool:
        """Like a post"""
        url = f"https://www.instagram.com/web/likes/{media_id}/like/"
        
        success, response = self._make_request(session, 'POST', url)
        
        # Log the activity
        self.session_manager.log_activity(session, 'likes', media_id, success)
        
        if success:
            self.session_manager.update_session_usage(session)
            return True
        
        return False
    
    def unlike_post(self, session: Dict[str, Any], media_id: str) -> bool:
        """Unlike a post"""
        url = f"https://www.instagram.com/web/likes/{media_id}/unlike/"
        
        success, response = self._make_request(session, 'POST', url)
        
        # Log the activity
        self.session_manager.log_activity(session, 'unlikes', media_id, success)
        
        if success:
            self.session_manager.update_session_usage(session)
            return True
        
        return False
    
    def follow_user(self, session: Dict[str, Any], user_id: str) -> bool:
        """Follow a user"""
        url = f"https://www.instagram.com/web/friendships/{user_id}/follow/"
        
        success, response = self._make_request(session, 'POST', url)
        
        # Log the activity
        self.session_manager.log_activity(session, 'follows', user_id, success)
        
        if success:
            self.session_manager.update_session_usage(session)
            return True
        
        return False
    
    def unfollow_user(self, session: Dict[str, Any], user_id: str) -> bool:
        """Unfollow a user"""
        url = f"https://www.instagram.com/web/friendships/{user_id}/unfollow/"
        
        success, response = self._make_request(session, 'POST', url)
        
        # Log the activity
        self.session_manager.log_activity(session, 'unfollows', user_id, success)
        
        if success:
            self.session_manager.update_session_usage(session)
            return True
        
        return False
    
    def view_story(self, session: Dict[str, Any], story_id: str) -> bool:
        """View a story"""
        url = "https://www.instagram.com/web/stories/reel/seen"
        data = {
            'reelMediaId': story_id,
            'reelMediaOwnerId': story_id.split('_')[1] if '_' in story_id else '',
            'reelId': story_id.split('_')[1] if '_' in story_id else '',
            'reelMediaTakenAt': int(time.time()),
            'viewSeenAt': int(time.time())
        }
        
        success, response = self._make_request(session, 'POST', url, data=data)
        
        # Log the activity
        self.session_manager.log_activity(session, 'story_views', story_id, success)
        
        if success:
            self.session_manager.update_session_usage(session)
            return True
        
        return False
    
    def browse_feed(self, session: Dict[str, Any], duration: int = 60) -> bool:
        """Browse the main feed for specified duration"""
        url = "https://www.instagram.com/api/v1/feed/timeline/"
        
        start_time = time.time()
        actions_performed = 0
        
        while time.time() - start_time < duration:
            success, response = self._make_request(session, 'GET', url)
            
            if success and isinstance(response, dict) and 'items' in response:
                items = response.get('items', [])
                
                # Randomly interact with some posts
                for item in items[:5]:  # Look at first 5 posts
                    if random.random() < self.config.get('activity_settings', {}).get('like_probability', 0.3):
                        media_id = item.get('id')
                        if media_id and self.like_post(session, media_id):
                            actions_performed += 1
                            time.sleep(random.uniform(3, 8))  # Random delay between actions
                
                # Log browsing activity
                self.session_manager.log_activity(session, 'feed_browsing', '', True)
                
                # Random delay before next page
                time.sleep(random.uniform(10, 30))
            else:
                break
        
        self.session_manager.update_session_usage(session)
        return actions_performed > 0
    
    def browse_explore(self, session: Dict[str, Any], duration: int = 60) -> bool:
        """Browse the explore page for specified duration"""
        url = "https://www.instagram.com/api/v1/discover/explore/"
        
        start_time = time.time()
        actions_performed = 0
        
        while time.time() - start_time < duration:
            success, response = self._make_request(session, 'GET', url)
            
            if success and isinstance(response, dict):
                # Log browsing activity
                self.session_manager.log_activity(session, 'explore_browsing', '', True)
                actions_performed += 1
                
                # Random delay
                time.sleep(random.uniform(15, 45))
            else:
                break
        
        self.session_manager.update_session_usage(session)
        return actions_performed > 0
    
    def browse_reels(self, session: Dict[str, Any], duration: int = 60) -> bool:
        """Browse reels for specified duration"""
        url = "https://www.instagram.com/api/v1/clips/discover/"
        
        start_time = time.time()
        actions_performed = 0
        
        while time.time() - start_time < duration:
            success, response = self._make_request(session, 'GET', url)
            
            if success and isinstance(response, dict):
                # Log browsing activity
                self.session_manager.log_activity(session, 'reels_browsing', '', True)
                actions_performed += 1
                
                # Random delay
                time.sleep(random.uniform(20, 60))
            else:
                break
        
        self.session_manager.update_session_usage(session)
        return actions_performed > 0
    
    def random_browsing_session(self, session: Dict[str, Any]) -> Dict[str, Any]:
        """Perform a random browsing session"""
        browsing_config = self.config.get('browsing_settings', {})
        
        activities = []
        total_time = 0
        
        # Define possible activities with their probabilities
        possible_activities = [
            ('feed', browsing_config.get('feed_probability', 0.8), self.browse_feed),
            ('explore', browsing_config.get('explore_probability', 0.6), self.browse_explore),
            ('reels', browsing_config.get('reels_probability', 0.7), self.browse_reels),
        ]
        
        # Select activities to perform
        selected_activities = [
            (name, func) for name, prob, func in possible_activities 
            if random.random() < prob
        ]
        
        if not selected_activities:
            selected_activities = [('feed', self.browse_feed)]  # Default to feed browsing
        
        # Perform selected activities
        for activity_name, activity_func in selected_activities:
            browse_time = random.randint(
                browsing_config.get('min_browse_time', 30),
                browsing_config.get('max_browse_time', 180)
            )
            
            success = activity_func(session, browse_time)
            activities.append({
                'activity': activity_name,
                'duration': browse_time,
                'success': success
            })
            total_time += browse_time
            
            # Random break between activities
            if len(activities) < len(selected_activities):
                break_time = random.randint(10, 30)
                time.sleep(break_time)
                total_time += break_time
        
        return {
            'session_id': session.get('session_key', ''),
            'username': session.get('user', ''),
            'activities': activities,
            'total_duration': total_time,
            'timestamp': datetime.now().isoformat()
        }
    
    def wait_random_duration(self, min_seconds: int = 30, max_seconds: int = 300) -> None:
        """Wait for a random duration to simulate human behavior"""
        wait_time = random.randint(min_seconds, max_seconds)
        time.sleep(wait_time)
    
    def get_random_delay(self) -> float:
        """Get random delay between actions"""
        timing_settings = self.config.get('timing_settings', {})
        min_delay = timing_settings.get('min_action_delay', 10)
        max_delay = timing_settings.get('max_action_delay', 30)
        return random.uniform(min_delay, max_delay)


if __name__ == "__main__":
    # Test the activity manager
    manager = InstagramActivityManager()
    session_manager = manager.session_manager
    
    # Get a random session
    session = session_manager.get_random_session()
    if session:
        print(f"Testing with session: {session.get('user', 'unknown')}")
        
        # Perform a random browsing session
        result = manager.random_browsing_session(session)
        print(f"Browsing session result: {result}")
    else:
        print("No active sessions available for testing")