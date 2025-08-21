# -*- coding: utf-8 -*-
"""
Instagram Automation Configuration
Tüm otomasyon ayarları ve parametreleri burada tanımlanır.
"""

import os
from typing import List, Dict, Any

class AutomationConfig:
    """Instagram otomasyon sistemi konfigürasyonu"""
    
    # Temel ayarlar
    ENABLE_AUTOMATION = True
    HEADLESS_MODE = True
    
    # WebDriver ayarları
    WEBDRIVER_TIMEOUT = 30
    PAGE_LOAD_TIMEOUT = 60
    IMPLICIT_WAIT = 10
    
    # Gecikme ayarları (saniye)
    MIN_ACTION_DELAY = 2
    MAX_ACTION_DELAY = 8
    MIN_PAGE_DELAY = 3
    MAX_PAGE_DELAY = 12
    
    # Günlük limitler
    DAILY_LIKES_LIMIT = 200
    DAILY_FOLLOWS_LIMIT = 50
    DAILY_UNFOLLOWS_LIMIT = 50
    DAILY_COMMENTS_LIMIT = 30
    DAILY_STORY_VIEWS_LIMIT = 100
    DAILY_PROFILE_VISITS_LIMIT = 150
    
    # Aktivite oranları (0.0 - 1.0)
    LIKE_PROBABILITY = 0.7
    FOLLOW_PROBABILITY = 0.3
    COMMENT_PROBABILITY = 0.1
    STORY_VIEW_PROBABILITY = 0.8
    PROFILE_VISIT_PROBABILITY = 0.5
    
    # Session yönetimi
    SESSION_ROTATION_INTERVAL = 300  # 5 dakika
    SESSION_HEALTH_CHECK_INTERVAL = 600  # 10 dakika
    SESSION_COOLDOWN_TIME = 1800  # 30 dakika
    
    # Güvenlik ayarları
    ENABLE_RATE_LIMITING = True
    ENABLE_HUMAN_BEHAVIOR = True
    ENABLE_RANDOM_DELAYS = True
    DETECT_CAPTCHA = True
    
    # Proxy ayarları
    USE_PROXY = False
    PROXY_ROTATION = False
    
    # Yorum metinleri
    COMMENT_TEXTS = [
        "Harika! 👏",
        "Çok güzel ❤️", 
        "Süper! 🔥",
        "Muhteşem paylaşım",
        "Tebrikler! 🎉",
        "Bayıldım! 😍",
        "Ne kadar güzel 🌟",
        "Mükemmel! ✨",
        "Çok beğendim 👍",
        "Enfes paylaşım 💫",
        "Harikasın! 💖",
        "Ellerine sağlık 🙌"
    ]
    
    # Hedef kullanıcı hashtag'leri
    TARGET_HASHTAGS = [
        "#instagram",
        "#photography", 
        "#photo",
        "#art",
        "#nature",
        "#travel",
        "#lifestyle",
        "#fashion",
        "#food",
        "#music"
    ]
    
    # Yasaklı kelimeler (bu kelimeler içeren postlara aktivite yapılmaz)
    BANNED_KEYWORDS = [
        "spam",
        "fake",
        "bot",
        "follow4follow",
        "like4like",
        "adult",
        "nsfw"
    ]
    
    # Log ayarları
    LOG_LEVEL = "INFO"
    LOG_FILE = "/tmp/instagram_automation.log"
    LOG_MAX_SIZE = 10 * 1024 * 1024  # 10MB
    LOG_BACKUP_COUNT = 5
    
    @classmethod
    def get_chrome_options(cls) -> List[str]:
        """Chrome WebDriver için seçenekler"""
        options = [
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-extensions",
            "--disable-plugins",
            "--disable-images",
            "--disable-javascript",
            "--window-size=1366,768",
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ]
        
        if cls.HEADLESS_MODE:
            options.append("--headless")
            
        return options
    
    @classmethod
    def get_config_dict(cls) -> Dict[str, Any]:
        """Tüm konfigürasyonu dict olarak döner"""
        return {
            "enable_automation": cls.ENABLE_AUTOMATION,
            "headless_mode": cls.HEADLESS_MODE,
            "webdriver_timeout": cls.WEBDRIVER_TIMEOUT,
            "page_load_timeout": cls.PAGE_LOAD_TIMEOUT,
            "implicit_wait": cls.IMPLICIT_WAIT,
            "min_action_delay": cls.MIN_ACTION_DELAY,
            "max_action_delay": cls.MAX_ACTION_DELAY,
            "min_page_delay": cls.MIN_PAGE_DELAY,
            "max_page_delay": cls.MAX_PAGE_DELAY,
            "daily_likes_limit": cls.DAILY_LIKES_LIMIT,
            "daily_follows_limit": cls.DAILY_FOLLOWS_LIMIT,
            "daily_unfollows_limit": cls.DAILY_UNFOLLOWS_LIMIT,
            "daily_comments_limit": cls.DAILY_COMMENTS_LIMIT,
            "daily_story_views_limit": cls.DAILY_STORY_VIEWS_LIMIT,
            "daily_profile_visits_limit": cls.DAILY_PROFILE_VISITS_LIMIT,
            "like_probability": cls.LIKE_PROBABILITY,
            "follow_probability": cls.FOLLOW_PROBABILITY,
            "comment_probability": cls.COMMENT_PROBABILITY,
            "story_view_probability": cls.STORY_VIEW_PROBABILITY,
            "profile_visit_probability": cls.PROFILE_VISIT_PROBABILITY,
            "session_rotation_interval": cls.SESSION_ROTATION_INTERVAL,
            "session_health_check_interval": cls.SESSION_HEALTH_CHECK_INTERVAL,
            "session_cooldown_time": cls.SESSION_COOLDOWN_TIME,
            "enable_rate_limiting": cls.ENABLE_RATE_LIMITING,
            "enable_human_behavior": cls.ENABLE_HUMAN_BEHAVIOR,
            "enable_random_delays": cls.ENABLE_RANDOM_DELAYS,
            "detect_captcha": cls.DETECT_CAPTCHA,
            "use_proxy": cls.USE_PROXY,
            "proxy_rotation": cls.PROXY_ROTATION,
            "comment_texts": cls.COMMENT_TEXTS,
            "target_hashtags": cls.TARGET_HASHTAGS,
            "banned_keywords": cls.BANNED_KEYWORDS,
            "log_level": cls.LOG_LEVEL,
            "log_file": cls.LOG_FILE
        }