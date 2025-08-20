# Instagram Otomatik Beğenme ve Takip Etme Sistemi

Instagram session verilerini kullanarak otomatik beğenme ve takip etme işlemleri yapan Python uygulaması.

## ⚠️ Önemli Uyarılar

- Bu sistem eğitim ve araştırma amaçlıdır
- Instagram Terms of Service'e uygun kullanım zorunludur
- Aşırı kullanımdan kaçının
- Kullanım sorumluluğu kullanıcıya aittir
- Yasal sorumlulukları göz önünde bulundurun

## Özellikler

### 1. Session Yönetimi
- Instagram cookie verilerini güvenli şekilde saklama
- Session durumunu kontrol etme
- Otomatik session yenileme
- Mevcut session pool sistemiyle entegrasyon

### 2. Otomatik Beğenme Sistemi
- Hashtag bazlı post arama
- Kullanıcı bazlı post beğenme
- Beğenme sınırları ve güvenlik kontrolleri
- Rate limiting (hız sınırlaması)
- Duplicate beğenme önleme

### 3. Otomatik Takip Sistemi
- Hedef kitlenin takipçilerini analiz etme
- Akıllı takip stratejileri
- Takip geri alma (unfollow) sistemi
- Takip/takipçi oranı optimizasyonu

### 4. Güvenlik ve Kontrol
- Instagram API rate limitlerini respekt etme
- Bot detection önlemleri
- Error handling ve logging
- Kullanım istatistikleri
- Otomatik session blok yönetimi

### 5. Konfigürasyon
- JSON bazlı ayar dosyası
- Hedef hashtag listesi
- Kullanıcı kara listesi
- Günlük/saatlik aktivite limitleri

## Kurulum

### Gereksinimler

```bash
pip install -r requirements.txt
```

### Konfigürasyon

1. `config/settings.json` dosyasını düzenleyin
2. Hedef hashtag'leri ve limitleri ayarlayın
3. Güvenlik parametrelerini kontrol edin

## Kullanım

### Interaktif Mod

```bash
python main.py --mode interactive
```

### Zamanlanmış Mod

```bash
python main.py --mode scheduled
```

### Tek Komut Çalıştırma

```bash
# Hashtag'den beğenme
python main.py --mode single --action like --hashtag nature

# Kullanıcı takip etme
python main.py --mode single --action follow --username targetuser

# İstatistikleri görme
python main.py --mode single --action stats
```

## Dosya Yapısı

```
instagram_bot/
├── main.py                 # Ana uygulama
├── config/
│   ├── settings.json       # Ayar dosyası
│   └── cookies.json        # Session verileri (referans)
├── src/
│   ├── instagram_client.py # Instagram API client
│   ├── like_manager.py     # Beğenme yöneticisi
│   ├── follow_manager.py   # Takip yöneticisi
│   ├── session_manager.py  # Session yöneticisi
│   └── utils.py           # Yardımcı fonksiyonlar
├── logs/                   # Log dosyaları
├── requirements.txt        # Python bağımlılıkları
├── test_bot.py            # Test scripti
└── README.md              # Bu dosya
```

## Konfigürasyon Seçenekleri

### Hedef Hashtag'ler
```json
{
  "target_hashtags": ["nature", "photography", "travel"]
}
```

### Günlük Limitler
```json
{
  "daily_limits": {
    "likes": 100,
    "follows": 50,
    "unfollows": 30
  }
}
```

### Saatlik Limitler
```json
{
  "hourly_limits": {
    "likes": 15,
    "follows": 8,
    "unfollows": 5
  }
}
```

### Gecikme Ayarları
```json
{
  "delays": {
    "min_like_delay": 10,
    "max_like_delay": 30,
    "min_follow_delay": 20,
    "max_follow_delay": 60
  }
}
```

### Güvenlik Ayarları
```json
{
  "safety": {
    "max_consecutive_failures": 3,
    "cooldown_after_failure": 300,
    "respect_rate_limits": true,
    "simulate_human_behavior": true
  }
}
```

## Test Etme

```bash
python test_bot.py
```

## Log Dosyaları

- `logs/instagram_bot_YYYYMMDD.log` - Ana log dosyası
- `logs/liked_posts.json` - Beğenilen postlar
- `logs/followed_users.json` - Takip edilen kullanıcılar
- `logs/stats_YYYYMMDD_HH.json` - Saatlik istatistikler
- `logs/daily_stats_YYYYMMDD.json` - Günlük istatistikler

## Mevcut Sistemle Entegrasyon

Bu bot, mevcut repository'deki session management sistemini kullanır:

- `session_pool.py` - Session pool yönetimi
- `sessions.json` - Mevcut session verileri
- `blocked_cookies.json` - Bloklanmış session'lar

## Güvenlik Önlemleri

1. **Rate Limiting**: Instagram limitlerini aşmamak için otomatik kontrol
2. **Random Delays**: İnsan davranışı simülasyonu
3. **Error Handling**: Başarısız istekleri yönetme
4. **Session Validation**: Geçerli session kontrolü
5. **Activity Limits**: Günlük/saatlik limitler
6. **Blacklist Support**: Kullanıcı ve hashtag kara listesi

## API Entegrasyonu

Instagram Private API endpoint'leri kullanılır:
- User profile info
- User feed
- Hashtag search
- Like/unlike posts
- Follow/unfollow users
- Followers/following lists

## Bakım

- Eski log dosyaları otomatik temizlenir
- Session durumları düzenli güncellenir
- Expired bloklar temizlenir
- Following data cleanup

## Sorun Giderme

1. **Session geçersiz**: `sessions.json` dosyasını kontrol edin
2. **Rate limit**: Delay ayarlarını artırın
3. **Consecutive failures**: Internet bağlantısını kontrol edin
4. **Config hatası**: JSON syntax'ını kontrol edin

## Geliştirme

Yeni özellikler eklemek için:

1. `src/` dizinindeki uygun modülü düzenleyin
2. `config/settings.json`'a yeni ayarları ekleyin
3. `main.py`'da yeni action'ları ekleyin
4. Test edin

## Lisans ve Sorumluluk

Bu yazılım eğitim amaçlıdır. Kullanıcı, Instagram'ın kullanım şartlarına uymakla yükümlüdür. Geliştiriciler herhangi bir sorumluluk kabul etmez.