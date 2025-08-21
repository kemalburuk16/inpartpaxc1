# -*- coding: utf-8 -*-
"""
Human Behavior Simulation
Instagram'da insan benzeri davranışları simüle eder.
"""

import random
import time
import math
from typing import Tuple, List
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.remote.webdriver import WebDriver

class HumanBehavior:
    """İnsan benzeri davranış simülasyonu"""
    
    def __init__(self, driver: WebDriver):
        self.driver = driver
        self.action_chains = ActionChains(driver)
    
    def random_delay(self, min_seconds: float = 1.0, max_seconds: float = 3.0) -> None:
        """Rastgele gecikme"""
        delay = random.uniform(min_seconds, max_seconds)
        time.sleep(delay)
    
    def human_type(self, element, text: str, typing_speed: float = 0.1) -> None:
        """İnsan benzeri yazma simülasyonu"""
        element.clear()
        for char in text:
            element.send_keys(char)
            # Rastgele yazma hızı
            delay = random.uniform(typing_speed * 0.5, typing_speed * 2.0)
            time.sleep(delay)
            
            # Bazen backspace yapıp düzelt
            if random.random() < 0.02:  # %2 hata oranı
                element.send_keys('\b')
                time.sleep(random.uniform(0.1, 0.3))
                element.send_keys(char)
    
    def human_scroll(self, pixels: int = None, duration: float = 2.0) -> None:
        """İnsan benzeri scroll"""
        if pixels is None:
            pixels = random.randint(200, 800)
        
        # Scroll'u küçük parçalara böl
        steps = random.randint(10, 20)
        pixel_per_step = pixels // steps
        step_delay = duration / steps
        
        for _ in range(steps):
            self.driver.execute_script(f"window.scrollBy(0, {pixel_per_step});")
            time.sleep(step_delay + random.uniform(-step_delay*0.3, step_delay*0.3))
    
    def human_mouse_movement(self, element) -> None:
        """İnsan benzeri mouse hareketi"""
        # Elementin konumunu al
        location = element.location
        size = element.size
        
        # Hedef noktayı hesapla (elementin ortasına yakın rastgele nokta)
        target_x = location['x'] + random.randint(size['width']//4, 3*size['width']//4)
        target_y = location['y'] + random.randint(size['height']//4, 3*size['height']//4)
        
        # Mevcut mouse pozisyonundan hedefe eğrisel hareket
        current_x, current_y = 0, 0  # Varsayılan başlangıç
        
        # Bezier eğrisi ile hareket simülasyonu
        steps = random.randint(20, 40)
        for i in range(steps):
            t = i / steps
            # Eğrisel hareket için ara noktalar
            mid_x = current_x + (target_x - current_x) * t + random.randint(-10, 10)
            mid_y = current_y + (target_y - current_y) * t + random.randint(-10, 10)
            
            self.action_chains.move_by_offset(
                mid_x - current_x if i > 0 else 0, 
                mid_y - current_y if i > 0 else 0
            ).perform()
            
            current_x, current_y = mid_x, mid_y
            time.sleep(random.uniform(0.01, 0.03))
    
    def human_click(self, element, click_type: str = "single") -> None:
        """İnsan benzeri tıklama"""
        # Mouse'u elemente götür
        self.human_mouse_movement(element)
        
        # Küçük bir bekleme
        self.random_delay(0.1, 0.3)
        
        if click_type == "single":
            element.click()
        elif click_type == "double":
            self.action_chains.double_click(element).perform()
        
        # Tıklama sonrası küçük gecikme
        self.random_delay(0.2, 0.5)
    
    def reading_behavior(self, duration: float = None) -> None:
        """Okuma davranışı simülasyonu"""
        if duration is None:
            duration = random.uniform(2.0, 8.0)
        
        # Okuma sırasında küçük scroll'lar
        steps = random.randint(3, 8)
        step_duration = duration / steps
        
        for _ in range(steps):
            # Bazen küçük scroll
            if random.random() < 0.7:
                self.human_scroll(random.randint(50, 200), random.uniform(0.5, 1.5))
            
            time.sleep(step_duration + random.uniform(-step_duration*0.2, step_duration*0.2))
    
    def browse_behavior(self, min_time: float = 5.0, max_time: float = 15.0) -> None:
        """Gezinme davranışı"""
        browse_time = random.uniform(min_time, max_time)
        
        # Rastgele scroll'lar ve beklemeler
        end_time = time.time() + browse_time
        while time.time() < end_time:
            action = random.choice(['scroll_down', 'scroll_up', 'pause', 'small_scroll'])
            
            if action == 'scroll_down':
                self.human_scroll(random.randint(300, 600), random.uniform(1.5, 3.0))
            elif action == 'scroll_up':
                self.human_scroll(-random.randint(100, 300), random.uniform(1.0, 2.0))
            elif action == 'pause':
                self.reading_behavior(random.uniform(1.0, 4.0))
            elif action == 'small_scroll':
                self.human_scroll(random.randint(100, 200), random.uniform(0.8, 1.5))
            
            # Aktiviteler arası gecikme
            self.random_delay(0.5, 2.0)
    
    def simulate_human_session(self, min_duration: float = 300, max_duration: float = 900) -> None:
        """Tam bir insan session'ı simülasyonu"""
        session_duration = random.uniform(min_duration, max_duration)
        end_time = time.time() + session_duration
        
        while time.time() < end_time:
            # Rastgele aktiviteler
            activities = [
                'browse', 'read', 'scroll', 'pause', 'explore'
            ]
            
            activity = random.choice(activities)
            
            if activity == 'browse':
                self.browse_behavior(5.0, 20.0)
            elif activity == 'read':
                self.reading_behavior(3.0, 10.0)
            elif activity == 'scroll':
                self.human_scroll(random.randint(400, 1000), random.uniform(2.0, 5.0))
            elif activity == 'pause':
                self.random_delay(2.0, 8.0)
            elif activity == 'explore':
                # Sayfada rastgele noktalara bakmak
                for _ in range(random.randint(2, 5)):
                    x = random.randint(100, 800)
                    y = random.randint(100, 600)
                    self.action_chains.move_by_offset(x, y).perform()
                    self.random_delay(0.5, 2.0)
            
            # Aktiviteler arası uzun gecikme
            self.random_delay(3.0, 10.0)
    
    def get_random_comment(self, comment_list: List[str]) -> str:
        """Rastgele yorum seç"""
        return random.choice(comment_list)
    
    def should_perform_action(self, probability: float) -> bool:
        """Verilen olasılıkla aksiyon alıp almayacağını belirle"""
        return random.random() < probability
    
    def get_human_like_delay(self) -> float:
        """İnsan benzeri gecikme süresi hesapla"""
        # Normal dağılım ile daha gerçekçi gecikme
        mean = 3.0
        std_dev = 1.5
        delay = max(0.5, random.normalvariate(mean, std_dev))
        return delay
    
    def simulate_thinking(self, min_time: float = 1.0, max_time: float = 5.0) -> None:
        """Düşünme/karar verme simülasyonu"""
        think_time = random.uniform(min_time, max_time)
        
        # Düşünme sırasında küçük hareketler
        steps = random.randint(2, 6)
        step_time = think_time / steps
        
        for _ in range(steps):
            # Bazen küçük mouse hareketi
            if random.random() < 0.3:
                self.action_chains.move_by_offset(
                    random.randint(-20, 20), 
                    random.randint(-20, 20)
                ).perform()
            
            time.sleep(step_time)
    
    def check_for_suspicious_elements(self) -> bool:
        """Şüpheli elementleri kontrol et (captcha, uyarı vs.)"""
        suspicious_texts = [
            "robot", "captcha", "verification", "suspicious", 
            "blocked", "temporarily", "try again", "error"
        ]
        
        page_text = self.driver.page_source.lower()
        
        for text in suspicious_texts:
            if text in page_text:
                return True
        
        return False