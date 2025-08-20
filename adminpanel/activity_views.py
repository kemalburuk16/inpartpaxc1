"""
Activity Views - Flask routes for Instagram activity management
"""
import os
import json
from datetime import datetime
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from adminpanel.views import login_required
from adminpanel.instagram_activity import activity_manager

# Create activity blueprint
activity_bp = Blueprint('activity', __name__, url_prefix='/srdr-proadmin/activity')

@activity_bp.route('/')
@login_required
def dashboard():
    """Activity dashboard - main overview page"""
    try:
        # Get activity statistics
        stats = activity_manager.get_activity_stats()
        
        # Get recent logs
        recent_logs = activity_manager.get_recent_logs(20)
        
        # Get current configuration
        config = activity_manager.config
        
        # Get targets
        targets = activity_manager.get_targets()
        
        # Get session status from session pool
        session_status = {
            "total_sessions": len(activity_manager.session_pool.sessions),
            "active_sessions": len([s for s in activity_manager.session_pool.sessions 
                                  if s.get("status") == "active"]),
        }
        
        return render_template('admin/activity/dashboard.html',
                             stats=stats,
                             recent_logs=recent_logs,
                             config=config,
                             targets=targets,
                             session_status=session_status)
    except Exception as e:
        flash(f'Error loading dashboard: {str(e)}', 'error')
        return redirect(url_for('admin.dashboard'))

@activity_bp.route('/likes')
@login_required
def likes_management():
    """Likes management page"""
    try:
        # Get current targets
        targets = activity_manager.get_targets()
        
        # Get recent like activities
        all_logs = activity_manager.get_recent_logs(100)
        like_logs = [log for log in all_logs if log.get('activity_type') == 'like']
        
        return render_template('admin/activity/likes.html',
                             hashtags=targets.get('hashtags', []),
                             like_logs=like_logs)
    except Exception as e:
        flash(f'Error loading likes management: {str(e)}', 'error')
        return redirect(url_for('activity.dashboard'))

@activity_bp.route('/follows')
@login_required
def follows_management():
    """Follows management page"""
    try:
        # Get current targets
        targets = activity_manager.get_targets()
        
        # Get recent follow activities
        all_logs = activity_manager.get_recent_logs(100)
        follow_logs = [log for log in all_logs if log.get('activity_type') == 'follow']
        
        return render_template('admin/activity/follows.html',
                             accounts=targets.get('accounts', []),
                             follow_logs=follow_logs)
    except Exception as e:
        flash(f'Error loading follows management: {str(e)}', 'error')
        return redirect(url_for('activity.dashboard'))

@activity_bp.route('/scheduler')
@login_required
def scheduler():
    """Scheduler management page"""
    try:
        config = activity_manager.config
        
        return render_template('admin/activity/scheduler.html',
                             config=config)
    except Exception as e:
        flash(f'Error loading scheduler: {str(e)}', 'error')
        return redirect(url_for('activity.dashboard'))

# API Endpoints
@activity_bp.route('/api/config', methods=['GET', 'POST'])
@login_required
def api_config():
    """Get or update activity configuration"""
    if request.method == 'GET':
        return jsonify({
            'success': True,
            'config': activity_manager.config
        })
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'})
        
        # Validate configuration data
        required_fields = ['like_delay_min', 'like_delay_max', 'follow_delay_min', 
                          'follow_delay_max', 'daily_like_limit', 'daily_follow_limit']
        
        for field in required_fields:
            if field not in data:
                return jsonify({'success': False, 'error': f'Missing field: {field}'})
            
            # Ensure numeric values are integers
            try:
                data[field] = int(data[field])
            except (ValueError, TypeError):
                return jsonify({'success': False, 'error': f'Invalid value for {field}'})
        
        # Validate ranges
        if data['like_delay_min'] >= data['like_delay_max']:
            return jsonify({'success': False, 'error': 'Like delay min must be less than max'})
        
        if data['follow_delay_min'] >= data['follow_delay_max']:
            return jsonify({'success': False, 'error': 'Follow delay min must be less than max'})
        
        # Save configuration
        activity_manager.save_config(data)
        
        return jsonify({'success': True, 'message': 'Configuration updated successfully'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@activity_bp.route('/api/targets', methods=['GET', 'POST'])
@login_required
def api_targets():
    """Get or update activity targets"""
    if request.method == 'GET':
        return jsonify({
            'success': True,
            'targets': activity_manager.get_targets()
        })
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'})
        
        # Validate targets data
        targets = {
            'hashtags': data.get('hashtags', []),
            'accounts': data.get('accounts', [])
        }
        
        # Clean and validate hashtags
        clean_hashtags = []
        for hashtag in targets['hashtags']:
            hashtag = str(hashtag).strip().lstrip('#')
            if hashtag and hashtag.isalnum():
                clean_hashtags.append(hashtag)
        
        # Clean and validate accounts
        clean_accounts = []
        for account in targets['accounts']:
            account = str(account).strip().lstrip('@')
            if account and len(account) <= 30:  # Instagram username limit
                clean_accounts.append(account)
        
        targets['hashtags'] = clean_hashtags
        targets['accounts'] = clean_accounts
        
        # Save targets
        activity_manager.save_targets(targets)
        
        return jsonify({
            'success': True, 
            'message': 'Targets updated successfully',
            'targets': targets
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@activity_bp.route('/api/like_hashtag', methods=['POST'])
@login_required
def api_like_hashtag():
    """Manually trigger hashtag liking"""
    try:
        data = request.get_json()
        hashtag = data.get('hashtag', '').strip().lstrip('#')
        limit = int(data.get('limit', 10))
        
        if not hashtag:
            return jsonify({'success': False, 'error': 'Hashtag is required'})
        
        if limit < 1 or limit > 50:
            return jsonify({'success': False, 'error': 'Limit must be between 1 and 50'})
        
        # Perform hashtag liking
        result = activity_manager.like_posts_by_hashtag(hashtag, limit)
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@activity_bp.route('/api/follow_user', methods=['POST'])
@login_required
def api_follow_user():
    """Manually follow a user"""
    try:
        data = request.get_json()
        username = data.get('username', '').strip().lstrip('@')
        
        if not username:
            return jsonify({'success': False, 'error': 'Username is required'})
        
        # Perform follow
        success = activity_manager.follow_user(username)
        
        return jsonify({
            'success': success,
            'message': f'Successfully followed @{username}' if success else f'Failed to follow @{username}'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@activity_bp.route('/api/keep_alive', methods=['POST'])
@login_required
def api_keep_alive():
    """Manually trigger session keep-alive"""
    try:
        result = activity_manager.keep_sessions_alive()
        return jsonify({
            'success': True,
            'result': result
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@activity_bp.route('/api/stats')
@login_required
def api_stats():
    """Get current activity statistics"""
    try:
        stats = activity_manager.get_activity_stats()
        return jsonify({
            'success': True,
            'stats': stats
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@activity_bp.route('/api/logs')
@login_required
def api_logs():
    """Get activity logs"""
    try:
        limit = int(request.args.get('limit', 50))
        logs = activity_manager.get_recent_logs(limit)
        
        return jsonify({
            'success': True,
            'logs': logs
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@activity_bp.route('/api/toggle', methods=['POST'])
@login_required
def api_toggle():
    """Toggle activity system on/off"""
    try:
        data = request.get_json()
        enabled = bool(data.get('enabled', False))
        
        config = activity_manager.config
        config['enabled'] = enabled
        activity_manager.save_config(config)
        
        return jsonify({
            'success': True,
            'enabled': enabled,
            'message': f'Activity system {"enabled" if enabled else "disabled"}'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})