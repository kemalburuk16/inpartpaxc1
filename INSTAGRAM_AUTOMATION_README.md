# Instagram Otomasyon Sistemi Dokümantasyonu

## Genel Bakış

InstaVido projesine entegre edilmiş kapsamlı Instagram otomasyon sistemi. Bu sistem session'ları canlı tutmak ve insansı aktiviteler gerçekleştirmek için tasarlanmıştır.

## Ana Özellikler

### 🤖 Otomasyon Aktiviteleri
- **Beğenme:** Rastgele gönderileri beğenme
- **Takip Etme:** Hedef kullanıcıları takip etme/takibi bırakma  
- **Yorum Yapma:** Önceden hazırlanmış metinlerle yorum yapma
- **Story İzleme:** Aktif story'leri izleme
- **Keşfet Gezintisi:** Explore sayfasında gezinme
- **Profil Ziyaretleri:** Rastgele profilleri ziyaret etme
- **Session Keep-Alive:** Oturumları canlı tutma

### 🛡️ Güvenlik Özellikleri
- Instagram'ın bot tespitinden kaçınma
- Rastgele gecikme süreleri (2-8 saniye)
- İnsan benzeri mouse hareketleri
- Session rotation sistemi
- Aktivite sınırları ve cooldown'lar
- Günlük limit kontrolleri

### 📊 Yönetim Paneli
- Ana otomasyon kontrol paneli
- Session durumlarını görüntüleme ve yönetme
- Gerçek zamanlı aktivite logları
- Manuel aktivite tetikleme
- Session güncelleme ve senkronizasyon

## Kurulum ve Yapılandırma

### Gereksinimler
```bash
pip install selenium webdriver-manager flask flask-session
```

### Dosya Yapısı
```
adminpanel/
├── automation/
│   ├── __init__.py
│   ├── instagram_bot.py          # Ana bot sınıfı
│   ├── session_manager.py        # Session yönetimi
│   ├── activity_scheduler.py     # Aktivite planlayıcısı
│   ├── human_behavior.py         # İnsansı davranış simülasyonu
│   └── config.py                 # Otomasyon ayarları
├── templates/admin/
│   ├── automation_dashboard.html # Ana otomasyon kontrol paneli
│   ├── automation_sessions.html  # Session yönetimi sayfası
│   └── activity_logs.html        # Aktivite logları
├── static/admin/
│   ├── automation.js             # Frontend JavaScript
│   └── automation.css            # Stil dosyaları
└── automation_views.py           # Flask route'ları
```

## Kullanım Kılavuzu

### 1. Admin Panel Erişimi
- Ana URL: `/srdr-proadmin/automation`
- Giriş: Admin kullanıcı adı ve şifre ile

### 2. Session Yönetimi
- **Session Listesi:** Tüm Instagram session'larını görüntüleme
- **Sağlık Kontrolü:** Session'ların durumunu test etme
- **Keep-Alive:** Session'ları canlı tutma aktiviteleri

### 3. Aktivite Planlama
- **Manuel Aktivite:** Belirli aktivite türleri zamanlamak
- **Rastgele Aktivite:** Sistem tarafından otomatik seçim
- **Toplu İşlemler:** Tüm session'lar için aynı anda

### 4. İzleme ve Raporlama
- **Gerçek Zamanlı:** Anlık aktivite durumu
- **İstatistikler:** Başarı oranları ve performans
- **Loglar:** Detaylı aktivite geçmişi

## API Endpoints

### Durum ve Bilgi
```
GET /srdr-proadmin/api/automation/status
GET /srdr-proadmin/api/automation/sessions  
GET /srdr-proadmin/api/automation/activities
```

### Aktivite Yönetimi
```
POST /srdr-proadmin/api/automation/schedule-activity
POST /srdr-proadmin/api/automation/schedule-random
POST /srdr-proadmin/api/automation/schedule-keepalive
POST /srdr-proadmin/api/automation/cancel-activity
POST /srdr-proadmin/api/automation/retry-activity
```

### Sistem Kontrolü
```
POST /srdr-proadmin/api/automation/start-scheduler
POST /srdr-proadmin/api/automation/stop-scheduler
POST /srdr-proadmin/api/automation/test-session
```

## Yapılandırma

### Günlük Limitler
```python
DAILY_LIKES_LIMIT = 200          # Günlük beğeni limiti
DAILY_FOLLOWS_LIMIT = 50         # Günlük takip limiti  
DAILY_COMMENTS_LIMIT = 30        # Günlük yorum limiti
DAILY_STORY_VIEWS_LIMIT = 100    # Günlük story izleme limiti
```

### Aktivite Olasılıkları
```python
LIKE_PROBABILITY = 0.7           # %70 beğeni olasılığı
FOLLOW_PROBABILITY = 0.3         # %30 takip olasılığı
COMMENT_PROBABILITY = 0.1        # %10 yorum olasılığı
```

### Gecikme Ayarları
```python
MIN_ACTION_DELAY = 2             # Minimum 2 saniye
MAX_ACTION_DELAY = 8             # Maksimum 8 saniye
```

### Yorum Metinleri
```python
COMMENT_TEXTS = [
    "Harika! 👏",
    "Çok güzel ❤️", 
    "Süper! 🔥",
    "Muhteşem paylaşım",
    "Tebrikler! 🎉",
    "Bayıldım! 😍"
]
```

## Güvenlik ve En İyi Uygulamalar

### 1. Rate Limiting
- Aktiviteler arası otomatik gecikmeler
- Günlük aktivite limitleri
- Session cooldown süreleri

### 2. Bot Tespitinden Kaçınma
- İnsan benzeri mouse hareketleri
- Rastgele scroll davranışları  
- Değişken yazma hızları
- Düşünme simülasyonu

### 3. Session Koruması
- Hata durumunda otomatik session değiştirme
- Başarısız session'ları karantinaya alma
- Düzenli sağlık kontrolleri

### 4. İzleme ve Uyarılar
- Şüpheli aktivite tespiti
- Captcha ve engel kontrolü
- Başarı oranı takibi

## Sorun Giderme

### Session Problemleri
```python
# Session test etme
POST /srdr-proadmin/api/automation/test-session
{
    "session_user": "username"
}
```

### Aktivite Problemleri
```python
# Başarısız aktiviteyi yeniden deneme
POST /srdr-proadmin/api/automation/retry-activity
{
    "activity_id": "activity_id"
}
```

### Sistem Performansı
- Chrome WebDriver memory kullanımı
- Session dosyası boyutu
- Log dosyası temizliği

## Gelişmiş Özellikler

### 1. Proxy Desteği
```python
USE_PROXY = True
PROXY_ROTATION = True
```

### 2. Özel Hedefleme
```python
TARGET_HASHTAGS = [
    "#photography",
    "#art", 
    "#nature"
]
```

### 3. Yasaklı İçerik Filtresi
```python
BANNED_KEYWORDS = [
    "spam",
    "fake", 
    "bot"
]
```

## Test ve Doğrulama

### Sistem Testi
```bash
cd /home/runner/work/inpartpaxc1/inpartpaxc1
python /tmp/test_automation.py
```

### Demo Çalıştırma
```bash
python /tmp/automation_demo.py
```

### Örnek Test Sonuçları
```
🚀 Instagram Automation System Test
==================================================
🔧 Testing AutomationConfig...
  ✓ Daily likes limit: 200
  ✓ Chrome options: 10 options
  ✓ Config dict has 34 parameters

👥 Testing AutomationSessionManager...
  ✓ Found 4 available sessions
  ✓ Session stats: active=4, blocked=0, invalid=3

📅 Testing ActivityScheduler...
  ✓ Scheduled activity successfully
  ✓ Activity stats tracking working

🤖 Testing HumanBehavior...
  ✓ Random delays and behaviors working
  ✓ Suspicious content detection working

==================================================
📊 Test Results: 5/5 tests passed
✅ All tests passed! Automation system is ready.
```

## Sonuç

Bu Instagram otomasyon sistemi, InstaVido projesinin session'larını güvenli bir şekilde canlı tutmak ve organik görünümlü aktiviteler gerçekleştirmek için kapsamlı bir çözüm sunar. Sistem production ortamında kullanıma hazırdır ve mevcut altyapıyı bozmadan entegre edilmiştir.

**Önemli:** Bu sistem sadece session'ları canlı tutmak ve meşru kullanım amaçları için tasarlanmıştır. Instagram'ın kullanım koşullarına uygun şekilde kullanılmalıdır.