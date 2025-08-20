"""
Instagram Activity Module - Core functionality for automated Instagram activities
"""
import os
import json
import time
import random
import logging
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Paths
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ACTIVITY_LOGS_PATH = os.path.join(os.path.dirname(__file__), "data", "activity_logs.json")
TARGETS_PATH = os.path.join(os.path.dirname(__file__), "data", "targets.json")
ACTIVITY_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "data", "activity_config.json")
SESSIONS_PATH = os.path.join(BASE_DIR, "sessions.json")

# Instagram API endpoints
INSTAGRAM_API_BASE = "https://i.instagram.com/api/v1"

def get_active_sessions() -> List[Dict[str, Any]]:
    """Get active sessions from sessions.json"""
    try:
        if os.path.exists(SESSIONS_PATH):
            with open(SESSIONS_PATH, 'r') as f:
                sessions = json.load(f)
                return [s for s in sessions if s.get("status") == "active"]
    except Exception as e:
        logger.error(f"Error loading sessions: {e}")
    return []

def make_instagram_request(url: str, method: str = "GET", data: Optional[Dict] = None) -> Optional[requests.Response]:
    """Make Instagram API request using available sessions"""
    sessions = get_active_sessions()
    if not sessions:
        logger.error("No active sessions available")
        return None
    
    # Use first available session
    session = sessions[0]
    cookies = {
        "sessionid": session.get("sessionid", ""),
        "ds_user_id": session.get("ds_user_id", ""),
        "csrftoken": session.get("csrftoken", "")
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "X-Requested-With": "XMLHttpRequest",
        "X-CSRFToken": session.get("csrftoken", ""),
        "X-Instagram-AJAX": "1",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
    }
    
    try:
        if method.upper() == "POST":
            response = requests.post(url, headers=headers, cookies=cookies, data=data, timeout=15)
        else:
            response = requests.get(url, headers=headers, cookies=cookies, params=data, timeout=15)
        
        return response
    except Exception as e:
        logger.error(f"Request failed: {e}")
        return None

class InstagramActivityManager:
    """Manages Instagram automated activities"""
    
    def __init__(self):
        self.config = self._load_config()
        self.ensure_data_files()
    
    def ensure_data_files(self):
        """Ensure all required data files exist"""
        os.makedirs(os.path.dirname(ACTIVITY_LOGS_PATH), exist_ok=True)
        
        # Initialize empty files if they don't exist
        for path, default_data in [
            (ACTIVITY_LOGS_PATH, []),
            (TARGETS_PATH, {"hashtags": [], "accounts": []}),
            (ACTIVITY_CONFIG_PATH, {
                "like_delay_min": 30,
                "like_delay_max": 120,
                "follow_delay_min": 60,
                "follow_delay_max": 300,
                "daily_like_limit": 500,
                "daily_follow_limit": 200,
                "session_keep_alive_interval": 1800,  # 30 minutes
                "enabled": False
            })
        ]:
            if not os.path.exists(path):
                with open(path, 'w') as f:
                    json.dump(default_data, f, indent=2)
    
    def _load_config(self) -> Dict[str, Any]:
        """Load activity configuration"""
        try:
            if os.path.exists(ACTIVITY_CONFIG_PATH):
                with open(ACTIVITY_CONFIG_PATH, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Error loading config: {e}")
        
        # Return default config
        return {
            "like_delay_min": 30,
            "like_delay_max": 120,
            "follow_delay_min": 60,
            "follow_delay_max": 300,
            "daily_like_limit": 500,
            "daily_follow_limit": 200,
            "session_keep_alive_interval": 1800,
            "enabled": False
        }
    
    def save_config(self, config: Dict[str, Any]):
        """Save activity configuration"""
        try:
            with open(ACTIVITY_CONFIG_PATH, 'w') as f:
                json.dump(config, f, indent=2)
            self.config = config
        except Exception as e:
            logger.error(f"Error saving config: {e}")
    
    def log_activity(self, session_user: str, activity_type: str, target: str, 
                    success: bool, details: str = ""):
        """Log an activity"""
        try:
            logs = []
            if os.path.exists(ACTIVITY_LOGS_PATH):
                with open(ACTIVITY_LOGS_PATH, 'r') as f:
                    logs = json.load(f)
            
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "session_user": session_user,
                "activity_type": activity_type,
                "target": target,
                "success": success,
                "details": details
            }
            
            logs.append(log_entry)
            
            # Keep only last 1000 logs to prevent file from growing too large
            if len(logs) > 1000:
                logs = logs[-1000:]
            
            with open(ACTIVITY_LOGS_PATH, 'w') as f:
                json.dump(logs, f, indent=2)
                
        except Exception as e:
            logger.error(f"Error logging activity: {e}")
    
    def get_recent_logs(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent activity logs"""
        try:
            if os.path.exists(ACTIVITY_LOGS_PATH):
                with open(ACTIVITY_LOGS_PATH, 'r') as f:
                    logs = json.load(f)
                    return logs[-limit:] if logs else []
        except Exception as e:
            logger.error(f"Error getting logs: {e}")
        return []
    
    def smart_delay(self, min_seconds: int, max_seconds: int):
        """Add smart delay with human-like variation"""
        delay = random.randint(min_seconds, max_seconds)
        # Add some randomness to make it more human-like
        delay += random.uniform(-0.3, 0.3) * delay
        time.sleep(max(1, delay))
    
    def like_posts_by_hashtag(self, hashtag: str, limit: int = 10) -> Dict[str, Any]:
        """Like posts from a specific hashtag"""
        if not self.config.get("enabled", False):
            return {"success": False, "error": "Activity system is disabled"}
        
        try:
            # Get posts from hashtag
            posts = self._get_hashtag_posts(hashtag, limit)
            if not posts:
                return {"success": False, "error": "No posts found for hashtag"}
            
            liked_count = 0
            errors = []
            
            for post in posts:
                try:
                    # Like the post
                    if self._like_post(post['id']):
                        liked_count += 1
                        self.log_activity("system", "like", f"#{hashtag}", True, 
                                        f"Liked post {post['id']}")
                    else:
                        errors.append(f"Failed to like post {post['id']}")
                    
                    # Smart delay between likes
                    self.smart_delay(
                        self.config.get("like_delay_min", 30),
                        self.config.get("like_delay_max", 120)
                    )
                    
                except Exception as e:
                    errors.append(str(e))
                    continue
            
            return {
                "success": True,
                "liked_count": liked_count,
                "total_posts": len(posts),
                "errors": errors
            }
            
        except Exception as e:
            logger.error(f"Error liking posts by hashtag: {e}")
            return {"success": False, "error": str(e)}
    
    def _get_hashtag_posts(self, hashtag: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get posts from a hashtag"""
        try:
            # Use Instagram hashtag feed API
            url = f"{INSTAGRAM_API_BASE}/tags/{hashtag}/sections/"
            params = {"tab": "recent", "count": limit}
            
            response = make_instagram_request(url, "GET", params)
            if response and response.status_code == 200:
                data = response.json()
                posts = []
                
                # Extract posts from response
                sections = data.get("sections", [])
                for section in sections:
                    layout_content = section.get("layout_content", {})
                    medias = layout_content.get("medias", [])
                    for media_item in medias:
                        media = media_item.get("media", {})
                        if media:
                            posts.append({
                                "id": media.get("id"),
                                "code": media.get("code"),
                                "user": media.get("user", {}).get("username", ""),
                                "like_count": media.get("like_count", 0)
                            })
                
                return posts[:limit]
                
        except Exception as e:
            logger.error(f"Error getting hashtag posts: {e}")
        
        return []
    
    def _like_post(self, media_id: str) -> bool:
        """Like a specific post"""
        try:
            url = f"{INSTAGRAM_API_BASE}/media/{media_id}/like/"
            response = make_instagram_request(url, "POST", {})
            return response and response.status_code == 200
        except Exception as e:
            logger.error(f"Error liking post {media_id}: {e}")
            return False
    
    def follow_user(self, username: str) -> bool:
        """Follow a specific user"""
        if not self.config.get("enabled", False):
            return False
        
        try:
            # Get user ID first
            user_id = self._get_user_id(username)
            if not user_id:
                return False
            
            url = f"{INSTAGRAM_API_BASE}/friendships/create/{user_id}/"
            response = make_instagram_request(url, "POST", {})
            
            success = response and response.status_code == 200
            self.log_activity("system", "follow", username, success,
                            f"Follow attempt for user {username}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error following user {username}: {e}")
            return False
    
    def _get_user_id(self, username: str) -> Optional[str]:
        """Get user ID from username"""
        try:
            url = f"{INSTAGRAM_API_BASE}/users/web_profile_info/"
            params = {"username": username}
            
            response = make_instagram_request(url, "GET", params)
            if response and response.status_code == 200:
                data = response.json()
                return data.get("data", {}).get("user", {}).get("id")
                
        except Exception as e:
            logger.error(f"Error getting user ID for {username}: {e}")
        
        return None
    
    def keep_sessions_alive(self) -> Dict[str, Any]:
        """Keep all sessions alive by performing light activities"""
        results = {
            "sessions_checked": 0,
            "sessions_activated": 0,
            "errors": []
        }
        
        try:
            # Get all available sessions
            sessions = get_active_sessions()
            results["sessions_checked"] = len(sessions)
            
            for session in sessions:
                try:
                    # Perform a light activity to keep session alive
                    if self._perform_keep_alive_activity(session):
                        results["sessions_activated"] += 1
                        self.log_activity(session.get("user", "unknown"), 
                                        "keep_alive", "session", True,
                                        "Session keep-alive successful")
                    
                    # Small delay between session activities
                    time.sleep(random.uniform(2, 5))
                    
                except Exception as e:
                    results["errors"].append(f"Session {session.get('user', 'unknown')}: {str(e)}")
                    continue
            
            return results
            
        except Exception as e:
            logger.error(f"Error keeping sessions alive: {e}")
            results["errors"].append(str(e))
            return results
    
    def _perform_keep_alive_activity(self, session: Dict[str, Any]) -> bool:
        """Perform a light activity to keep a session alive"""
        try:
            # Just check current user info - light API call
            url = f"{INSTAGRAM_API_BASE}/accounts/current_user/"
            response = make_instagram_request(url, "GET")
            return response and response.status_code == 200
        except Exception as e:
            logger.error(f"Keep alive activity failed: {e}")
            return False
    
    def get_activity_stats(self) -> Dict[str, Any]:
        """Get activity statistics"""
        try:
            logs = self.get_recent_logs(1000)  # Get more logs for stats
            
            stats = {
                "total_activities": len(logs),
                "likes_today": 0,
                "follows_today": 0,
                "success_rate": 0,
                "last_activity": None
            }
            
            if not logs:
                return stats
            
            today = datetime.now().date()
            successful_activities = 0
            
            for log in logs:
                try:
                    log_date = datetime.fromisoformat(log["timestamp"]).date()
                    
                    if log_date == today:
                        if log["activity_type"] == "like":
                            stats["likes_today"] += 1
                        elif log["activity_type"] == "follow":
                            stats["follows_today"] += 1
                    
                    if log["success"]:
                        successful_activities += 1
                        
                except Exception:
                    continue
            
            if logs:
                stats["success_rate"] = round((successful_activities / len(logs)) * 100, 1)
                stats["last_activity"] = logs[-1]["timestamp"]
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting activity stats: {e}")
            return {
                "total_activities": 0,
                "likes_today": 0,
                "follows_today": 0,
                "success_rate": 0,
                "last_activity": None
            }
    
    def get_targets(self) -> Dict[str, List[str]]:
        """Get current targets configuration"""
        try:
            if os.path.exists(TARGETS_PATH):
                with open(TARGETS_PATH, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Error loading targets: {e}")
        
        return {"hashtags": [], "accounts": []}
    
    def save_targets(self, targets: Dict[str, List[str]]):
        """Save targets configuration"""
        try:
            with open(TARGETS_PATH, 'w') as f:
                json.dump(targets, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving targets: {e}")


# Global instance
activity_manager = InstagramActivityManager()