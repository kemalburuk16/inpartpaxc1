# Instagram Automation System

Kapsamlı bir Instagram otomasyon sistemi - InstaVido projesi için hazırlanmış taşınabilir modül.

## Özellikler

### Ana Özellikler
- **Otomatik Instagram Aktiviteleri**: Like, takip, keşfet gezinti, feed gezinti, reels ve story görüntüleme
- **Akıllı Zamanlayıcı**: Belirlenmiş saatlerde otomatik aktivite başlatma
- **Manuel Tetikleme**: İstenildiğinde manuel aktivite başlatma
- **Session Yönetimi**: Aktif Instagram sessionlarını yönetme ve rotation
- **Güvenlik Önlemleri**: Rate limiting, human-like behavior, error handling
- **Admin Panel Entegrasyonu**: Web arayüzü ile kolay yönetim

### Aktivite Türleri
- **Feed Gezinti**: Ana sayfada dolaşma ve rastgele beğeni
- **Keşfet Gezinti**: Explore sayfasında content discovery
- **Reels Gezinti**: Reels videolarını izleme
- **Story Görüntüleme**: Kullanıcı hikayelerini görüntüleme
- **Rastgele Bekleme**: İnsan benzeri davranış için beklemeler

### Güvenlik Özellikleri
- Günlük ve session bazlı limitler
- Rastgele gecikmeler ve insan benzeri davranış
- Rate limit ve challenge detection
- Session rotation ve blocking sistemi
- Detaylı activity logging

## Kurulum

### 1. Sistem Gereksinimleri
```bash
pip install schedule requests flask
```

### 2. Klasör Yerleştirme
Projenizin ana dizininde `instavideo/` klasörünü oluşturun ve tüm dosyaları kopyalayın:

```
your_project/
├── instavideo/
│   ├── __init__.py
│   └── instagram_auto/
│       ├── __init__.py
│       ├── config.json
│       ├── session_manager.py
│       ├── activity_manager.py
│       └── scheduler.py
├── sessions.json (mevcut dosya)
├── app.py (mevcut dosya)
└── adminpanel/ (mevcut dizin)
```

### 3. Admin Panel Entegrasyonu
Admin panel template dosyasını yerleştirin:
```
adminpanel/templates/admin/instagram_automation.html
```

Admin panel base template'ine navigasyon linki eklenmiştir.

## Konfigürasyon

### config.json Ayarları

```json
{
  "activity_settings": {
    "like_probability": 0.7,        // %70 like ihtimali
    "follow_probability": 0.3,      // %30 takip ihtimali
    "story_view_probability": 0.8   // %80 story görüntüleme
  },
  "timing_settings": {
    "min_action_delay": 10,         // Eylemler arası min süre (sn)
    "max_action_delay": 30,         // Eylemler arası max süre (sn)
    "min_session_duration": 300,    // Min session süresi (sn)
    "max_session_duration": 1800    // Max session süresi (sn)
  },
  "daily_limits": {
    "max_likes_per_day": 500,       // Günlük max beğeni
    "max_follows_per_day": 100,     // Günlük max takip
    "max_story_views_per_day": 200  // Günlük max story
  },
  "scheduler_settings": {
    "auto_start": false,            // Otomatik başlatma
    "start_hour": 9,                // Başlangıç saati
    "end_hour": 21,                 // Bitiş saati
    "session_interval_minutes": 120 // Session aralığı (dk)
  }
}
```

## Kullanım

### 1. Programatic Kullanım

```python
from instavideo.instagram_auto import InstagramAuto

# Otomasyon sistemi oluştur
automation = InstagramAuto()

# 30 dakikalık otomasyon başlat
result = automation.start_automation(duration_minutes=30, session_count=2)

# Durum kontrolü
status = automation.get_status()

# Manuel aktivite tetikle
automation.manual_activity('browse_feed')

# Otomasyonu durdur
automation.stop_automation()
```

### 2. Admin Panel Kullanımı

1. Admin paneline giriş yapın
2. "Instagram Otomasyon" sekmesine gidin
3. Zamanlayıcıyı başlatın/durdurun
4. Manuel aktiviteler tetikleyin
5. Aktif sessionları ve logları izleyin

### 3. API Endpoints

```bash
# Durum kontrol
GET /api/automation/status

# Manuel otomasyon başlat
POST /api/automation/start
{
  "duration": 30,
  "session_count": 1
}

# Otomasyon durdur
POST /api/automation/stop
{
  "session_id": "optional_session_id"
}

# Manuel aktivite tetikle
POST /api/automation/trigger
{
  "activity_type": "browse_feed",
  "target": "optional_target"
}

# Session bilgileri
GET /api/automation/sessions
```

## Loglama ve İzleme

### Activity Log
Tüm aktiviteler `activity_log.json` dosyasında kaydedilir:
```json
{
  "2024-01-15": {
    "session_123": {
      "likes": 25,
      "follows": 5,
      "story_views": 12
    }
  },
  "detailed_log": [
    {
      "timestamp": "2024-01-15T10:30:00",
      "session_id": "session_123",
      "username": "user123",
      "activity_type": "likes",
      "target": "media_456",
      "success": true
    }
  ]
}
```

### Scheduler State
Zamanlayıcı durumu `scheduler_state.json` dosyasında saklanır.

## Güvenlik ve Limitler

### Günlük Limitler
- **Beğeni**: 500/gün
- **Takip**: 100/gün  
- **Takip Bırakma**: 50/gün
- **Story Görüntüleme**: 200/gün

### Session Limitler
- **Beğeni**: 50/session
- **Takip**: 10/session
- **Süre**: 5-30 dakika arası

### Güvenlik Önlemleri
- Session rotation sistemi
- Rate limit detection
- Human-like delays (10-30 saniye)
- Challenge detection ve durdurma
- Error tracking ve session blocking

## Sorun Giderme

### Yaygın Hatalar

1. **"No active sessions"**: `sessions.json` dosyasında aktif session bulunmuyor
2. **"Module not found"**: Import path'leri kontrol edin
3. **"Rate limited"**: Session geçici olarak bloke, bekleyin
4. **"Session blocked"**: Session refresh gerekiyor

### Debug Modu
```python
# Debug log aktifleştirme
import logging
logging.basicConfig(level=logging.DEBUG)

# Test modu
from instavideo.instagram_auto import AutoSessionManager
manager = AutoSessionManager()
print(manager.get_session_stats())
```

### Log Dosyaları
- `activity_log.json`: Aktivite geçmişi
- `scheduler_state.json`: Zamanlayıcı durumu
- Console output: Gerçek zamanlı hata mesajları

## Geliştirici Notları

### Kod Yapısı
- **session_manager.py**: Session CRUD operations
- **activity_manager.py**: Instagram API interactions
- **scheduler.py**: Automation scheduling logic
- **config.json**: Configurable parameters

### Özelleştirme
- Yeni aktivite türleri `activity_manager.py` içine eklenebilir
- Zamanlama kuralları `scheduler.py` içinde değiştirilebilir
- Limitler `config.json` dosyasında ayarlanabilir

### Extension Points
- Custom activity handlers
- External notification systems
- Database integration
- Advanced analytics

## Lisans ve Destek

Bu modül InstaVido projesi için geliştirilmiştir. Kullanım sırasında Instagram'ın hizmet şartlarına uyulması gereklidir.

**Önemli Uyarı**: Bu otomasyon sistemi eğitim amaçlıdır. Instagram'ın API kullanım kurallarına ve hizmet şartlarına uygun şekilde kullanılmalıdır.