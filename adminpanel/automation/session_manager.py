# -*- coding: utf-8 -*-
"""
Session Manager for Instagram Automation
Mevcut sessions.json dosyası ile entegrasyonu sağlar.
"""

import json
import time
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from threading import Lock

class AutomationSessionManager:
    """Instagram session'larını yönetir ve otomasyon için uygun session'ları seçer"""
    
    def __init__(self, sessions_file: str, blocked_file: str = None):
        self.sessions_file = sessions_file
        self.blocked_file = blocked_file or os.path.join(os.path.dirname(sessions_file), "blocked_cookies.json")
        self.lock = Lock()
        self._sessions = []
        self._current_session_index = 0
        self._last_reload = 0
        self._reload_interval = 300  # 5 dakika
        
        self.logger = logging.getLogger(__name__)
        self._load_sessions()
    
    def _load_sessions(self) -> None:
        """Sessions dosyasını yükle"""
        try:
            with open(self.sessions_file, 'r', encoding='utf-8') as f:
                self._sessions = json.load(f)
            self._last_reload = time.time()
            self.logger.info(f"Loaded {len(self._sessions)} sessions from {self.sessions_file}")
        except Exception as e:
            self.logger.error(f"Error loading sessions: {e}")
            self._sessions = []
    
    def _save_sessions(self) -> None:
        """Sessions dosyasını kaydet"""
        try:
            with open(self.sessions_file, 'w', encoding='utf-8') as f:
                json.dump(self._sessions, f, indent=2, ensure_ascii=False)
            self.logger.info("Sessions saved successfully")
        except Exception as e:
            self.logger.error(f"Error saving sessions: {e}")
    
    def _get_blocked_sessions(self) -> set:
        """Bloklu session'ları döner"""
        blocked_ids = set()
        if not os.path.exists(self.blocked_file):
            return blocked_ids
        
        try:
            with open(self.blocked_file, 'r', encoding='utf-8') as f:
                blocked_data = json.load(f)
            
            current_time = time.time()
            for item in blocked_data:
                if item.get('blocked_until', 0) > current_time:
                    blocked_ids.add(item.get('sessionid'))
        except Exception as e:
            self.logger.error(f"Error reading blocked sessions: {e}")
        
        return blocked_ids
    
    def _should_reload(self) -> bool:
        """Session'ları yeniden yüklemeli mi?"""
        return time.time() - self._last_reload > self._reload_interval
    
    def get_available_sessions(self) -> List[Dict[str, Any]]:
        """Kullanılabilir session'ları döner"""
        with self.lock:
            if self._should_reload():
                self._load_sessions()
            
            blocked_sessions = self._get_blocked_sessions()
            available = []
            
            for session in self._sessions:
                sessionid = session.get('sessionid')
                status = session.get('status', 'unknown')
                
                # Bloklu değilse ve aktifse
                if sessionid not in blocked_sessions and status == 'active':
                    available.append(session)
            
            return available
    
    def get_next_session(self) -> Optional[Dict[str, Any]]:
        """Sıradaki kullanılabilir session'ı döner"""
        available_sessions = self.get_available_sessions()
        
        if not available_sessions:
            self.logger.warning("No available sessions found")
            return None
        
        with self.lock:
            # Round-robin selection
            session = available_sessions[self._current_session_index % len(available_sessions)]
            self._current_session_index = (self._current_session_index + 1) % len(available_sessions)
            
            # Son kullanım zamanını güncelle
            session['last_used'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            self._update_session_data(session)
            
            return session
    
    def _update_session_data(self, updated_session: Dict[str, Any]) -> None:
        """Session verisini güncelle"""
        sessionid = updated_session.get('sessionid')
        
        for i, session in enumerate(self._sessions):
            if session.get('sessionid') == sessionid:
                self._sessions[i] = updated_session
                break
        
        self._save_sessions()
    
    def mark_session_success(self, session: Dict[str, Any]) -> None:
        """Session'ı başarılı olarak işaretle"""
        session['success_count'] = session.get('success_count', 0) + 1
        session['fail_count'] = max(0, session.get('fail_count', 0) - 1)  # Başarı durumunda fail sayısını azalt
        session['status'] = 'active'
        session['last_success'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        self._update_session_data(session)
        self.logger.info(f"Session {session.get('user', 'unknown')} marked as successful")
    
    def mark_session_failed(self, session: Dict[str, Any], error_type: str = 'unknown') -> None:
        """Session'ı başarısız olarak işaretle"""
        session['fail_count'] = session.get('fail_count', 0) + 1
        session['last_error'] = error_type
        session['last_failure'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Çok fazla hata varsa session'ı deaktif et
        if session['fail_count'] >= 5:
            session['status'] = 'invalid'
            self.logger.warning(f"Session {session.get('user', 'unknown')} marked as invalid due to repeated failures")
        
        self._update_session_data(session)
        self.logger.warning(f"Session {session.get('user', 'unknown')} failed: {error_type}")
    
    def get_session_stats(self) -> Dict[str, int]:
        """Session istatistiklerini döner"""
        with self.lock:
            if self._should_reload():
                self._load_sessions()
            
            blocked_sessions = self._get_blocked_sessions()
            
            stats = {
                'total': len(self._sessions),
                'active': 0,
                'blocked': 0,
                'invalid': 0,
                'available': 0
            }
            
            for session in self._sessions:
                status = session.get('status', 'unknown')
                sessionid = session.get('sessionid')
                
                if sessionid in blocked_sessions:
                    stats['blocked'] += 1
                elif status == 'active':
                    stats['active'] += 1
                    if sessionid not in blocked_sessions:
                        stats['available'] += 1
                elif status == 'invalid':
                    stats['invalid'] += 1
            
            return stats
    
    def get_session_by_user(self, username: str) -> Optional[Dict[str, Any]]:
        """Kullanıcı adına göre session döner"""
        with self.lock:
            for session in self._sessions:
                if session.get('user') == username:
                    return session
        return None
    
    def is_session_healthy(self, session: Dict[str, Any]) -> bool:
        """Session'ın sağlıklı olup olmadığını kontrol eder"""
        # Temel kontroller
        required_fields = ['sessionid', 'ds_user_id', 'csrftoken']
        for field in required_fields:
            if not session.get(field):
                return False
        
        # Fail oranı kontrolü
        fail_count = session.get('fail_count', 0)
        success_count = session.get('success_count', 0)
        
        if fail_count > 3 and success_count == 0:
            return False
        
        if fail_count > success_count * 2:  # Fail oranı çok yüksek
            return False
        
        # Status kontrolü
        if session.get('status') != 'active':
            return False
        
        return True
    
    def get_healthy_sessions(self) -> List[Dict[str, Any]]:
        """Sağlıklı session'ları döner"""
        available = self.get_available_sessions()
        return [s for s in available if self.is_session_healthy(s)]
    
    def cleanup_old_sessions(self, days: int = 30) -> int:
        """Eski session'ları temizle"""
        cutoff_date = datetime.now() - timedelta(days=days)
        cutoff_str = cutoff_date.strftime('%Y-%m-%d %H:%M:%S')
        
        with self.lock:
            original_count = len(self._sessions)
            
            # Son kullanım tarihi çok eski olan session'ları kaldır
            self._sessions = [
                s for s in self._sessions 
                if s.get('last_used', '9999-12-31 23:59:59') > cutoff_str or s.get('status') == 'active'
            ]
            
            removed_count = original_count - len(self._sessions)
            
            if removed_count > 0:
                self._save_sessions()
                self.logger.info(f"Cleaned up {removed_count} old sessions")
            
            return removed_count
    
    def force_reload(self) -> None:
        """Session'ları zorla yeniden yükle"""
        with self.lock:
            self._load_sessions()
    
    def add_automation_metrics(self, session: Dict[str, Any], activity_type: str, success: bool) -> None:
        """Otomasyon metrikleri ekle"""
        if 'automation_stats' not in session:
            session['automation_stats'] = {}
        
        stats = session['automation_stats']
        
        if activity_type not in stats:
            stats[activity_type] = {'success': 0, 'failed': 0, 'last_activity': None}
        
        if success:
            stats[activity_type]['success'] += 1
        else:
            stats[activity_type]['failed'] += 1
        
        stats[activity_type]['last_activity'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        self._update_session_data(session)
    
    def get_session_activity_summary(self, session: Dict[str, Any]) -> Dict[str, Any]:
        """Session'ın aktivite özetini döner"""
        automation_stats = session.get('automation_stats', {})
        
        total_activities = 0
        total_success = 0
        total_failed = 0
        
        for activity_data in automation_stats.values():
            total_success += activity_data.get('success', 0)
            total_failed += activity_data.get('failed', 0)
        
        total_activities = total_success + total_failed
        success_rate = (total_success / total_activities * 100) if total_activities > 0 else 0
        
        return {
            'total_activities': total_activities,
            'success_rate': round(success_rate, 2),
            'automation_stats': automation_stats,
            'last_used': session.get('last_used'),
            'status': session.get('status'),
            'fail_count': session.get('fail_count', 0),
            'success_count': session.get('success_count', 0)
        }