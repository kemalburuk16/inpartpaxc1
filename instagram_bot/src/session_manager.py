import json
import logging
import os
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional, Any

# Add parent directory to path to import existing modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

try:
    from session_pool import SessionPool
    from session_manager import load_json, save_json, normalize_session, detect_status, _blocked_set_with_expiry
except ImportError:
    # Fallback if modules are not available
    logging.warning("Could not import existing session modules")
    SessionPool = None

from utils import setup_logging, validate_session_data


class InstagramSessionManager:
    """
    Instagram session manager that wraps existing session functionality
    and provides additional features for the automation bot.
    """
    
    def __init__(self, sessions_path: str = "../sessions.json", blocked_path: str = "../blocked_cookies.json"):
        self.logger = setup_logging()
        self.sessions_path = os.path.abspath(sessions_path)
        self.blocked_path = os.path.abspath(blocked_path)
        
        # Use existing SessionPool if available
        if SessionPool:
            try:
                self.session_pool = SessionPool(
                    path_sessions=self.sessions_path,
                    path_blocked=self.blocked_path
                )
                self.logger.info("Initialized with existing SessionPool")
            except Exception as e:
                self.logger.error(f"Failed to initialize SessionPool: {e}")
                self.session_pool = None
        else:
            self.session_pool = None
            
        self.current_session = None
        self.failure_count = 0
        self.max_failures = 3
    
    def load_sessions(self) -> List[Dict[str, Any]]:
        """Load all sessions from file."""
        try:
            if os.path.exists(self.sessions_path):
                with open(self.sessions_path, 'r', encoding='utf-8') as f:
                    sessions = json.load(f)
                self.logger.info(f"Loaded {len(sessions)} sessions")
                return sessions
            else:
                self.logger.warning(f"Sessions file not found: {self.sessions_path}")
                return []
        except Exception as e:
            self.logger.error(f"Failed to load sessions: {e}")
            return []
    
    def get_active_session(self) -> Optional[Dict[str, Any]]:
        """Get an active session for making requests."""
        if self.session_pool:
            try:
                # Use existing session pool if available
                session_hint = self.session_pool.next_account_hint()
                if session_hint:
                    sessions = self.load_sessions()
                    for session in sessions:
                        if session.get('user') == session_hint:
                            if self.validate_session(session):
                                self.current_session = session
                                return session
                            break
            except Exception as e:
                self.logger.error(f"Error getting session from pool: {e}")
        
        # Fallback to manual session selection
        sessions = self.load_sessions()
        active_sessions = [s for s in sessions if s.get('status') == 'active']
        
        if not active_sessions:
            self.logger.warning("No active sessions available")
            return None
        
        # Filter out blocked sessions
        blocked_ids = self._get_blocked_session_ids()
        available_sessions = [
            s for s in active_sessions 
            if s.get('sessionid') not in blocked_ids
        ]
        
        if not available_sessions:
            self.logger.warning("No available sessions (all blocked)")
            return None
        
        # Select session with least failures
        best_session = min(available_sessions, key=lambda s: s.get('fail_count', 0))
        
        if self.validate_session(best_session):
            self.current_session = best_session
            return best_session
        
        return None
    
    def validate_session(self, session: Dict[str, Any]) -> bool:
        """Validate if session is valid and not expired."""
        if not validate_session_data(session):
            return False
        
        # Additional validation can be added here
        # For now, rely on existing status
        return session.get('status') == 'active'
    
    def mark_session_success(self, session: Dict[str, Any]) -> None:
        """Mark session as successful (reset failure count)."""
        if self.session_pool:
            try:
                # Let the session pool handle success reporting
                return
            except Exception as e:
                self.logger.error(f"Error reporting success to pool: {e}")
        
        # Fallback manual handling
        sessions = self.load_sessions()
        for i, s in enumerate(sessions):
            if s.get('sessionid') == session.get('sessionid'):
                sessions[i]['fail_count'] = 0
                sessions[i]['success_count'] = sessions[i].get('success_count', 0) + 1
                sessions[i]['last_used'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                break
        
        self._save_sessions(sessions)
        self.failure_count = 0
    
    def mark_session_failure(self, session: Dict[str, Any], error_code: Optional[int] = None) -> None:
        """Mark session as failed and potentially block it."""
        if self.session_pool:
            try:
                # Let the session pool handle failure reporting
                should_block = error_code in [401, 403, 419, 429] if error_code else True
                return
            except Exception as e:
                self.logger.error(f"Error reporting failure to pool: {e}")
        
        # Fallback manual handling
        sessions = self.load_sessions()
        for i, s in enumerate(sessions):
            if s.get('sessionid') == session.get('sessionid'):
                sessions[i]['fail_count'] = sessions[i].get('fail_count', 0) + 1
                
                # Block session if too many failures or specific error codes
                if (sessions[i]['fail_count'] >= self.max_failures or 
                    error_code in [401, 403, 419]):
                    sessions[i]['status'] = 'invalid'
                    self._block_session(session.get('sessionid'))
                
                break
        
        self._save_sessions(sessions)
        self.failure_count += 1
    
    def refresh_session_status(self) -> None:
        """Refresh status of all sessions."""
        if load_json and detect_status and _blocked_set_with_expiry:
            try:
                sessions = load_json(self.sessions_path)
                active_blocked = _blocked_set_with_expiry()
                
                for s in sessions:
                    normalize_session(s)
                    s["status"] = detect_status(s, active_blocked)
                
                save_json(self.sessions_path, sessions)
                self.logger.info(f"Refreshed status for {len(sessions)} sessions")
            except Exception as e:
                self.logger.error(f"Failed to refresh session status: {e}")
    
    def get_session_stats(self) -> Dict[str, int]:
        """Get statistics about sessions."""
        sessions = self.load_sessions()
        stats = {
            'total': len(sessions),
            'active': len([s for s in sessions if s.get('status') == 'active']),
            'invalid': len([s for s in sessions if s.get('status') == 'invalid']),
            'pending': len([s for s in sessions if s.get('status') == 'pending']),
            'blocked': len(self._get_blocked_session_ids())
        }
        return stats
    
    def _get_blocked_session_ids(self) -> set:
        """Get set of currently blocked session IDs."""
        blocked_ids = set()
        try:
            if os.path.exists(self.blocked_path):
                with open(self.blocked_path, 'r', encoding='utf-8') as f:
                    blocked_data = json.load(f)
                
                current_time = time.time()
                for entry in blocked_data:
                    if entry.get('blocked_until', 0) > current_time:
                        blocked_ids.add(entry.get('sessionid'))
        except Exception as e:
            self.logger.error(f"Failed to load blocked sessions: {e}")
        
        return blocked_ids
    
    def _block_session(self, session_id: str, duration_minutes: int = 30) -> None:
        """Block a session for specified duration."""
        try:
            blocked_data = []
            if os.path.exists(self.blocked_path):
                with open(self.blocked_path, 'r', encoding='utf-8') as f:
                    blocked_data = json.load(f)
            
            # Remove existing entry for this session
            blocked_data = [b for b in blocked_data if b.get('sessionid') != session_id]
            
            # Add new block entry
            blocked_until = time.time() + (duration_minutes * 60)
            blocked_data.append({
                'sessionid': session_id,
                'blocked_until': blocked_until
            })
            
            with open(self.blocked_path, 'w', encoding='utf-8') as f:
                json.dump(blocked_data, f, indent=2)
                
            self.logger.info(f"Blocked session {session_id} for {duration_minutes} minutes")
            
        except Exception as e:
            self.logger.error(f"Failed to block session: {e}")
    
    def _save_sessions(self, sessions: List[Dict[str, Any]]) -> None:
        """Save sessions to file."""
        try:
            with open(self.sessions_path, 'w', encoding='utf-8') as f:
                json.dump(sessions, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.logger.error(f"Failed to save sessions: {e}")
    
    def cleanup_expired_blocks(self) -> None:
        """Remove expired blocks from blocked sessions file."""
        try:
            if not os.path.exists(self.blocked_path):
                return
            
            with open(self.blocked_path, 'r', encoding='utf-8') as f:
                blocked_data = json.load(f)
            
            current_time = time.time()
            active_blocks = [
                b for b in blocked_data 
                if b.get('blocked_until', 0) > current_time
            ]
            
            with open(self.blocked_path, 'w', encoding='utf-8') as f:
                json.dump(active_blocks, f, indent=2)
                
            removed_count = len(blocked_data) - len(active_blocks)
            if removed_count > 0:
                self.logger.info(f"Cleaned up {removed_count} expired blocks")
                
        except Exception as e:
            self.logger.error(f"Failed to cleanup expired blocks: {e}")