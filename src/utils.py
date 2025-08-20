#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Utility functions for Instagram automation system
"""

import os
import json
import logging
import logging.handlers
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import random
import string

# Global logger setup
logger = logging.getLogger(__name__)


def setup_logging(config: Dict[str, Any]) -> logging.Logger:
    """
    Set up logging configuration based on config settings
    Returns configured logger
    """
    log_config = config.get('logging', {})
    
    # Create logs directory if it doesn't exist
    log_file = log_config.get('file', 'logs/instagram_automation.log')
    log_dir = os.path.dirname(log_file)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
    
    # Set logging level
    level = getattr(logging, log_config.get('level', 'INFO').upper())
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create and configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # Clear existing handlers
    root_logger.handlers.clear()
    
    # File handler with rotation
    max_bytes = log_config.get('max_file_size_mb', 10) * 1024 * 1024
    backup_count = log_config.get('backup_count', 5)
    
    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=max_bytes, backupCount=backup_count
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    
    # Console handler (optional)
    if log_config.get('console_output', True):
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
    
    logger.info("Logging configured successfully")
    return root_logger


def load_config(config_path: str = "config/settings.json") -> Dict[str, Any]:
    """
    Load configuration from JSON file
    Returns configuration dictionary
    """
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        logger.info(f"Configuration loaded from {config_path}")
        return config
        
    except FileNotFoundError:
        logger.error(f"Configuration file not found: {config_path}")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in configuration file: {e}")
        raise
    except Exception as e:
        logger.error(f"Error loading configuration: {e}")
        raise


def save_config(config: Dict[str, Any], config_path: str = "config/settings.json") -> bool:
    """
    Save configuration to JSON file
    Returns True if successful
    """
    try:
        # Create directory if it doesn't exist
        config_dir = os.path.dirname(config_path)
        if config_dir:
            os.makedirs(config_dir, exist_ok=True)
        
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Configuration saved to {config_path}")
        return True
        
    except Exception as e:
        logger.error(f"Error saving configuration: {e}")
        return False


def save_action_log(action_type: str, log_entry: Dict[str, Any]) -> bool:
    """
    Save action log entry to JSON file
    action_type: 'likes', 'follows', 'unfollows', etc.
    Returns True if successful
    """
    try:
        # Create logs directory if it doesn't exist
        logs_dir = "logs"
        os.makedirs(logs_dir, exist_ok=True)
        
        log_file = os.path.join(logs_dir, f"{action_type}.json")
        
        # Load existing logs or create new list
        if os.path.exists(log_file):
            with open(log_file, 'r', encoding='utf-8') as f:
                logs = json.load(f)
        else:
            logs = []
        
        # Add new entry
        logs.append(log_entry)
        
        # Keep only recent entries (last 1000 to prevent file from growing too large)
        if len(logs) > 1000:
            logs = logs[-1000:]
        
        # Save back to file
        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump(logs, f, indent=2, ensure_ascii=False)
        
        return True
        
    except Exception as e:
        logger.error(f"Error saving action log: {e}")
        return False


def load_action_log(action_type: str) -> List[Dict[str, Any]]:
    """
    Load action log from JSON file
    action_type: 'likes', 'follows', 'unfollows', etc.
    Returns list of log entries
    """
    try:
        log_file = os.path.join("logs", f"{action_type}.json")
        
        if not os.path.exists(log_file):
            return []
        
        with open(log_file, 'r', encoding='utf-8') as f:
            logs = json.load(f)
        
        return logs if isinstance(logs, list) else []
        
    except Exception as e:
        logger.error(f"Error loading action log: {e}")
        return []


def generate_session_id() -> str:
    """Generate a random session ID"""
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))


def format_number(num: int) -> str:
    """Format number with appropriate suffixes (K, M, etc.)"""
    if num >= 1000000:
        return f"{num/1000000:.1f}M"
    elif num >= 1000:
        return f"{num/1000:.1f}K"
    else:
        return str(num)


def validate_config(config: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate configuration structure and values
    Returns (is_valid, list_of_errors)
    """
    errors = []
    
    # Check required sections
    required_sections = ['instagram', 'logging', 'session']
    for section in required_sections:
        if section not in config:
            errors.append(f"Missing required section: {section}")
    
    # Validate Instagram config
    if 'instagram' in config:
        instagram_config = config['instagram']
        
        # Check rate limits
        if 'rate_limits' in instagram_config:
            rate_limits = instagram_config['rate_limits']
            
            # Validate numeric values
            numeric_fields = [
                'likes_per_hour', 'follows_per_hour', 'requests_per_minute',
                'min_delay_seconds', 'max_delay_seconds'
            ]
            
            for field in numeric_fields:
                if field in rate_limits:
                    if not isinstance(rate_limits[field], (int, float)) or rate_limits[field] < 0:
                        errors.append(f"Invalid rate_limits.{field}: must be a positive number")
            
            # Check delay logic
            min_delay = rate_limits.get('min_delay_seconds', 0)
            max_delay = rate_limits.get('max_delay_seconds', 0)
            if max_delay < min_delay:
                errors.append("max_delay_seconds must be greater than min_delay_seconds")
        
        # Check hashtags config
        if 'hashtags' in instagram_config:
            hashtags = instagram_config['hashtags']
            if 'target_tags' in hashtags:
                if not isinstance(hashtags['target_tags'], list):
                    errors.append("hashtags.target_tags must be a list")
    
    # Validate logging config
    if 'logging' in config:
        logging_config = config['logging']
        
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if 'level' in logging_config:
            if logging_config['level'] not in valid_levels:
                errors.append(f"Invalid logging level: {logging_config['level']}")
    
    return len(errors) == 0, errors


def create_default_config() -> Dict[str, Any]:
    """Create a default configuration dictionary"""
    return {
        "instagram": {
            "rate_limits": {
                "likes_per_hour": 60,
                "follows_per_hour": 30,
                "requests_per_minute": 20,
                "min_delay_seconds": 10,
                "max_delay_seconds": 30
            },
            "safety": {
                "max_consecutive_errors": 3,
                "cooldown_after_error_minutes": 15,
                "respect_instagram_limits": True,
                "random_delays": True
            },
            "hashtags": {
                "target_tags": [
                    "photography",
                    "art",
                    "nature"
                ],
                "posts_per_tag": 10,
                "like_probability": 0.8,
                "min_likes_threshold": 1,
                "max_likes_threshold": 10000,
                "max_post_age_hours": 72,
                "spam_keywords": [
                    "follow for follow",
                    "f4f",
                    "l4l",
                    "like for like",
                    "dm me",
                    "check my bio"
                ]
            },
            "following": {
                "target_users": [],
                "follow_followers_of": [],
                "max_follows_per_user": 50,
                "follow_probability": 0.6,
                "min_followers": 50,
                "max_followers": 50000,
                "max_following_ratio": 2.0,
                "min_posts": 3,
                "spam_keywords": [
                    "follow for follow",
                    "f4f",
                    "dm for promotion",
                    "buy followers"
                ]
            }
        },
        "logging": {
            "level": "INFO",
            "file": "logs/instagram_automation.log",
            "max_file_size_mb": 10,
            "backup_count": 5,
            "console_output": True
        },
        "session": {
            "use_existing_sessions": True,
            "session_rotation": True,
            "session_health_check": True
        }
    }


def get_summary_stats(config: Dict[str, Any]) -> Dict[str, Any]:
    """Get summary statistics from action logs"""
    stats = {
        'likes': {'total': 0, 'today': 0, 'successful': 0},
        'follows': {'total': 0, 'today': 0, 'successful': 0},
        'last_activity': None
    }
    
    today = datetime.now().date()
    
    # Analyze likes
    likes_log = load_action_log('likes')
    for entry in likes_log:
        stats['likes']['total'] += 1
        if entry.get('success', False):
            stats['likes']['successful'] += 1
        
        try:
            entry_date = datetime.fromisoformat(entry.get('timestamp', '')).date()
            if entry_date == today:
                stats['likes']['today'] += 1
        except:
            pass
    
    # Analyze follows
    follows_log = load_action_log('follows')
    for entry in follows_log:
        stats['follows']['total'] += 1
        if entry.get('success', False):
            stats['follows']['successful'] += 1
        
        try:
            entry_date = datetime.fromisoformat(entry.get('timestamp', '')).date()
            if entry_date == today:
                stats['follows']['today'] += 1
        except:
            pass
    
    # Get last activity
    all_logs = likes_log + follows_log
    if all_logs:
        try:
            all_logs.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
            stats['last_activity'] = all_logs[0].get('timestamp')
        except:
            pass
    
    return stats


def clean_old_logs(days_to_keep: int = 30):
    """Clean old log entries to prevent log files from growing too large"""
    from datetime import timedelta
    
    cutoff_date = datetime.now() - timedelta(days=days_to_keep)
    
    for log_type in ['likes', 'follows']:
        try:
            logs = load_action_log(log_type)
            if not logs:
                continue
            
            # Filter out old entries
            filtered_logs = []
            for entry in logs:
                try:
                    entry_date = datetime.fromisoformat(entry.get('timestamp', ''))
                    if entry_date > cutoff_date:
                        filtered_logs.append(entry)
                except:
                    # Keep entries with invalid timestamps
                    filtered_logs.append(entry)
            
            # Save filtered logs
            if len(filtered_logs) != len(logs):
                log_file = os.path.join("logs", f"{log_type}.json")
                with open(log_file, 'w', encoding='utf-8') as f:
                    json.dump(filtered_logs, f, indent=2, ensure_ascii=False)
                
                logger.info(f"Cleaned {log_type} log: {len(logs)} -> {len(filtered_logs)} entries")
        
        except Exception as e:
            logger.error(f"Error cleaning {log_type} log: {e}")


def safe_divide(a: float, b: float, default: float = 0.0) -> float:
    """Safely divide two numbers, returning default if division by zero"""
    try:
        return a / b if b != 0 else default
    except:
        return default