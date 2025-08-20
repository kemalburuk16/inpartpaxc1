import json
import logging
import os
import random
import sys
import time
from typing import Dict, List, Optional, Any, Tuple

# Add parent directory to path to import existing modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

try:
    from session_pool import SessionPool
except ImportError:
    SessionPool = None

import requests
from session_manager import InstagramSessionManager
from utils import setup_logging, get_random_delay


class InstagramClient:
    """
    Instagram API client that handles authentication, requests, and rate limiting.
    Leverages existing session management infrastructure.
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = setup_logging()
        self.session_manager = InstagramSessionManager()
        
        # Use existing session pool if available
        if SessionPool:
            try:
                self.session_pool = SessionPool()
                self.logger.info("Using existing SessionPool for requests")
            except Exception as e:
                self.logger.error(f"Failed to initialize SessionPool: {e}")
                self.session_pool = None
        else:
            self.session_pool = None
        
        self.base_headers = {
            "User-Agent": "Instagram 298.0.0.0.0 Android",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9,tr;q=0.8",
            "X-IG-App-ID": "1217981644879628",
            "X-ASBD-ID": "129477",
            "Accept-Encoding": "gzip, deflate"
        }
        
        self.last_request_time = 0
        self.request_count = 0
    
    def _make_request(self, method: str, url: str, **kwargs) -> Optional[requests.Response]:
        """Make an HTTP request with proper session management and rate limiting."""
        
        # Apply rate limiting
        self._apply_rate_limiting()
        
        if self.session_pool:
            try:
                # Use existing session pool for requests
                if method.lower() == 'get':
                    response = self.session_pool.http_get(url, **kwargs)
                elif method.lower() == 'post':
                    response = self.session_pool.http_post(url, **kwargs)
                else:
                    raise ValueError(f"Unsupported method: {method}")
                
                self.request_count += 1
                return response
                
            except Exception as e:
                self.logger.error(f"SessionPool request failed: {e}")
                # Fall back to manual request handling
        
        # Manual request handling
        session = self.session_manager.get_active_session()
        if not session:
            self.logger.error("No active session available")
            return None
        
        headers = self._build_headers(session, kwargs.get('extra_headers', {}))
        cookies = self._build_cookies(session)
        
        try:
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                cookies=cookies,
                timeout=(10, 30),
                **kwargs
            )
            
            self.request_count += 1
            
            # Handle response status
            if response.status_code == 200:
                self.session_manager.mark_session_success(session)
            elif response.status_code in [401, 403, 419, 429]:
                self.session_manager.mark_session_failure(session, response.status_code)
                self.logger.warning(f"Request failed with status {response.status_code}")
            
            return response
            
        except Exception as e:
            self.logger.error(f"Request failed: {e}")
            self.session_manager.mark_session_failure(session)
            return None
    
    def _apply_rate_limiting(self) -> None:
        """Apply rate limiting between requests."""
        current_time = time.time()
        
        # Minimum delay between requests
        min_delay = self.config.get('delays', {}).get('min_request_delay', 1)
        max_delay = self.config.get('delays', {}).get('max_request_delay', 3)
        
        time_since_last = current_time - self.last_request_time
        if time_since_last < min_delay:
            sleep_time = get_random_delay(min_delay, max_delay)
            self.logger.debug(f"Rate limiting: sleeping for {sleep_time} seconds")
            time.sleep(sleep_time)
        
        self.last_request_time = time.time()
    
    def _build_headers(self, session: Dict[str, Any], extra_headers: Dict[str, str]) -> Dict[str, str]:
        """Build headers for request."""
        headers = self.base_headers.copy()
        
        # Add CSRF token if available
        csrf_token = session.get('csrftoken', '')
        if csrf_token:
            headers['X-CSRFToken'] = csrf_token
        
        headers['Referer'] = 'https://www.instagram.com/'
        headers.update(extra_headers)
        
        return headers
    
    def _build_cookies(self, session: Dict[str, Any]) -> Dict[str, str]:
        """Build cookies for request."""
        cookies = {}
        
        # Essential cookies
        for key in ['sessionid', 'ds_user_id', 'csrftoken']:
            if session.get(key):
                cookies[key] = session[key]
        
        # Additional cookies if available
        session_cookies = session.get('cookies', {})
        cookies.update(session_cookies)
        
        return cookies
    
    def get_user_info(self, username: str) -> Optional[Dict[str, Any]]:
        """Get user information by username."""
        url = f"https://i.instagram.com/api/v1/users/web_profile_info/?username={username}"
        
        response = self._make_request('GET', url)
        if response and response.status_code == 200:
            try:
                data = response.json()
                user_data = data.get('data', {}).get('user', {})
                return user_data
            except json.JSONDecodeError:
                self.logger.error("Failed to parse user info response")
        
        return None
    
    def get_user_feed(self, user_id: str, max_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get user's feed/posts."""
        url = f"https://i.instagram.com/api/v1/users/{user_id}/feed/"
        params = {'count': 12}
        if max_id:
            params['max_id'] = max_id
        
        response = self._make_request('GET', url, params=params)
        if response and response.status_code == 200:
            try:
                return response.json()
            except json.JSONDecodeError:
                self.logger.error("Failed to parse feed response")
        
        return None
    
    def search_hashtag(self, hashtag: str) -> Optional[Dict[str, Any]]:
        """Search for posts by hashtag."""
        url = f"https://i.instagram.com/api/v1/tags/{hashtag}/recent/"
        params = {'count': 12}
        
        response = self._make_request('GET', url, params=params)
        if response and response.status_code == 200:
            try:
                return response.json()
            except json.JSONDecodeError:
                self.logger.error("Failed to parse hashtag search response")
        
        return None
    
    def like_post(self, media_id: str) -> bool:
        """Like a post by media ID."""
        url = f"https://i.instagram.com/api/v1/media/{media_id}/like/"
        
        response = self._make_request('POST', url)
        if response and response.status_code == 200:
            try:
                data = response.json()
                return data.get('status') == 'ok'
            except json.JSONDecodeError:
                self.logger.error("Failed to parse like response")
        
        return False
    
    def unlike_post(self, media_id: str) -> bool:
        """Unlike a post by media ID."""
        url = f"https://i.instagram.com/api/v1/media/{media_id}/unlike/"
        
        response = self._make_request('POST', url)
        if response and response.status_code == 200:
            try:
                data = response.json()
                return data.get('status') == 'ok'
            except json.JSONDecodeError:
                self.logger.error("Failed to parse unlike response")
        
        return False
    
    def follow_user(self, user_id: str) -> bool:
        """Follow a user by user ID."""
        url = f"https://i.instagram.com/api/v1/friendships/create/{user_id}/"
        
        response = self._make_request('POST', url)
        if response and response.status_code == 200:
            try:
                data = response.json()
                return data.get('status') == 'ok'
            except json.JSONDecodeError:
                self.logger.error("Failed to parse follow response")
        
        return False
    
    def unfollow_user(self, user_id: str) -> bool:
        """Unfollow a user by user ID."""
        url = f"https://i.instagram.com/api/v1/friendships/destroy/{user_id}/"
        
        response = self._make_request('POST', url)
        if response and response.status_code == 200:
            try:
                data = response.json()
                return data.get('status') == 'ok'
            except json.JSONDecodeError:
                self.logger.error("Failed to parse unfollow response")
        
        return False
    
    def get_user_followers(self, user_id: str, max_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get user's followers."""
        url = f"https://i.instagram.com/api/v1/friendships/{user_id}/followers/"
        params = {'count': 200}
        if max_id:
            params['max_id'] = max_id
        
        response = self._make_request('GET', url, params=params)
        if response and response.status_code == 200:
            try:
                return response.json()
            except json.JSONDecodeError:
                self.logger.error("Failed to parse followers response")
        
        return None
    
    def get_user_following(self, user_id: str, max_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get users that this user is following."""
        url = f"https://i.instagram.com/api/v1/friendships/{user_id}/following/"
        params = {'count': 200}
        if max_id:
            params['max_id'] = max_id
        
        response = self._make_request('GET', url, params=params)
        if response and response.status_code == 200:
            try:
                return response.json()
            except json.JSONDecodeError:
                self.logger.error("Failed to parse following response")
        
        return None
    
    def check_friendship_status(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Check friendship status with a user."""
        url = f"https://i.instagram.com/api/v1/friendships/show/{user_id}/"
        
        response = self._make_request('GET', url)
        if response and response.status_code == 200:
            try:
                return response.json()
            except json.JSONDecodeError:
                self.logger.error("Failed to parse friendship status response")
        
        return None
    
    def get_media_info(self, media_id: str) -> Optional[Dict[str, Any]]:
        """Get information about a media item."""
        url = f"https://i.instagram.com/api/v1/media/{media_id}/info/"
        
        response = self._make_request('GET', url)
        if response and response.status_code == 200:
            try:
                return response.json()
            except json.JSONDecodeError:
                self.logger.error("Failed to parse media info response")
        
        return None
    
    def get_current_user(self) -> Optional[Dict[str, Any]]:
        """Get current authenticated user information."""
        url = "https://i.instagram.com/api/v1/accounts/current_user/"
        
        response = self._make_request('GET', url)
        if response and response.status_code == 200:
            try:
                return response.json()
            except json.JSONDecodeError:
                self.logger.error("Failed to parse current user response")
        
        return None
    
    def is_session_valid(self) -> bool:
        """Check if current session is still valid."""
        user_info = self.get_current_user()
        return user_info is not None
    
    def get_request_stats(self) -> Dict[str, int]:
        """Get request statistics."""
        return {
            'total_requests': self.request_count,
            'session_stats': self.session_manager.get_session_stats()
        }