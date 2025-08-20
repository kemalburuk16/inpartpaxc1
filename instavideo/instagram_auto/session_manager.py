#!/usr/bin/env python3
"""
Instagram Automation Session Manager
Manages Instagram sessions for automation activities
"""

import json
import os
import time
import random
from datetime import datetime
from typing import List, Dict, Optional, Any
from pathlib import Path

class AutoSessionManager:
    """Manages Instagram sessions for automation"""
    
    def __init__(self, sessions_file="sessions.json", config_file="config.json"):
        self.base_dir = Path(__file__).parent.parent.parent  # Go to project root
        self.sessions_file = self.base_dir / sessions_file
        self.config_file = Path(__file__).parent / config_file
        self.activity_log_file = Path(__file__).parent / "activity_log.json"
        self.config = self.load_config()
        
    def load_config(self) -> Dict[str, Any]:
        """Load configuration from config.json"""
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            return self._default_config()
    
    def _default_config(self) -> Dict[str, Any]:
        """Return default configuration if config file not found"""
        return {
            "daily_limits": {"max_likes_per_day": 500, "max_follows_per_day": 100},
            "session_limits": {"max_likes_per_session": 50, "max_follows_per_session": 10},
            "timing_settings": {"min_action_delay": 10, "max_action_delay": 30}
        }
    
    def load_sessions(self) -> List[Dict[str, Any]]:
        """Load all sessions from sessions.json"""
        try:
            with open(self.sessions_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            return []
    
    def save_sessions(self, sessions: List[Dict[str, Any]]) -> None:
        """Save sessions back to sessions.json"""
        with open(self.sessions_file, 'w', encoding='utf-8') as f:
            json.dump(sessions, f, indent=2, ensure_ascii=False)
    
    def get_active_sessions(self) -> List[Dict[str, Any]]:
        """Get all active sessions available for automation"""
        sessions = self.load_sessions()
        active_sessions = []
        
        for session in sessions:
            if session.get('status') == 'active' and not session.get('blocked', False):
                # Check if session hasn't exceeded daily limits
                if self._check_daily_limits(session):
                    active_sessions.append(session)
        
        return active_sessions
    
    def get_random_session(self) -> Optional[Dict[str, Any]]:
        """Get a random active session for automation"""
        active_sessions = self.get_active_sessions()
        if not active_sessions:
            return None
        return random.choice(active_sessions)
    
    def _check_daily_limits(self, session: Dict[str, Any]) -> bool:
        """Check if session hasn't exceeded daily limits"""
        session_id = session.get('session_key', session.get('sessionid', ''))
        today = datetime.now().strftime('%Y-%m-%d')
        
        activity_log = self.load_activity_log()
        daily_activities = activity_log.get(today, {}).get(session_id, {})
        
        limits = self.config.get('daily_limits', {})
        
        # Check each activity type against limits
        for activity_type, limit in limits.items():
            activity_name = activity_type.replace('max_', '').replace('_per_day', '')
            current_count = daily_activities.get(activity_name, 0)
            if current_count >= limit:
                return False
        
        return True
    
    def load_activity_log(self) -> Dict[str, Any]:
        """Load activity log from file"""
        try:
            with open(self.activity_log_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
    
    def save_activity_log(self, activity_log: Dict[str, Any]) -> None:
        """Save activity log to file"""
        with open(self.activity_log_file, 'w', encoding='utf-8') as f:
            json.dump(activity_log, f, indent=2, ensure_ascii=False)
    
    def log_activity(self, session: Dict[str, Any], activity_type: str, target: str = "", success: bool = True) -> None:
        """Log an automation activity"""
        session_id = session.get('session_key', session.get('sessionid', ''))
        today = datetime.now().strftime('%Y-%m-%d')
        timestamp = datetime.now().isoformat()
        
        activity_log = self.load_activity_log()
        
        # Initialize structures if needed
        if today not in activity_log:
            activity_log[today] = {}
        if session_id not in activity_log[today]:
            activity_log[today][session_id] = {}
        if activity_type not in activity_log[today][session_id]:
            activity_log[today][session_id][activity_type] = 0
        
        # Log the activity
        if success:
            activity_log[today][session_id][activity_type] += 1
        
        # Also log detailed activity
        if 'detailed_log' not in activity_log:
            activity_log['detailed_log'] = []
        
        activity_log['detailed_log'].append({
            'timestamp': timestamp,
            'session_id': session_id,
            'username': session.get('user', ''),
            'activity_type': activity_type,
            'target': target,
            'success': success
        })
        
        # Keep only last 1000 detailed logs
        activity_log['detailed_log'] = activity_log['detailed_log'][-1000:]
        
        self.save_activity_log(activity_log)
    
    def update_session_usage(self, session: Dict[str, Any]) -> None:
        """Update session last used time"""
        sessions = self.load_sessions()
        session_key = session.get('session_key')
        
        for i, sess in enumerate(sessions):
            if sess.get('session_key') == session_key:
                sessions[i]['last_used'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                break
        
        self.save_sessions(sessions)
    
    def mark_session_blocked(self, session: Dict[str, Any], duration_minutes: int = 30) -> None:
        """Mark a session as temporarily blocked"""
        sessions = self.load_sessions()
        session_key = session.get('session_key')
        
        from datetime import timedelta
        unblock_time = datetime.now() + timedelta(minutes=duration_minutes)
        
        for i, sess in enumerate(sessions):
            if sess.get('session_key') == session_key:
                sessions[i]['blocked'] = True
                sessions[i]['unblock_at'] = unblock_time.strftime("%Y-%m-%d %H:%M:%S")
                sessions[i]['fail_count'] = sess.get('fail_count', 0) + 1
                break
        
        self.save_sessions(sessions)
    
    def get_session_stats(self) -> Dict[str, Any]:
        """Get statistics about sessions and activities"""
        sessions = self.load_sessions()
        activity_log = self.load_activity_log()
        today = datetime.now().strftime('%Y-%m-%d')
        
        stats = {
            'total_sessions': len(sessions),
            'active_sessions': len([s for s in sessions if s.get('status') == 'active']),
            'blocked_sessions': len([s for s in sessions if s.get('blocked', False)]),
            'today_activities': {}
        }
        
        # Calculate today's activities
        if today in activity_log:
            total_activities = {}
            for session_id, activities in activity_log[today].items():
                for activity_type, count in activities.items():
                    if activity_type not in total_activities:
                        total_activities[activity_type] = 0
                    total_activities[activity_type] += count
            stats['today_activities'] = total_activities
        
        return stats
    
    def cleanup_old_logs(self, days_to_keep: int = 30) -> None:
        """Clean up old activity logs"""
        activity_log = self.load_activity_log()
        today = datetime.now()
        
        # Remove old daily logs
        dates_to_remove = []
        for date_str in activity_log.keys():
            if date_str == 'detailed_log':
                continue
            try:
                log_date = datetime.strptime(date_str, '%Y-%m-%d')
                if (today - log_date).days > days_to_keep:
                    dates_to_remove.append(date_str)
            except ValueError:
                continue
        
        for date_str in dates_to_remove:
            del activity_log[date_str]
        
        self.save_activity_log(activity_log)


if __name__ == "__main__":
    # Test the session manager
    manager = AutoSessionManager()
    active_sessions = manager.get_active_sessions()
    print(f"Found {len(active_sessions)} active sessions")
    
    stats = manager.get_session_stats()
    print("Session stats:", stats)