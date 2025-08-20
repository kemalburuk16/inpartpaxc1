import os
import sys
import time
import logging
from datetime import datetime

# Add src directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from instagram_client import InstagramClient
from like_manager import LikeManager
from follow_manager import FollowManager
from utils import load_config, setup_logging

def main():
    """Ana uygulama giriş noktası"""
    
    # Logging kurulumu
    setup_logging()
    logger = logging.getLogger(__name__)
    
    logger.info("Instagram Auto Like/Follow System başlatılıyor...")
    
    try:
        # Konfigürasyon yükle
        config = load_config()
        
        # Instagram client oluştur
        instagram_client = InstagramClient(config)
        
        # Yöneticileri başlat
        like_manager = LikeManager(instagram_client, config)
        follow_manager = FollowManager(instagram_client, config)
        
        logger.info("Sistem başarıyla başlatıldı!")
        
        # Ana döngü
        while True:
            try:
                # Auto-like işlemleri
                if config.get('auto_like', {}).get('enabled', False):
                    like_manager.run()
                
                # Auto-follow işlemleri  
                if config.get('auto_follow', {}).get('enabled', False):
                    follow_manager.run()
                
                # Bekleme süresi
                sleep_time = config.get('general', {}).get('cycle_delay', 300)
                logger.info(f"{sleep_time} saniye bekleniyor...")
                time.sleep(sleep_time)
                
            except KeyboardInterrupt:
                logger.info("Kullanıcı tarafından durduruldu.")
                break
            except Exception as e:
                logger.error(f"Döngü hatası: {str(e)}")
                time.sleep(60)  # Hata durumunda 1 dakika bekle
                
    except Exception as e:
        logger.error(f"Sistem başlatma hatası: {str(e)}")
        return 1
    
    logger.info("Sistem kapatılıyor...")
    return 0

if __name__ == "__main__":
    exit(main())
