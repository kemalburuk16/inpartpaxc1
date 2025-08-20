#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Session Manager - Wrapper around existing session infrastructure for Instagram automation
"""

import logging
import time
import sys
import os
from typing import Dict, Any, Optional, List

# Add parent directory to path to import existing modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from session_pool import SessionPool
from session_manager import update_sessions, load_json, SESSIONS_FILE

logger = logging.getLogger(__name__)


class SessionManager:
    """
    Wrapper around the existing session management infrastructure
    providing additional features for automation
    """
    
    def __init__(self):
        self.session_pool = SessionPool()
        self._last_health_check = 0
        self._health_check_interval = 300  # 5 minutes
        
        logger.info("SessionManager initialized")
    
    def get_session_pool(self) -> SessionPool:
        """Get the underlying session pool instance"""
        return self.session_pool
    
    def perform_health_check(self) -> Dict[str, Any]:
        """
        Perform health check on all sessions
        Returns health check results
        """
        current_time = time.time()
        
        # Don't check too frequently
        if current_time - self._last_health_check < self._health_check_interval:
            logger.debug("Skipping health check - too soon since last check")
            return self.get_session_status()
        
        logger.info("Performing session health check")
        
        try:
            # Update sessions using existing infrastructure
            update_sessions()
            self._last_health_check = current_time
            
            # Get updated status
            status = self.get_session_status()
            
            logger.info(f"Health check completed: {status['active']} active, "
                       f"{status['pending']} pending, {status['invalid']} invalid sessions")
            
            return status
            
        except Exception as e:
            logger.error(f"Error during health check: {e}")
            return {'error': str(e)}
    
    def get_session_status(self) -> Dict[str, Any]:
        """
        Get current status of all sessions
        Returns status summary
        """
        try:
            sessions = load_json(SESSIONS_FILE)
            
            status = {
                'total': len(sessions),
                'active': 0,
                'pending': 0,
                'invalid': 0,
                'blocked': 0,
                'sessions': []
            }
            
            for session in sessions:
                session_status = session.get('status', 'unknown')
                is_blocked = session.get('blocked', False)
                
                # Count by status
                if session_status == 'active' and not is_blocked:
                    status['active'] += 1
                elif session_status == 'pending':
                    status['pending'] += 1
                elif session_status == 'invalid' or is_blocked:
                    status['invalid'] += 1
                
                if is_blocked:
                    status['blocked'] += 1
                
                # Add session info
                session_info = {
                    'session_key': session.get('session_key', 'unknown'),
                    'user': session.get('user', 'unknown'),
                    'status': session_status,
                    'blocked': is_blocked,
                    'unblock_at': session.get('unblock_at'),
                    'last_used': session.get('last_used'),
                    'success_count': session.get('success_count', 0),
                    'fail_count': session.get('fail_count', 0)
                }
                status['sessions'].append(session_info)
            
            return status
            
        except Exception as e:
            logger.error(f"Error getting session status: {e}")
            return {'error': str(e)}
    
    def get_best_sessions(self, count: int = 5) -> List[Dict[str, Any]]:
        """
        Get the best available sessions for automation
        Returns list of session info
        """
        try:
            sessions = load_json(SESSIONS_FILE)
            
            # Filter for active, non-blocked sessions
            good_sessions = []
            for session in sessions:
                if (session.get('status') == 'active' and 
                    not session.get('blocked', False)):
                    good_sessions.append(session)
            
            # Sort by success rate and recent usage
            def session_score(session):
                success_count = session.get('success_count', 0)
                fail_count = session.get('fail_count', 0)
                total_requests = success_count + fail_count
                
                if total_requests == 0:
                    success_rate = 1.0  # New sessions get benefit of doubt
                else:
                    success_rate = success_count / total_requests
                
                # Prefer sessions with good success rate and some usage
                return success_rate * min(total_requests, 100)
            
            good_sessions.sort(key=session_score, reverse=True)
            
            # Return top sessions
            return good_sessions[:count]
            
        except Exception as e:
            logger.error(f"Error getting best sessions: {e}")
            return []
    
    def mark_session_used(self, session_key: str, success: bool = True):
        """
        Mark a session as used (for tracking purposes)
        This is handled automatically by SessionPool, but can be called manually
        """
        try:
            if success:
                logger.debug(f"Session {session_key} used successfully")
            else:
                logger.warning(f"Session {session_key} failed")
                
        except Exception as e:
            logger.error(f"Error marking session usage: {e}")
    
    def get_session_recommendations(self) -> Dict[str, Any]:
        """
        Get recommendations for session management
        Returns recommendations and warnings
        """
        try:
            status = self.get_session_status()
            recommendations = {
                'warnings': [],
                'suggestions': [],
                'critical': []
            }
            
            # Check total session count
            if status['total'] < 3:
                recommendations['critical'].append(
                    "Very low session count. Add more sessions for better reliability."
                )
            elif status['total'] < 5:
                recommendations['warnings'].append(
                    "Low session count. Consider adding more sessions."
                )
            
            # Check active session ratio
            if status['total'] > 0:
                active_ratio = status['active'] / status['total']
                if active_ratio < 0.3:
                    recommendations['critical'].append(
                        "Too few active sessions. Check session health and add new ones."
                    )
                elif active_ratio < 0.5:
                    recommendations['warnings'].append(
                        "Low ratio of active sessions. Some sessions may need attention."
                    )
            
            # Check blocked sessions
            if status['blocked'] > 0:
                if status['blocked'] > status['active']:
                    recommendations['warnings'].append(
                        "More sessions are blocked than active. Reduce automation intensity."
                    )
                else:
                    recommendations['suggestions'].append(
                        f"{status['blocked']} sessions are temporarily blocked. This is normal."
                    )
            
            # Check session distribution
            if status['total'] > 0:
                invalid_ratio = status['invalid'] / status['total']
                if invalid_ratio > 0.5:
                    recommendations['critical'].append(
                        "Too many invalid sessions. Review and refresh session pool."
                    )
            
            return recommendations
            
        except Exception as e:
            logger.error(f"Error getting recommendations: {e}")
            return {'error': str(e)}
    
    def test_session_connectivity(self, session_key: str = None) -> Dict[str, Any]:
        """
        Test connectivity of a specific session or all sessions
        Returns test results
        """
        try:
            sessions = load_json(SESSIONS_FILE)
            
            if session_key:
                # Test specific session
                target_sessions = [s for s in sessions if s.get('session_key') == session_key]
                if not target_sessions:
                    return {'error': f'Session {session_key} not found'}
                sessions_to_test = target_sessions
            else:
                # Test active sessions only
                sessions_to_test = [s for s in sessions if s.get('status') == 'active']
            
            results = []
            
            for session in sessions_to_test[:5]:  # Limit to 5 to avoid spam
                session_key = session.get('session_key', 'unknown')
                
                try:
                    # Use session pool to make a simple test request
                    response = self.session_pool.http_get(
                        "https://i.instagram.com/api/v1/accounts/current_user/",
                        extra_headers={'User-Agent': 'Instagram 300.0.0 Android'}
                    )
                    
                    if response and response.status_code == 200:
                        status = 'success'
                        message = 'Session is working'
                    else:
                        status = 'failed'
                        message = f'HTTP {response.status_code if response else "No response"}'
                    
                except Exception as e:
                    status = 'error'
                    message = str(e)
                
                results.append({
                    'session_key': session_key,
                    'user': session.get('user', 'unknown'),
                    'status': status,
                    'message': message
                })
                
                # Small delay between tests
                time.sleep(2)
            
            return {'results': results}
            
        except Exception as e:
            logger.error(f"Error testing session connectivity: {e}")
            return {'error': str(e)}
    
    def get_usage_statistics(self) -> Dict[str, Any]:
        """
        Get usage statistics for sessions
        Returns usage stats
        """
        try:
            sessions = load_json(SESSIONS_FILE)
            
            stats = {
                'total_sessions': len(sessions),
                'total_requests': 0,
                'total_successes': 0,
                'total_failures': 0,
                'average_success_rate': 0,
                'most_used_session': None,
                'least_used_session': None
            }
            
            if not sessions:
                return stats
            
            success_rates = []
            session_usage = []
            
            for session in sessions:
                success_count = session.get('success_count', 0)
                fail_count = session.get('fail_count', 0)
                total_requests = success_count + fail_count
                
                stats['total_requests'] += total_requests
                stats['total_successes'] += success_count
                stats['total_failures'] += fail_count
                
                if total_requests > 0:
                    success_rate = success_count / total_requests
                    success_rates.append(success_rate)
                    
                    session_usage.append({
                        'session_key': session.get('session_key', 'unknown'),
                        'user': session.get('user', 'unknown'),
                        'total_requests': total_requests,
                        'success_rate': success_rate
                    })
            
            # Calculate average success rate
            if success_rates:
                stats['average_success_rate'] = sum(success_rates) / len(success_rates)
            
            # Find most and least used sessions
            if session_usage:
                session_usage.sort(key=lambda x: x['total_requests'], reverse=True)
                stats['most_used_session'] = session_usage[0]
                stats['least_used_session'] = session_usage[-1]
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting usage statistics: {e}")
            return {'error': str(e)}
    
    def cleanup_old_data(self):
        """Clean up old session data and perform maintenance"""
        try:
            logger.info("Performing session cleanup")
            
            # This could include:
            # - Removing very old blocked entries
            # - Resetting fail counts for sessions that haven't been used recently
            # - Other maintenance tasks
            
            # For now, just trigger a health check
            self.perform_health_check()
            
            logger.info("Session cleanup completed")
            
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")