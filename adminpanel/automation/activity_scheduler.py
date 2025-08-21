# -*- coding: utf-8 -*-
"""
Activity Scheduler for Instagram Automation
Aktiviteleri planlama ve zamanlama sistemi.
"""

import json
import time
import random
import threading
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, asdict
from enum import Enum

class ActivityType(Enum):
    """Aktivite türleri"""
    LIKE = "like"
    FOLLOW = "follow" 
    UNFOLLOW = "unfollow"
    COMMENT = "comment"
    STORY_VIEW = "story_view"
    PROFILE_VISIT = "profile_visit"
    EXPLORE_BROWSE = "explore_browse"
    SESSION_KEEPALIVE = "session_keepalive"

class ActivityStatus(Enum):
    """Aktivite durumları"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class ScheduledActivity:
    """Zamanlanmış aktivite"""
    id: str
    activity_type: ActivityType
    session_user: str
    target: Optional[str]  # Hedef username, hashtag vs.
    scheduled_time: float  # Unix timestamp
    status: ActivityStatus
    created_at: float
    completed_at: Optional[float] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    metadata: Optional[Dict[str, Any]] = None

class ActivityScheduler:
    """Instagram aktivitelerini planlayan ve yöneten sınıf"""
    
    def __init__(self, config, session_manager):
        self.config = config
        self.session_manager = session_manager
        self.activities: List[ScheduledActivity] = []
        self.daily_counts: Dict[str, Dict[str, int]] = {}  # user -> activity_type -> count
        self.lock = threading.Lock()
        self.is_running = False
        self.scheduler_thread = None
        
        self.logger = logging.getLogger(__name__)
        
        # Callback fonksiyonları (activity executor'lar tarafından set edilecek)
        self.activity_executors: Dict[ActivityType, Callable] = {}
        
        self._load_daily_counts()
    
    def register_activity_executor(self, activity_type: ActivityType, executor: Callable) -> None:
        """Aktivite executor'ını kaydet"""
        self.activity_executors[activity_type] = executor
        self.logger.info(f"Registered executor for {activity_type.value}")
    
    def _load_daily_counts(self) -> None:
        """Günlük sayaçları yükle"""
        today = datetime.now().strftime('%Y-%m-%d')
        # Her gün sıfırlansın
        self.daily_counts = {}
    
    def _get_daily_count(self, user: str, activity_type: ActivityType) -> int:
        """Kullanıcının günlük aktivite sayısını döner"""
        today = datetime.now().strftime('%Y-%m-%d')
        if today not in self.daily_counts:
            self.daily_counts[today] = {}
        if user not in self.daily_counts[today]:
            self.daily_counts[today][user] = {}
        return self.daily_counts[today][user].get(activity_type.value, 0)
    
    def _increment_daily_count(self, user: str, activity_type: ActivityType) -> None:
        """Günlük aktivite sayısını artır"""
        today = datetime.now().strftime('%Y-%m-%d')
        if today not in self.daily_counts:
            self.daily_counts[today] = {}
        if user not in self.daily_counts[today]:
            self.daily_counts[today][user] = {}
        
        current = self.daily_counts[today][user].get(activity_type.value, 0)
        self.daily_counts[today][user][activity_type.value] = current + 1
    
    def _get_daily_limit(self, activity_type: ActivityType) -> int:
        """Aktivite türü için günlük limiti döner"""
        limits = {
            ActivityType.LIKE: self.config.DAILY_LIKES_LIMIT,
            ActivityType.FOLLOW: self.config.DAILY_FOLLOWS_LIMIT,
            ActivityType.UNFOLLOW: self.config.DAILY_UNFOLLOWS_LIMIT,
            ActivityType.COMMENT: self.config.DAILY_COMMENTS_LIMIT,
            ActivityType.STORY_VIEW: self.config.DAILY_STORY_VIEWS_LIMIT,
            ActivityType.PROFILE_VISIT: self.config.DAILY_PROFILE_VISITS_LIMIT,
            ActivityType.EXPLORE_BROWSE: 50,  # Varsayılan
            ActivityType.SESSION_KEEPALIVE: 100  # Varsayılan
        }
        return limits.get(activity_type, 10)
    
    def can_schedule_activity(self, user: str, activity_type: ActivityType) -> bool:
        """Aktivite zamanlanabilir mi?"""
        daily_count = self._get_daily_count(user, activity_type)
        daily_limit = self._get_daily_limit(activity_type)
        
        return daily_count < daily_limit
    
    def schedule_activity(self, activity_type: ActivityType, session_user: str, 
                         target: Optional[str] = None, delay_seconds: int = 0,
                         metadata: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Aktivite zamanla"""
        
        if not self.can_schedule_activity(session_user, activity_type):
            self.logger.warning(f"Daily limit reached for {session_user}, {activity_type.value}")
            return None
        
        activity_id = f"{activity_type.value}_{session_user}_{int(time.time())}_{random.randint(1000, 9999)}"
        
        scheduled_time = time.time() + delay_seconds
        
        activity = ScheduledActivity(
            id=activity_id,
            activity_type=activity_type,
            session_user=session_user,
            target=target,
            scheduled_time=scheduled_time,
            status=ActivityStatus.PENDING,
            created_at=time.time(),
            metadata=metadata or {}
        )
        
        with self.lock:
            self.activities.append(activity)
        
        self.logger.info(f"Scheduled {activity_type.value} for {session_user} at {datetime.fromtimestamp(scheduled_time)}")
        return activity_id
    
    def schedule_random_activity(self, session_user: str) -> Optional[str]:
        """Rastgele aktivite zamanla"""
        available_activities = []
        
        # Hangi aktiviteler yapılabilir?
        activity_probabilities = {
            ActivityType.LIKE: self.config.LIKE_PROBABILITY,
            ActivityType.FOLLOW: self.config.FOLLOW_PROBABILITY,
            ActivityType.COMMENT: self.config.COMMENT_PROBABILITY,
            ActivityType.STORY_VIEW: self.config.STORY_VIEW_PROBABILITY,
            ActivityType.PROFILE_VISIT: self.config.PROFILE_VISIT_PROBABILITY,
            ActivityType.EXPLORE_BROWSE: 0.4
        }
        
        for activity_type, probability in activity_probabilities.items():
            if self.can_schedule_activity(session_user, activity_type) and random.random() < probability:
                available_activities.append(activity_type)
        
        if not available_activities:
            return None
        
        # Rastgele aktivite seç
        activity_type = random.choice(available_activities)
        
        # Rastgele gecikme
        delay = random.randint(self.config.MIN_ACTION_DELAY, self.config.MAX_ACTION_DELAY * 10)
        
        # Hedef seç (gerekirse)
        target = None
        if activity_type in [ActivityType.FOLLOW, ActivityType.PROFILE_VISIT]:
            target = random.choice(self.config.TARGET_HASHTAGS) if self.config.TARGET_HASHTAGS else None
        
        return self.schedule_activity(activity_type, session_user, target, delay)
    
    def schedule_keepalive_session(self, session_user: str) -> Optional[str]:
        """Session keep-alive aktivitesi zamanla"""
        # Bir sonraki keep-alive için rastgele zaman (30-60 dakika)
        delay = random.randint(1800, 3600)  
        
        return self.schedule_activity(
            ActivityType.SESSION_KEEPALIVE,
            session_user,
            delay_seconds=delay,
            metadata={"type": "keepalive"}
        )
    
    def get_pending_activities(self) -> List[ScheduledActivity]:
        """Bekleyen aktiviteleri döner"""
        current_time = time.time()
        with self.lock:
            return [
                activity for activity in self.activities
                if activity.status == ActivityStatus.PENDING and activity.scheduled_time <= current_time
            ]
    
    def get_activity_by_id(self, activity_id: str) -> Optional[ScheduledActivity]:
        """ID'ye göre aktivite döner"""
        with self.lock:
            for activity in self.activities:
                if activity.id == activity_id:
                    return activity
        return None
    
    def update_activity_status(self, activity_id: str, status: ActivityStatus, 
                              error_message: Optional[str] = None) -> bool:
        """Aktivite durumunu güncelle"""
        with self.lock:
            for activity in self.activities:
                if activity.id == activity_id:
                    activity.status = status
                    if error_message:
                        activity.error_message = error_message
                    if status in [ActivityStatus.COMPLETED, ActivityStatus.FAILED]:
                        activity.completed_at = time.time()
                    
                    # Başarılı aktivitelerin günlük sayısını artır
                    if status == ActivityStatus.COMPLETED:
                        self._increment_daily_count(activity.session_user, activity.activity_type)
                    
                    self.logger.info(f"Activity {activity_id} status updated to {status.value}")
                    return True
        return False
    
    def retry_activity(self, activity_id: str) -> bool:
        """Aktiviteyi yeniden dene"""
        with self.lock:
            for activity in self.activities:
                if activity.id == activity_id and activity.status == ActivityStatus.FAILED:
                    if activity.retry_count < activity.max_retries:
                        activity.retry_count += 1
                        activity.status = ActivityStatus.PENDING
                        activity.scheduled_time = time.time() + random.randint(300, 900)  # 5-15 dakika
                        activity.error_message = None
                        self.logger.info(f"Retrying activity {activity_id} (attempt {activity.retry_count})")
                        return True
        return False
    
    def cancel_activity(self, activity_id: str) -> bool:
        """Aktiviteyi iptal et"""
        return self.update_activity_status(activity_id, ActivityStatus.CANCELLED)
    
    def cleanup_old_activities(self, hours: int = 24) -> int:
        """Eski aktiviteleri temizle"""
        cutoff_time = time.time() - (hours * 3600)
        
        with self.lock:
            original_count = len(self.activities)
            self.activities = [
                activity for activity in self.activities
                if activity.created_at > cutoff_time or activity.status == ActivityStatus.PENDING
            ]
            removed_count = original_count - len(self.activities)
        
        if removed_count > 0:
            self.logger.info(f"Cleaned up {removed_count} old activities")
        
        return removed_count
    
    def get_activity_stats(self, user: Optional[str] = None, hours: int = 24) -> Dict[str, Any]:
        """Aktivite istatistiklerini döner"""
        cutoff_time = time.time() - (hours * 3600)
        
        with self.lock:
            activities = [a for a in self.activities if a.created_at > cutoff_time]
            
            if user:
                activities = [a for a in activities if a.session_user == user]
        
        stats = {
            'total': len(activities),
            'pending': len([a for a in activities if a.status == ActivityStatus.PENDING]),
            'running': len([a for a in activities if a.status == ActivityStatus.RUNNING]),
            'completed': len([a for a in activities if a.status == ActivityStatus.COMPLETED]),
            'failed': len([a for a in activities if a.status == ActivityStatus.FAILED]),
            'cancelled': len([a for a in activities if a.status == ActivityStatus.CANCELLED]),
            'by_type': {},
            'success_rate': 0
        }
        
        # Aktivite türlerine göre groupla
        for activity_type in ActivityType:
            type_activities = [a for a in activities if a.activity_type == activity_type]
            stats['by_type'][activity_type.value] = {
                'total': len(type_activities),
                'completed': len([a for a in type_activities if a.status == ActivityStatus.COMPLETED]),
                'failed': len([a for a in type_activities if a.status == ActivityStatus.FAILED])
            }
        
        # Başarı oranı
        total_finished = stats['completed'] + stats['failed']
        if total_finished > 0:
            stats['success_rate'] = round((stats['completed'] / total_finished) * 100, 2)
        
        return stats
    
    def start_scheduler(self) -> None:
        """Scheduler'ı başlat"""
        if self.is_running:
            return
        
        self.is_running = True
        self.scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self.scheduler_thread.start()
        self.logger.info("Activity scheduler started")
    
    def stop_scheduler(self) -> None:
        """Scheduler'ı durdur"""
        self.is_running = False
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=5)
        self.logger.info("Activity scheduler stopped")
    
    def _scheduler_loop(self) -> None:
        """Ana scheduler döngüsü"""
        while self.is_running:
            try:
                # Bekleyen aktiviteleri işle
                pending_activities = self.get_pending_activities()
                
                for activity in pending_activities[:5]:  # Aynı anda max 5 aktivite
                    if not self.is_running:
                        break
                    
                    self._execute_activity(activity)
                
                # Eski aktiviteleri temizle (her saatte bir)
                if random.random() < 0.01:  # %1 şans
                    self.cleanup_old_activities()
                
                # Kısa bekleme
                time.sleep(10)
                
            except Exception as e:
                self.logger.error(f"Error in scheduler loop: {e}")
                time.sleep(30)
    
    def _execute_activity(self, activity: ScheduledActivity) -> None:
        """Aktiviteyi çalıştır"""
        self.update_activity_status(activity.id, ActivityStatus.RUNNING)
        
        try:
            # Executor'ı bul
            executor = self.activity_executors.get(activity.activity_type)
            if not executor:
                raise Exception(f"No executor found for {activity.activity_type.value}")
            
            # Aktiviteyi çalıştır
            success = executor(activity)
            
            if success:
                self.update_activity_status(activity.id, ActivityStatus.COMPLETED)
            else:
                self.update_activity_status(activity.id, ActivityStatus.FAILED, "Executor returned False")
                # Yeniden denemeyi zamanla
                self.retry_activity(activity.id)
                
        except Exception as e:
            error_msg = str(e)
            self.logger.error(f"Error executing activity {activity.id}: {error_msg}")
            self.update_activity_status(activity.id, ActivityStatus.FAILED, error_msg)
            # Yeniden denemeyi zamanla
            self.retry_activity(activity.id)
    
    def get_recent_activities(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Son aktiviteleri döner"""
        with self.lock:
            recent = sorted(self.activities, key=lambda x: x.created_at, reverse=True)[:limit]
            return [asdict(activity) for activity in recent]
    
    def schedule_bulk_keepalive(self) -> int:
        """Tüm aktif session'lar için keep-alive zamanla"""
        sessions = self.session_manager.get_healthy_sessions()
        scheduled_count = 0
        
        for session in sessions:
            user = session.get('user')
            if user and self.schedule_keepalive_session(user):
                scheduled_count += 1
        
        self.logger.info(f"Scheduled keep-alive for {scheduled_count} sessions")
        return scheduled_count