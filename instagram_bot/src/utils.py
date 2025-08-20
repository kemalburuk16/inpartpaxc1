import json
import logging
import os
import random
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any


def load_config(config_path: str = "config/settings.json") -> Dict[str, Any]:
    """Load configuration from JSON file."""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Failed to load config: {e}")
        return {}


def save_config(config: Dict[str, Any], config_path: str = "config/settings.json") -> bool:
    """Save configuration to JSON file."""
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logging.error(f"Failed to save config: {e}")
        return False


def get_random_delay(min_delay: int, max_delay: int) -> int:
    """Get a random delay between min and max seconds."""
    return random.randint(min_delay, max_delay)


def is_within_limits(action_type: str, daily_count: int, hourly_count: int, config: Dict[str, Any]) -> bool:
    """Check if action is within daily and hourly limits."""
    daily_limits = config.get('daily_limits', {})
    hourly_limits = config.get('hourly_limits', {})
    
    daily_limit = daily_limits.get(action_type, 0)
    hourly_limit = hourly_limits.get(action_type, 0)
    
    if daily_limit > 0 and daily_count >= daily_limit:
        return False
    if hourly_limit > 0 and hourly_count >= hourly_limit:
        return False
    
    return True


def is_user_blacklisted(username: str, config: Dict[str, Any]) -> bool:
    """Check if user is in blacklist."""
    blacklisted_users = config.get('blacklisted_users', [])
    return username.lower() in [user.lower() for user in blacklisted_users]


def is_hashtag_blacklisted(hashtag: str, config: Dict[str, Any]) -> bool:
    """Check if hashtag is in blacklist."""
    blacklisted_hashtags = config.get('blacklisted_hashtags', [])
    return hashtag.lower() in [tag.lower() for tag in blacklisted_hashtags]


def setup_logging(log_dir: str = "logs") -> logging.Logger:
    """Setup logging configuration."""
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    log_filename = os.path.join(log_dir, f"instagram_bot_{datetime.now().strftime('%Y%m%d')}.log")
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_filename, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    
    return logging.getLogger('instagram_bot')


def get_current_hour_stats(action_type: str, log_dir: str = "logs") -> int:
    """Get count of actions performed in current hour."""
    current_hour = datetime.now().strftime('%Y%m%d_%H')
    stats_file = os.path.join(log_dir, f"stats_{current_hour}.json")
    
    if not os.path.exists(stats_file):
        return 0
    
    try:
        with open(stats_file, 'r') as f:
            stats = json.load(f)
        return stats.get(action_type, 0)
    except:
        return 0


def get_daily_stats(action_type: str, log_dir: str = "logs") -> int:
    """Get count of actions performed today."""
    today = datetime.now().strftime('%Y%m%d')
    stats_file = os.path.join(log_dir, f"daily_stats_{today}.json")
    
    if not os.path.exists(stats_file):
        return 0
    
    try:
        with open(stats_file, 'r') as f:
            stats = json.load(f)
        return stats.get(action_type, 0)
    except:
        return 0


def update_stats(action_type: str, log_dir: str = "logs") -> None:
    """Update action statistics."""
    current_hour = datetime.now().strftime('%Y%m%d_%H')
    today = datetime.now().strftime('%Y%m%d')
    
    # Update hourly stats
    hourly_file = os.path.join(log_dir, f"stats_{current_hour}.json")
    hourly_stats = {}
    if os.path.exists(hourly_file):
        try:
            with open(hourly_file, 'r') as f:
                hourly_stats = json.load(f)
        except:
            hourly_stats = {}
    
    hourly_stats[action_type] = hourly_stats.get(action_type, 0) + 1
    
    try:
        with open(hourly_file, 'w') as f:
            json.dump(hourly_stats, f)
    except:
        pass
    
    # Update daily stats
    daily_file = os.path.join(log_dir, f"daily_stats_{today}.json")
    daily_stats = {}
    if os.path.exists(daily_file):
        try:
            with open(daily_file, 'r') as f:
                daily_stats = json.load(f)
        except:
            daily_stats = {}
    
    daily_stats[action_type] = daily_stats.get(action_type, 0) + 1
    
    try:
        with open(daily_file, 'w') as f:
            json.dump(daily_stats, f)
    except:
        pass


def clean_old_logs(log_dir: str = "logs", days_to_keep: int = 30) -> None:
    """Clean old log files to save space."""
    if not os.path.exists(log_dir):
        return
    
    cutoff_date = datetime.now() - timedelta(days=days_to_keep)
    
    for filename in os.listdir(log_dir):
        filepath = os.path.join(log_dir, filename)
        if os.path.isfile(filepath):
            file_time = datetime.fromtimestamp(os.path.getctime(filepath))
            if file_time < cutoff_date:
                try:
                    os.remove(filepath)
                    logging.info(f"Removed old log file: {filename}")
                except:
                    pass


def validate_session_data(session_data: Dict[str, Any]) -> bool:
    """Validate if session data contains required fields."""
    required_fields = ['sessionid', 'ds_user_id', 'csrftoken']
    return all(field in session_data and session_data[field] for field in required_fields)


def format_username(username: str) -> str:
    """Format username by removing @ symbol if present."""
    return username.lstrip('@').strip()


def extract_hashtags_from_text(text: str) -> List[str]:
    """Extract hashtags from text."""
    import re
    hashtag_pattern = r'#(\w+)'
    hashtags = re.findall(hashtag_pattern, text)
    return [tag.lower() for tag in hashtags]


def is_business_hours() -> bool:
    """Check if current time is within business hours (9 AM - 10 PM)."""
    current_hour = datetime.now().hour
    return 9 <= current_hour <= 22


def calculate_engagement_rate(likes: int, comments: int, followers: int) -> float:
    """Calculate engagement rate percentage."""
    if followers == 0:
        return 0.0
    engagement = likes + comments
    return (engagement / followers) * 100


def is_suspicious_activity(action_count: int, time_window_minutes: int, max_actions: int) -> bool:
    """Check if activity pattern looks suspicious."""
    actions_per_minute = action_count / time_window_minutes if time_window_minutes > 0 else 0
    max_per_minute = max_actions / 60
    return actions_per_minute > max_per_minute