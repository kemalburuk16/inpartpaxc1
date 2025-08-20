#!/usr/bin/env python3
"""
Instagram Automation System
A comprehensive Instagram automation module for instavideo
"""

try:
    from .session_manager import AutoSessionManager
    from .activity_manager import InstagramActivityManager
    from .scheduler import InstagramScheduler
except ImportError:
    from session_manager import AutoSessionManager
    from activity_manager import InstagramActivityManager
    from scheduler import InstagramScheduler

__version__ = "1.0.0"
__author__ = "InstaVideo Team"
__email__ = "support@instavideo.com"

# Main automation class for easy access
class InstagramAuto:
    """Main Instagram automation class"""
    
    def __init__(self):
        self.session_manager = AutoSessionManager()
        self.activity_manager = InstagramActivityManager(self.session_manager)
        self.scheduler = InstagramScheduler(self.session_manager)
    
    def start_automation(self, duration_minutes: int = 30, session_count: int = 1):
        """Start automation session"""
        return self.scheduler.start_automation_session(duration_minutes, session_count)
    
    def stop_automation(self):
        """Stop all automation"""
        return self.scheduler.stop_all_sessions()
    
    def get_status(self):
        """Get automation status"""
        return self.scheduler.get_scheduler_status()
    
    def manual_activity(self, activity_type: str, target: str = None):
        """Trigger manual activity"""
        return self.scheduler.manual_trigger_activity(activity_type, target=target)

# Convenience functions
def create_automation():
    """Create new automation instance"""
    return InstagramAuto()

def get_active_sessions():
    """Get active sessions"""
    manager = AutoSessionManager()
    return manager.get_active_sessions()

def get_session_stats():
    """Get session statistics"""
    manager = AutoSessionManager()
    return manager.get_session_stats()

__all__ = [
    'AutoSessionManager',
    'InstagramActivityManager', 
    'InstagramScheduler',
    'InstagramAuto',
    'create_automation',
    'get_active_sessions',
    'get_session_stats'
]