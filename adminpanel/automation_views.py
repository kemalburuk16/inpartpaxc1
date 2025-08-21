# -*- coding: utf-8 -*-
"""
Instagram Automation Views  
Admin panel için otomasyon kontrol route'ları.
"""

import json
import time
import threading
import os
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from flask import render_template, request, jsonify, redirect, url_for

# Avoid circular imports by importing within functions when needed
def get_admin_requirements():
    """Get admin panel requirements safely"""
    try:
        from adminpanel import admin_bp
        from adminpanel.views import login_required, BASE_DIR
        return admin_bp, login_required, BASE_DIR
    except ImportError as e:
        print(f"Warning: Could not import admin requirements: {e}")
        return None, None, None

def get_automation_modules():
    """Get automation modules safely"""
    try:
        from adminpanel.automation import (
            InstagramBot, AutomationSessionManager, ActivityScheduler, 
            HumanBehavior, AutomationConfig
        )
        from adminpanel.automation.activity_scheduler import ActivityType, ScheduledActivity
        return (InstagramBot, AutomationSessionManager, ActivityScheduler, 
                HumanBehavior, AutomationConfig, ActivityType, ScheduledActivity)
    except ImportError as e:
        print(f"Warning: Could not import automation modules: {e}")
        return None, None, None, None, None, None, None

# Get requirements
admin_bp, login_required, BASE_DIR = get_admin_requirements()

# Handle cases where imports fail
if not admin_bp:
    # Create a mock blueprint for testing
    from flask import Blueprint
    admin_bp = Blueprint('admin', __name__)
    
    def login_required(f):
        return f
    
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Singleton instances
_automation_manager = None
_activity_scheduler = None
_session_manager = None

def get_automation_manager():
    """Automation manager singleton"""
    global _automation_manager, _session_manager, _activity_scheduler
    
    if _automation_manager is None:
        # Get automation modules
        automation_modules = get_automation_modules()
        if None in automation_modules:
            raise ImportError("Could not import automation modules")
        
        (InstagramBot, AutomationSessionManager, ActivityScheduler, 
         HumanBehavior, AutomationConfig, ActivityType, ScheduledActivity) = automation_modules
        
        sessions_file = os.path.join(BASE_DIR, "sessions.json")
        blocked_file = os.path.join(BASE_DIR, "blocked_cookies.json")
        
        _session_manager = AutomationSessionManager(sessions_file, blocked_file)
        _activity_scheduler = ActivityScheduler(AutomationConfig, _session_manager)
        _automation_manager = InstagramBot(AutomationConfig, _session_manager)
        
        # Activity executor'ları kaydet
        _register_activity_executors()
        
        # Scheduler'ı başlat
        _activity_scheduler.start_scheduler()
    
    return _automation_manager, _activity_scheduler, _session_manager

def _register_activity_executors():
    """Activity executor'ları kaydet"""
    global _activity_scheduler, _automation_manager
    
    # Get automation modules
    automation_modules = get_automation_modules()
    if None in automation_modules:
        raise ImportError("Could not import automation modules")
    
    (InstagramBot, AutomationSessionManager, ActivityScheduler, 
     HumanBehavior, AutomationConfig, ActivityType, ScheduledActivity) = automation_modules
    
    def execute_like(activity: ScheduledActivity) -> bool:
        try:
            with _automation_manager:
                session = _session_manager.get_session_by_user(activity.session_user)
                if not session:
                    return False
                
                if not _automation_manager.start_session(session):
                    return False
                
                count = activity.metadata.get('count', 1)
                result = _automation_manager.like_posts(count)
                return result > 0
        except Exception as e:
            logging.error(f"Error executing like activity: {e}")
            return False
    
    def execute_follow(activity: ScheduledActivity) -> bool:
        try:
            with _automation_manager:
                session = _session_manager.get_session_by_user(activity.session_user)
                if not session:
                    return False
                
                if not _automation_manager.start_session(session):
                    return False
                
                count = activity.metadata.get('count', 1)
                hashtag = activity.target
                result = _automation_manager.follow_users(hashtag, count)
                return result > 0
        except Exception as e:
            logging.error(f"Error executing follow activity: {e}")
            return False
    
    def execute_comment(activity: ScheduledActivity) -> bool:
        try:
            with _automation_manager:
                session = _session_manager.get_session_by_user(activity.session_user)
                if not session:
                    return False
                
                if not _automation_manager.start_session(session):
                    return False
                
                count = activity.metadata.get('count', 1)
                result = _automation_manager.comment_on_posts(count)
                return result > 0
        except Exception as e:
            logging.error(f"Error executing comment activity: {e}")
            return False
    
    def execute_story_view(activity: ScheduledActivity) -> bool:
        try:
            with _automation_manager:
                session = _session_manager.get_session_by_user(activity.session_user)
                if not session:
                    return False
                
                if not _automation_manager.start_session(session):
                    return False
                
                count = activity.metadata.get('count', 3)
                result = _automation_manager.view_stories(count)
                return result > 0
        except Exception as e:
            logging.error(f"Error executing story view activity: {e}")
            return False
    
    def execute_profile_visit(activity: ScheduledActivity) -> bool:
        try:
            with _automation_manager:
                session = _session_manager.get_session_by_user(activity.session_user)
                if not session:
                    return False
                
                if not _automation_manager.start_session(session):
                    return False
                
                count = activity.metadata.get('count', 2)
                result = _automation_manager.visit_profiles(count)
                return result > 0
        except Exception as e:
            logging.error(f"Error executing profile visit activity: {e}")
            return False
    
    def execute_explore_browse(activity: ScheduledActivity) -> bool:
        try:
            with _automation_manager:
                session = _session_manager.get_session_by_user(activity.session_user)
                if not session:
                    return False
                
                if not _automation_manager.start_session(session):
                    return False
                
                duration = activity.metadata.get('duration', 60)
                return _automation_manager.browse_explore(duration)
        except Exception as e:
            logging.error(f"Error executing explore browse activity: {e}")
            return False
    
    def execute_keepalive(activity: ScheduledActivity) -> bool:
        try:
            with _automation_manager:
                session = _session_manager.get_session_by_user(activity.session_user)
                if not session:
                    return False
                
                if not _automation_manager.start_session(session):
                    return False
                
                return _automation_manager.perform_keepalive_activity()
        except Exception as e:
            logging.error(f"Error executing keepalive activity: {e}")
            return False
    
    # Executor'ları kaydet
    _activity_scheduler.register_activity_executor(ActivityType.LIKE, execute_like)
    _activity_scheduler.register_activity_executor(ActivityType.FOLLOW, execute_follow)
    _activity_scheduler.register_activity_executor(ActivityType.COMMENT, execute_comment)
    _activity_scheduler.register_activity_executor(ActivityType.STORY_VIEW, execute_story_view)
    _activity_scheduler.register_activity_executor(ActivityType.PROFILE_VISIT, execute_profile_visit)
    _activity_scheduler.register_activity_executor(ActivityType.EXPLORE_BROWSE, execute_explore_browse)
    _activity_scheduler.register_activity_executor(ActivityType.SESSION_KEEPALIVE, execute_keepalive)

# ============================================================================
# Routes
# ============================================================================

@admin_bp.route('/automation')
@login_required
def automation_dashboard():
    """Otomasyon ana kontrol paneli"""
    return render_template('admin/automation_dashboard.html')

@admin_bp.route('/automation/sessions')
@login_required  
def automation_sessions():
    """Session yönetimi sayfası"""
    return render_template('admin/automation_sessions.html')

@admin_bp.route('/automation/activity-logs')
@login_required
def automation_activity_logs():
    """Aktivite logları sayfası"""
    return render_template('admin/activity_logs.html')

# ============================================================================
# API Endpoints
# ============================================================================

@admin_bp.route('/api/automation/status')
@login_required
def api_automation_status():
    """Otomasyon sistemi durumu"""
    try:
        _, scheduler, session_manager = get_automation_manager()
        
        session_stats = session_manager.get_session_stats()
        activity_stats = scheduler.get_activity_stats(hours=24)
        
        return jsonify({
            'success': True,
            'automation_active': scheduler.is_running,
            'session_stats': session_stats,
            'activity_stats': activity_stats,
            'config': {
                'daily_likes_limit': AutomationConfig.DAILY_LIKES_LIMIT,
                'daily_follows_limit': AutomationConfig.DAILY_FOLLOWS_LIMIT,
                'daily_comments_limit': AutomationConfig.DAILY_COMMENTS_LIMIT,
                'automation_enabled': AutomationConfig.ENABLE_AUTOMATION
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@admin_bp.route('/api/automation/sessions')
@login_required
def api_automation_sessions():
    """Session listesi ve durumları"""
    try:
        _, _, session_manager = get_automation_manager()
        
        all_sessions = session_manager.get_available_sessions()
        session_summaries = []
        
        for session in all_sessions:
            summary = session_manager.get_session_activity_summary(session)
            summary.update({
                'user': session.get('user'),
                'session_key': session.get('session_key'),
                'status': session.get('status'),
                'last_used': session.get('last_used')
            })
            session_summaries.append(summary)
        
        return jsonify({
            'success': True,
            'sessions': session_summaries
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@admin_bp.route('/api/automation/activities')
@login_required
def api_automation_activities():
    """Son aktiviteler"""
    try:
        _, scheduler, _ = get_automation_manager()
        
        limit = int(request.args.get('limit', 50))
        activities = scheduler.get_recent_activities(limit)
        
        return jsonify({
            'success': True,
            'activities': activities
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@admin_bp.route('/api/automation/schedule-activity', methods=['POST'])
@login_required
def api_schedule_activity():
    """Manuel aktivite zamanla"""
    try:
        data = request.get_json()
        
        activity_type = ActivityType(data.get('activity_type'))
        session_user = data.get('session_user')
        target = data.get('target')
        delay_seconds = int(data.get('delay_seconds', 0))
        metadata = data.get('metadata', {})
        
        _, scheduler, _ = get_automation_manager()
        
        activity_id = scheduler.schedule_activity(
            activity_type, session_user, target, delay_seconds, metadata
        )
        
        if activity_id:
            return jsonify({
                'success': True,
                'activity_id': activity_id,
                'message': f'Activity {activity_type.value} scheduled for {session_user}'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to schedule activity (daily limit reached?)'
            })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@admin_bp.route('/api/automation/schedule-random', methods=['POST'])
@login_required
def api_schedule_random_activity():
    """Rastgele aktivite zamanla"""
    try:
        data = request.get_json()
        session_user = data.get('session_user')
        
        _, scheduler, _ = get_automation_manager()
        
        activity_id = scheduler.schedule_random_activity(session_user)
        
        if activity_id:
            return jsonify({
                'success': True,
                'activity_id': activity_id,
                'message': f'Random activity scheduled for {session_user}'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to schedule random activity'
            })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@admin_bp.route('/api/automation/schedule-keepalive', methods=['POST'])
@login_required
def api_schedule_keepalive():
    """Keep-alive aktivitesi zamanla"""
    try:
        data = request.get_json()
        session_user = data.get('session_user')
        
        _, scheduler, _ = get_automation_manager()
        
        if session_user:
            activity_id = scheduler.schedule_keepalive_session(session_user)
            message = f'Keep-alive scheduled for {session_user}'
        else:
            # Tüm session'lar için
            count = scheduler.schedule_bulk_keepalive()
            activity_id = True
            message = f'Keep-alive scheduled for {count} sessions'
        
        if activity_id:
            return jsonify({
                'success': True,
                'message': message
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to schedule keep-alive'
            })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@admin_bp.route('/api/automation/cancel-activity', methods=['POST'])
@login_required
def api_cancel_activity():
    """Aktiviteyi iptal et"""
    try:
        data = request.get_json()
        activity_id = data.get('activity_id')
        
        _, scheduler, _ = get_automation_manager()
        
        success = scheduler.cancel_activity(activity_id)
        
        return jsonify({
            'success': success,
            'message': 'Activity cancelled' if success else 'Activity not found'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@admin_bp.route('/api/automation/retry-activity', methods=['POST'])
@login_required
def api_retry_activity():
    """Aktiviteyi yeniden dene"""
    try:
        data = request.get_json()
        activity_id = data.get('activity_id')
        
        _, scheduler, _ = get_automation_manager()
        
        success = scheduler.retry_activity(activity_id)
        
        return jsonify({
            'success': success,
            'message': 'Activity retried' if success else 'Cannot retry activity'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@admin_bp.route('/api/automation/config', methods=['GET', 'POST'])
@login_required
def api_automation_config():
    """Otomasyon konfigürasyonu"""
    if request.method == 'GET':
        return jsonify({
            'success': True,
            'config': AutomationConfig.get_config_dict()
        })
    
    elif request.method == 'POST':
        try:
            data = request.get_json()
            
            # Güvenli bir şekilde config'i güncelle
            # Bu implementasyonda sadece bazı değerleri güncellemeye izin ver
            safe_updates = [
                'daily_likes_limit', 'daily_follows_limit', 'daily_comments_limit',
                'like_probability', 'follow_probability', 'comment_probability',
                'min_action_delay', 'max_action_delay'
            ]
            
            updated = {}
            for key, value in data.items():
                if key in safe_updates:
                    setattr(AutomationConfig, key.upper(), value)
                    updated[key] = value
            
            return jsonify({
                'success': True,
                'updated': updated,
                'message': f'Updated {len(updated)} config values'
            })
            
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})

@admin_bp.route('/api/automation/start-scheduler', methods=['POST'])
@login_required
def api_start_scheduler():
    """Scheduler'ı başlat"""
    try:
        _, scheduler, _ = get_automation_manager()
        scheduler.start_scheduler()
        
        return jsonify({
            'success': True,
            'message': 'Automation scheduler started'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@admin_bp.route('/api/automation/stop-scheduler', methods=['POST'])
@login_required
def api_stop_scheduler():
    """Scheduler'ı durdur"""
    try:
        _, scheduler, _ = get_automation_manager()
        scheduler.stop_scheduler()
        
        return jsonify({
            'success': True,
            'message': 'Automation scheduler stopped'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@admin_bp.route('/api/automation/test-session', methods=['POST'])
@login_required
def api_test_session():
    """Session'ı test et"""
    try:
        data = request.get_json()
        session_user = data.get('session_user')
        
        automation_manager, _, session_manager = get_automation_manager()
        
        session = session_manager.get_session_by_user(session_user)
        if not session:
            return jsonify({
                'success': False,
                'error': 'Session not found'
            })
        
        # Test için basit login denemesi
        with automation_manager:
            success = automation_manager.start_session(session)
            
            result = {
                'success': success,
                'user': session_user,
                'login_successful': success,
                'message': 'Login successful' if success else 'Login failed'
            }
            
            if success:
                # Ek bilgiler
                info = automation_manager.get_current_session_info()
                result.update(info)
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})