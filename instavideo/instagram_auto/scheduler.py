#!/usr/bin/env python3
"""
Instagram Automation Scheduler
Handles automatic scheduling and manual triggering of Instagram activities
"""

import json
import time
import threading
import schedule
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from pathlib import Path

try:
    from .session_manager import AutoSessionManager
    from .activity_manager import InstagramActivityManager
except ImportError:
    from session_manager import AutoSessionManager
    from activity_manager import InstagramActivityManager

class InstagramScheduler:
    """Schedules and manages Instagram automation activities"""
    
    def __init__(self, session_manager: Optional[AutoSessionManager] = None):
        self.session_manager = session_manager or AutoSessionManager()
        self.activity_manager = InstagramActivityManager(self.session_manager)
        self.config = self.session_manager.config
        self.is_running = False
        self.scheduler_thread = None
        self.active_sessions = {}
        self.scheduler_state_file = Path(__file__).parent / "scheduler_state.json"
        
        # Load scheduler state
        self.load_scheduler_state()
    
    def load_scheduler_state(self) -> None:
        """Load scheduler state from file"""
        try:
            with open(self.scheduler_state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
                self.is_running = state.get('is_running', False)
                self.active_sessions = state.get('active_sessions', {})
        except FileNotFoundError:
            self.is_running = False
            self.active_sessions = {}
    
    def save_scheduler_state(self) -> None:
        """Save scheduler state to file"""
        state = {
            'is_running': self.is_running,
            'active_sessions': self.active_sessions,
            'last_updated': datetime.now().isoformat()
        }
        with open(self.scheduler_state_file, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    
    def start_scheduler(self) -> bool:
        """Start the automatic scheduler"""
        if self.is_running:
            return False
        
        self.is_running = True
        self.save_scheduler_state()
        
        # Setup schedule based on config
        scheduler_settings = self.config.get('scheduler_settings', {})
        
        if scheduler_settings.get('auto_start', False):
            # Schedule regular automation sessions
            interval_minutes = scheduler_settings.get('session_interval_minutes', 120)
            schedule.every(interval_minutes).minutes.do(self._scheduled_automation_session)
            
            # Schedule during work hours only
            start_hour = scheduler_settings.get('start_hour', 9)
            end_hour = scheduler_settings.get('end_hour', 21)
            
            for hour in range(start_hour, end_hour, 2):  # Every 2 hours during work time
                schedule.every().day.at(f"{hour:02d}:00").do(self._scheduled_automation_session)
        
        # Start scheduler thread
        self.scheduler_thread = threading.Thread(target=self._run_scheduler, daemon=True)
        self.scheduler_thread.start()
        
        return True
    
    def stop_scheduler(self) -> bool:
        """Stop the automatic scheduler"""
        if not self.is_running:
            return False
        
        self.is_running = False
        schedule.clear()
        self.save_scheduler_state()
        
        # Stop active sessions
        self.stop_all_sessions()
        
        return True
    
    def _run_scheduler(self) -> None:
        """Main scheduler loop"""
        while self.is_running:
            try:
                schedule.run_pending()
                time.sleep(60)  # Check every minute
            except Exception as e:
                print(f"Scheduler error: {e}")
                time.sleep(60)
    
    def _scheduled_automation_session(self) -> None:
        """Run a scheduled automation session"""
        scheduler_settings = self.config.get('scheduler_settings', {})
        
        # Check if we're in allowed time window
        now = datetime.now()
        start_hour = scheduler_settings.get('start_hour', 9)
        end_hour = scheduler_settings.get('end_hour', 21)
        
        if not (start_hour <= now.hour < end_hour):
            return
        
        # Check if weekend activity is allowed
        if not scheduler_settings.get('weekend_activity', True) and now.weekday() >= 5:
            return
        
        # Start automation session
        self.start_automation_session(duration_minutes=30, auto_mode=True)
    
    def start_automation_session(self, duration_minutes: int = 30, 
                                session_count: int = 1, auto_mode: bool = False) -> Dict[str, Any]:
        """Start a manual or automatic automation session"""
        if not self.is_running and not auto_mode:
            return {"success": False, "error": "Scheduler not running"}
        
        # Get available sessions
        available_sessions = self.session_manager.get_active_sessions()
        if not available_sessions:
            return {"success": False, "error": "No active sessions available"}
        
        # Select sessions for automation
        selected_sessions = available_sessions[:session_count]
        
        session_results = []
        
        for session in selected_sessions:
            session_id = session.get('session_key', session.get('sessionid', ''))
            
            # Check if session is already active
            if session_id in self.active_sessions:
                continue
            
            # Start session thread
            session_thread = threading.Thread(
                target=self._run_automation_session,
                args=(session, duration_minutes),
                daemon=True
            )
            
            self.active_sessions[session_id] = {
                'thread': session_thread,
                'start_time': datetime.now().isoformat(),
                'duration_minutes': duration_minutes,
                'username': session.get('user', ''),
                'status': 'starting'
            }
            
            session_thread.start()
            session_results.append({
                'session_id': session_id,
                'username': session.get('user', ''),
                'status': 'started'
            })
        
        self.save_scheduler_state()
        
        return {
            "success": True,
            "sessions_started": len(session_results),
            "sessions": session_results,
            "mode": "auto" if auto_mode else "manual"
        }
    
    def _run_automation_session(self, session: Dict[str, Any], duration_minutes: int) -> None:
        """Run automation for a single session"""
        session_id = session.get('session_key', session.get('sessionid', ''))
        
        try:
            # Update session status
            if session_id in self.active_sessions:
                self.active_sessions[session_id]['status'] = 'running'
                self.save_scheduler_state()
            
            end_time = datetime.now() + timedelta(minutes=duration_minutes)
            activities_performed = []
            
            while datetime.now() < end_time and self.is_running:
                # Check daily limits before performing activities
                if not self.session_manager._check_daily_limits(session):
                    break
                
                # Decide what activity to perform
                activity_type = self._choose_random_activity()
                
                if activity_type == 'browsing':
                    result = self.activity_manager.random_browsing_session(session)
                    activities_performed.append(result)
                elif activity_type == 'wait':
                    # Random wait period
                    wait_time = self.activity_manager.get_random_delay()
                    time.sleep(wait_time)
                    activities_performed.append({
                        'activity': 'wait',
                        'duration': wait_time,
                        'timestamp': datetime.now().isoformat()
                    })
                
                # Random delay between activities
                delay = self.activity_manager.get_random_delay()
                time.sleep(delay)
            
            # Update session status
            if session_id in self.active_sessions:
                self.active_sessions[session_id]['status'] = 'completed'
                self.active_sessions[session_id]['activities'] = activities_performed
                self.save_scheduler_state()
        
        except Exception as e:
            # Update session status on error
            if session_id in self.active_sessions:
                self.active_sessions[session_id]['status'] = 'error'
                self.active_sessions[session_id]['error'] = str(e)
                self.save_scheduler_state()
        
        finally:
            # Clean up session from active list after some time
            threading.Timer(300, self._cleanup_session, args=[session_id]).start()
    
    def _choose_random_activity(self) -> str:
        """Choose a random activity type based on configuration"""
        import random
        
        activities = ['browsing', 'wait']
        weights = [0.7, 0.3]  # 70% browsing, 30% waiting
        
        return random.choices(activities, weights=weights)[0]
    
    def _cleanup_session(self, session_id: str) -> None:
        """Clean up completed session from active list"""
        if session_id in self.active_sessions:
            del self.active_sessions[session_id]
            self.save_scheduler_state()
    
    def stop_session(self, session_id: str) -> bool:
        """Stop a specific automation session"""
        if session_id not in self.active_sessions:
            return False
        
        session_info = self.active_sessions[session_id]
        session_info['status'] = 'stopped'
        session_info['stop_time'] = datetime.now().isoformat()
        
        self.save_scheduler_state()
        return True
    
    def stop_all_sessions(self) -> int:
        """Stop all active automation sessions"""
        stopped_count = 0
        
        for session_id in list(self.active_sessions.keys()):
            if self.stop_session(session_id):
                stopped_count += 1
        
        return stopped_count
    
    def get_scheduler_status(self) -> Dict[str, Any]:
        """Get current scheduler status"""
        stats = self.session_manager.get_session_stats()
        
        return {
            'is_running': self.is_running,
            'active_sessions_count': len(self.active_sessions),
            'active_sessions': {
                session_id: {
                    'username': info.get('username', ''),
                    'status': info.get('status', ''),
                    'start_time': info.get('start_time', ''),
                    'duration_minutes': info.get('duration_minutes', 0)
                }
                for session_id, info in self.active_sessions.items()
            },
            'session_stats': stats,
            'config': {
                'auto_start': self.config.get('scheduler_settings', {}).get('auto_start', False),
                'start_hour': self.config.get('scheduler_settings', {}).get('start_hour', 9),
                'end_hour': self.config.get('scheduler_settings', {}).get('end_hour', 21),
                'session_interval_minutes': self.config.get('scheduler_settings', {}).get('session_interval_minutes', 120)
            }
        }
    
    def get_activity_log(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent activity log"""
        activity_log = self.session_manager.load_activity_log()
        detailed_log = activity_log.get('detailed_log', [])
        
        # Return the most recent activities
        return detailed_log[-limit:] if detailed_log else []
    
    def manual_trigger_activity(self, activity_type: str, session_id: Optional[str] = None, 
                               target: Optional[str] = None) -> Dict[str, Any]:
        """Manually trigger a specific activity"""
        # Get session to use
        if session_id:
            sessions = self.session_manager.load_sessions()
            session = next((s for s in sessions if s.get('session_key') == session_id), None)
        else:
            session = self.session_manager.get_random_session()
        
        if not session:
            return {"success": False, "error": "No suitable session found"}
        
        try:
            result = False
            
            if activity_type == 'like' and target:
                result = self.activity_manager.like_post(session, target)
            elif activity_type == 'follow' and target:
                result = self.activity_manager.follow_user(session, target)
            elif activity_type == 'browse_feed':
                result = self.activity_manager.browse_feed(session, 60)
            elif activity_type == 'browse_explore':
                result = self.activity_manager.browse_explore(session, 60)
            elif activity_type == 'browse_reels':
                result = self.activity_manager.browse_reels(session, 60)
            elif activity_type == 'random_session':
                session_result = self.activity_manager.random_browsing_session(session)
                result = len(session_result.get('activities', [])) > 0
            else:
                return {"success": False, "error": f"Unknown activity type: {activity_type}"}
            
            return {
                "success": result,
                "activity_type": activity_type,
                "session_id": session.get('session_key', ''),
                "username": session.get('user', ''),
                "target": target,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}


if __name__ == "__main__":
    # Test the scheduler
    scheduler = InstagramScheduler()
    
    print("Scheduler status:", scheduler.get_scheduler_status())
    
    # Test manual trigger
    result = scheduler.manual_trigger_activity('browse_feed')
    print("Manual trigger result:", result)