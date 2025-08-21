# -*- coding: utf-8 -*-
"""
Instagram Bot - Ana otomasyon sınıfı
Selenium WebDriver kullanarak Instagram'da insansı aktiviteler gerçekleştirir.
"""

import time
import random
import logging
import json
import re
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from urllib.parse import urlparse

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException, WebDriverException,
    ElementClickInterceptedException, ElementNotInteractableException
)
from webdriver_manager.chrome import ChromeDriverManager

from .config import AutomationConfig
from .human_behavior import HumanBehavior
from .session_manager import AutomationSessionManager

class InstagramBot:
    """Instagram otomasyon bot'u"""
    
    def __init__(self, config: AutomationConfig, session_manager: AutomationSessionManager):
        self.config = config
        self.session_manager = session_manager
        self.driver = None
        self.human_behavior = None
        self.current_session = None
        self.is_logged_in = False
        self.login_attempts = 0
        self.max_login_attempts = 3
        
        self.logger = logging.getLogger(__name__)
        self._setup_logging()
        
        # Instagram selectors
        self.selectors = {
            'login_username': 'input[name="username"]',
            'login_password': 'input[name="password"]', 
            'login_button': 'button[type="submit"]',
            'home_feed': 'main[role="main"]',
            'like_button': 'svg[aria-label*="Like"]',
            'unlike_button': 'svg[aria-label*="Unlike"]',
            'follow_button': 'button:has-text("Follow")',
            'unfollow_button': 'button:has-text("Following")',
            'comment_input': 'textarea[placeholder*="comment"]',
            'comment_submit': 'button[type="submit"]',
            'story_viewer': 'div[role="button"][style*="cursor"]',
            'explore_link': 'a[href="/explore/"]',
            'profile_picture': 'img[data-testid="user-avatar"]',
            'post_link': 'a[href*="/p/"]',
            'next_button': 'button[aria-label*="Next"]',
            'close_button': 'button[aria-label*="Close"]'
        }
    
    def _setup_logging(self) -> None:
        """Logging yapılandırması"""
        log_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        file_handler = logging.FileHandler(self.config.LOG_FILE, encoding='utf-8')
        file_handler.setFormatter(log_formatter)
        file_handler.setLevel(getattr(logging, self.config.LOG_LEVEL))
        
        if not self.logger.handlers:
            self.logger.addHandler(file_handler)
            self.logger.setLevel(getattr(logging, self.config.LOG_LEVEL))
    
    def _create_driver(self) -> webdriver.Chrome:
        """Chrome WebDriver oluştur"""
        try:
            chrome_options = Options()
            
            # Temel seçenekler
            for option in self.config.get_chrome_options():
                chrome_options.add_argument(option)
            
            # Ek güvenlik ve performans ayarları
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            chrome_options.add_experimental_option("prefs", {
                "profile.default_content_setting_values.notifications": 2,
                "profile.default_content_settings.popups": 0,
                "profile.managed_default_content_settings.images": 2
            })
            
            # WebDriver manager ile ChromeDriver indir
            service = Service(ChromeDriverManager().install())
            
            driver = webdriver.Chrome(service=service, options=chrome_options)
            
            # Timeouts
            driver.set_page_load_timeout(self.config.PAGE_LOAD_TIMEOUT)
            driver.implicitly_wait(self.config.IMPLICIT_WAIT)
            
            # Fingerprint karşıtı script
            driver.execute_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined,
                });
            """)
            
            self.logger.info("Chrome WebDriver created successfully")
            return driver
            
        except Exception as e:
            self.logger.error(f"Error creating WebDriver: {e}")
            raise
    
    def start_session(self, session: Optional[Dict[str, Any]] = None) -> bool:
        """Bot session'ını başlat"""
        try:
            if self.driver:
                self.quit()
            
            self.driver = self._create_driver()
            self.human_behavior = HumanBehavior(self.driver)
            
            if session:
                return self._login_with_session(session)
            else:
                # Rastgele session seç
                session = self.session_manager.get_next_session()
                if not session:
                    self.logger.error("No available sessions found")
                    return False
                
                return self._login_with_session(session)
                
        except Exception as e:
            self.logger.error(f"Error starting session: {e}")
            return False
    
    def _login_with_session(self, session: Dict[str, Any]) -> bool:
        """Session ile Instagram'a giriş yap"""
        try:
            self.current_session = session
            user = session.get('user', 'unknown')
            
            self.logger.info(f"Attempting login with session for user: {user}")
            
            # Instagram ana sayfasına git
            self.driver.get("https://www.instagram.com/")
            self.human_behavior.random_delay(2, 5)
            
            # Cookies ekle
            cookies = session.get('cookies', {})
            
            # Temel cookies
            basic_cookies = ['sessionid', 'ds_user_id', 'csrftoken']
            for cookie_name in basic_cookies:
                cookie_value = session.get(cookie_name) or cookies.get(cookie_name)
                if cookie_value:
                    self.driver.add_cookie({
                        'name': cookie_name,
                        'value': cookie_value,
                        'domain': '.instagram.com'
                    })
            
            # Diğer cookies
            for name, value in cookies.items():
                if name not in basic_cookies and value:
                    try:
                        self.driver.add_cookie({
                            'name': name,
                            'value': str(value),
                            'domain': '.instagram.com'
                        })
                    except Exception:
                        continue
            
            # Sayfayı yenile
            self.driver.refresh()
            self.human_behavior.random_delay(3, 6)
            
            # Giriş kontrolü
            if self._check_login_status():
                self.is_logged_in = True
                self.login_attempts = 0
                self.session_manager.mark_session_success(session)
                self.logger.info(f"Successfully logged in as {user}")
                return True
            else:
                self.login_attempts += 1
                self.session_manager.mark_session_failed(session, "login_failed")
                self.logger.warning(f"Login failed for user {user}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error during login: {e}")
            if self.current_session:
                self.session_manager.mark_session_failed(self.current_session, f"login_exception: {str(e)}")
            return False
    
    def _check_login_status(self) -> bool:
        """Giriş yapılıp yapılmadığını kontrol et"""
        try:
            # Ana feed'in varlığını kontrol et
            WebDriverWait(self.driver, 10).until(
                EC.any_of(
                    EC.presence_of_element_located((By.CSS_SELECTOR, self.selectors['home_feed'])),
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'main[role="main"]')),
                    EC.presence_of_element_located((By.XPATH, "//a[@href='/']"))
                )
            )
            
            # Login sayfası elementlerinin yokluğunu kontrol et
            login_elements = self.driver.find_elements(By.CSS_SELECTOR, self.selectors['login_username'])
            if login_elements:
                return False
            
            # URL kontrolü
            current_url = self.driver.current_url
            if 'accounts/login' in current_url:
                return False
            
            return True
            
        except TimeoutException:
            return False
        except Exception as e:
            self.logger.error(f"Error checking login status: {e}")
            return False
    
    def like_posts(self, count: int = 5) -> int:
        """Rastgele postları beğen"""
        if not self.is_logged_in:
            return 0
        
        liked_count = 0
        
        try:
            # Ana sayfaya git
            self.driver.get("https://www.instagram.com/")
            self.human_behavior.random_delay(2, 5)
            
            # Scroll ve like
            for i in range(count * 2):  # Daha fazla post bulmak için
                if liked_count >= count:
                    break
                
                # Scroll down
                self.human_behavior.human_scroll(300, 2.0)
                self.human_behavior.random_delay(1, 3)
                
                # Like butonlarını bul
                like_buttons = self.driver.find_elements(By.CSS_SELECTOR, 'svg[aria-label="Like"]')
                
                for button in like_buttons[:2]:  # Her scroll'da max 2 beğeni
                    if liked_count >= count:
                        break
                    
                    try:
                        # İnsan benzeri tıklama
                        self.human_behavior.human_click(button)
                        liked_count += 1
                        
                        self.logger.info(f"Liked post {liked_count}")
                        
                        # Beğeni arası gecikme
                        self.human_behavior.random_delay(
                            self.config.MIN_ACTION_DELAY,
                            self.config.MAX_ACTION_DELAY
                        )
                        
                    except Exception as e:
                        self.logger.warning(f"Error liking post: {e}")
                        continue
            
            if self.current_session:
                self.session_manager.add_automation_metrics(
                    self.current_session, 'like', True
                )
            
            return liked_count
            
        except Exception as e:
            self.logger.error(f"Error in like_posts: {e}")
            if self.current_session:
                self.session_manager.add_automation_metrics(
                    self.current_session, 'like', False
                )
            return liked_count
    
    def follow_users(self, hashtag: str = None, count: int = 3) -> int:
        """Kullanıcıları takip et"""
        if not self.is_logged_in:
            return 0
        
        followed_count = 0
        
        try:
            # Explore sayfasına git ya da hashtag ara
            if hashtag:
                search_url = f"https://www.instagram.com/explore/tags/{hashtag.replace('#', '')}/"
            else:
                search_url = "https://www.instagram.com/explore/"
            
            self.driver.get(search_url)
            self.human_behavior.random_delay(3, 6)
            
            # Postları bul ve profillere git
            post_links = self.driver.find_elements(By.CSS_SELECTOR, 'a[href*="/p/"]')
            
            for link in post_links[:count*2]:
                if followed_count >= count:
                    break
                
                try:
                    # Posta git
                    self.human_behavior.human_click(link)
                    self.human_behavior.random_delay(2, 4)
                    
                    # Follow butonunu bul
                    follow_buttons = self.driver.find_elements(
                        By.XPATH, "//button[contains(text(), 'Follow')]"
                    )
                    
                    if follow_buttons:
                        button = follow_buttons[0]
                        if button.is_displayed() and button.is_enabled():
                            self.human_behavior.human_click(button)
                            followed_count += 1
                            
                            self.logger.info(f"Followed user {followed_count}")
                            
                            # Follow arası gecikme
                            self.human_behavior.random_delay(
                                self.config.MIN_ACTION_DELAY * 2,
                                self.config.MAX_ACTION_DELAY * 2
                            )
                    
                    # Geri dön
                    self.driver.back()
                    self.human_behavior.random_delay(1, 3)
                    
                except Exception as e:
                    self.logger.warning(f"Error following user: {e}")
                    continue
            
            if self.current_session:
                self.session_manager.add_automation_metrics(
                    self.current_session, 'follow', True
                )
            
            return followed_count
            
        except Exception as e:
            self.logger.error(f"Error in follow_users: {e}")
            if self.current_session:
                self.session_manager.add_automation_metrics(
                    self.current_session, 'follow', False
                )
            return followed_count
    
    def comment_on_posts(self, count: int = 2) -> int:
        """Postlara yorum yap"""
        if not self.is_logged_in:
            return 0
        
        commented_count = 0
        
        try:
            # Ana sayfaya git
            self.driver.get("https://www.instagram.com/")
            self.human_behavior.random_delay(2, 5)
            
            for i in range(count * 3):  # Daha fazla post aramak için
                if commented_count >= count:
                    break
                
                # Scroll down
                self.human_behavior.human_scroll(400, 2.0)
                self.human_behavior.random_delay(2, 4)
                
                # Rastgele yorum yapma kararı
                if not self.human_behavior.should_perform_action(self.config.COMMENT_PROBABILITY):
                    continue
                
                # Comment input'unu bul
                comment_inputs = self.driver.find_elements(
                    By.CSS_SELECTOR, 'textarea[placeholder*="comment"]'
                )
                
                if comment_inputs:
                    try:
                        input_field = comment_inputs[0]
                        
                        # Rastgele yorum seç
                        comment_text = self.human_behavior.get_random_comment(
                            self.config.COMMENT_TEXTS
                        )
                        
                        # Yorumu yaz
                        self.human_behavior.human_type(input_field, comment_text)
                        self.human_behavior.random_delay(1, 2)
                        
                        # Submit et
                        submit_buttons = self.driver.find_elements(
                            By.CSS_SELECTOR, 'button[type="submit"]'
                        )
                        
                        if submit_buttons:
                            self.human_behavior.human_click(submit_buttons[0])
                            commented_count += 1
                            
                            self.logger.info(f"Commented: {comment_text}")
                            
                            # Yorum arası uzun gecikme
                            self.human_behavior.random_delay(
                                self.config.MIN_ACTION_DELAY * 3,
                                self.config.MAX_ACTION_DELAY * 3
                            )
                    
                    except Exception as e:
                        self.logger.warning(f"Error commenting: {e}")
                        continue
            
            if self.current_session:
                self.session_manager.add_automation_metrics(
                    self.current_session, 'comment', True
                )
            
            return commented_count
            
        except Exception as e:
            self.logger.error(f"Error in comment_on_posts: {e}")
            if self.current_session:
                self.session_manager.add_automation_metrics(
                    self.current_session, 'comment', False
                )
            return commented_count
    
    def view_stories(self, count: int = 5) -> int:
        """Story'leri izle"""
        if not self.is_logged_in:
            return 0
        
        viewed_count = 0
        
        try:
            # Ana sayfaya git
            self.driver.get("https://www.instagram.com/")
            self.human_behavior.random_delay(2, 5)
            
            # Story elementlerini bul
            story_elements = self.driver.find_elements(
                By.CSS_SELECTOR, 'div[role="button"][style*="cursor"]'
            )
            
            for element in story_elements[:count]:
                try:
                    # Story'yi aç
                    self.human_behavior.human_click(element)
                    
                    # Story'yi izle (rastgele süre)
                    watch_time = random.uniform(3, 8)
                    time.sleep(watch_time)
                    
                    viewed_count += 1
                    self.logger.info(f"Viewed story {viewed_count}")
                    
                    # Story'yi kapat
                    close_buttons = self.driver.find_elements(
                        By.CSS_SELECTOR, 'button[aria-label*="Close"]'
                    )
                    if close_buttons:
                        self.human_behavior.human_click(close_buttons[0])
                    
                    # Story arası gecikme
                    self.human_behavior.random_delay(2, 5)
                    
                except Exception as e:
                    self.logger.warning(f"Error viewing story: {e}")
                    continue
            
            if self.current_session:
                self.session_manager.add_automation_metrics(
                    self.current_session, 'story_view', True
                )
            
            return viewed_count
            
        except Exception as e:
            self.logger.error(f"Error in view_stories: {e}")
            if self.current_session:
                self.session_manager.add_automation_metrics(
                    self.current_session, 'story_view', False
                )
            return viewed_count
    
    def browse_explore(self, duration: int = 60) -> bool:
        """Explore sayfasında gezin"""
        if not self.is_logged_in:
            return False
        
        try:
            # Explore sayfasına git
            self.driver.get("https://www.instagram.com/explore/")
            self.human_behavior.random_delay(2, 5)
            
            # Belirtilen süre boyunca gezin
            self.human_behavior.browse_behavior(duration // 2, duration)
            
            if self.current_session:
                self.session_manager.add_automation_metrics(
                    self.current_session, 'explore_browse', True
                )
            
            self.logger.info(f"Browsed explore for {duration} seconds")
            return True
            
        except Exception as e:
            self.logger.error(f"Error browsing explore: {e}")
            if self.current_session:
                self.session_manager.add_automation_metrics(
                    self.current_session, 'explore_browse', False
                )
            return False
    
    def visit_profiles(self, count: int = 3) -> int:
        """Rastgele profilleri ziyaret et"""
        if not self.is_logged_in:
            return 0
        
        visited_count = 0
        
        try:
            # Explore'dan başla
            self.driver.get("https://www.instagram.com/explore/")
            self.human_behavior.random_delay(2, 5)
            
            # Profile linklerini bul
            profile_links = self.driver.find_elements(
                By.CSS_SELECTOR, 'a[href*="/p/"]'
            )
            
            for link in profile_links[:count*2]:
                if visited_count >= count:
                    break
                
                try:
                    # Post'a git
                    self.human_behavior.human_click(link)
                    self.human_behavior.random_delay(2, 4)
                    
                    # Profile git
                    profile_pics = self.driver.find_elements(
                        By.CSS_SELECTOR, 'img[data-testid="user-avatar"]'
                    )
                    
                    if profile_pics:
                        self.human_behavior.human_click(profile_pics[0])
                        
                        # Profile'da gez
                        self.human_behavior.browse_behavior(10, 30)
                        visited_count += 1
                        
                        self.logger.info(f"Visited profile {visited_count}")
                    
                    # Geri dön
                    self.driver.back()
                    self.human_behavior.random_delay(1, 3)
                    self.driver.back()
                    self.human_behavior.random_delay(1, 3)
                    
                except Exception as e:
                    self.logger.warning(f"Error visiting profile: {e}")
                    continue
            
            if self.current_session:
                self.session_manager.add_automation_metrics(
                    self.current_session, 'profile_visit', True
                )
            
            return visited_count
            
        except Exception as e:
            self.logger.error(f"Error visiting profiles: {e}")
            if self.current_session:
                self.session_manager.add_automation_metrics(
                    self.current_session, 'profile_visit', False
                )
            return visited_count
    
    def perform_keepalive_activity(self) -> bool:
        """Session'ı canlı tutmak için basit aktivite"""
        if not self.is_logged_in:
            return False
        
        try:
            # Ana sayfaya git
            self.driver.get("https://www.instagram.com/")
            self.human_behavior.random_delay(2, 5)
            
            # Basit gezinme
            self.human_behavior.browse_behavior(30, 60)
            
            # Bir kaç scroll
            for _ in range(3):
                self.human_behavior.human_scroll(200, 1.5)
                self.human_behavior.random_delay(2, 4)
            
            if self.current_session:
                self.session_manager.add_automation_metrics(
                    self.current_session, 'keepalive', True
                )
            
            self.logger.info("Performed keepalive activity")
            return True
            
        except Exception as e:
            self.logger.error(f"Error in keepalive activity: {e}")
            if self.current_session:
                self.session_manager.add_automation_metrics(
                    self.current_session, 'keepalive', False
                )
            return False
    
    def check_for_blocks_or_limits(self) -> bool:
        """Blok veya limit uyarılarını kontrol et"""
        try:
            page_text = self.driver.page_source.lower()
            
            warning_keywords = [
                'temporarily blocked', 'action blocked', 'try again later',
                'suspicious activity', 'we limit', 'unusual activity',
                'captcha', 'verify', 'robot'
            ]
            
            for keyword in warning_keywords:
                if keyword in page_text:
                    self.logger.warning(f"Detected potential block/limit: {keyword}")
                    return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Error checking for blocks: {e}")
            return False
    
    def quit(self) -> None:
        """WebDriver'ı kapat"""
        try:
            if self.driver:
                self.driver.quit()
                self.driver = None
                self.human_behavior = None
                self.is_logged_in = False
                self.current_session = None
                self.logger.info("WebDriver closed")
        except Exception as e:
            self.logger.error(f"Error closing WebDriver: {e}")
    
    def get_current_session_info(self) -> Optional[Dict[str, Any]]:
        """Mevcut session bilgilerini döner"""
        if self.current_session:
            return {
                'user': self.current_session.get('user'),
                'is_logged_in': self.is_logged_in,
                'login_attempts': self.login_attempts,
                'session_key': self.current_session.get('session_key')
            }
        return None
    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.quit()