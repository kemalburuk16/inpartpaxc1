# Instagram Otomatik Beğenme ve Takip Sistemi

Bu sistem Instagram'da otomatik beğenme ve takip işlemlerini güvenli bir şekilde gerçekleştirir.

## Özellikler

- ✅ Hashtag bazlı otomatik beğenme
- ✅ Kullanıcı bazlı otomatik takip
- ✅ Mevcut session altyapısıyla entegrasyon
- ✅ Rate limiting ve güvenlik önlemleri
- ✅ Detaylı loglama
- ✅ Konfigürasyonlu çalışma
- ✅ Rastgele gecikme ve insansı davranış

## Kurulum

1. Gerekli paketleri yükleyin:
```bash
pip install -r requirements.txt
```

2. Konfigürasyon dosyasını oluşturun:
```bash
python main.py --mode init
```

3. `config/settings.json` dosyasını düzenleyin ve hedef hashtag'ları ve kullanıcıları ayarlayın.

## Kullanım

### Durum Kontrolü
```bash
python main.py --mode status
```

### Sadece Beğenme
```bash
python main.py --mode like
```

### Sadece Takip
```bash
python main.py --mode follow
```

### Her İkisi Birden
```bash
python main.py --mode both
```

### Dry Run (Test)
```bash
python main.py --mode both --dry-run
```

### Verbose Loglama
```bash
python main.py --mode both --verbose
```

## Konfigürasyon

`config/settings.json` dosyasında aşağıdaki ayarları yapabilirsiniz:

### Rate Limiting
- `likes_per_hour`: Saatte maksimum beğeni sayısı (varsayılan: 60)
- `follows_per_hour`: Saatte maksimum takip sayısı (varsayılan: 30)
- `min_delay_seconds`: İstekler arası minimum bekleme (varsayılan: 10)
- `max_delay_seconds`: İstekler arası maksimum bekleme (varsayılan: 30)

### Hashtag Ayarları
- `target_tags`: Hedef hashtag listesi
- `posts_per_tag`: Her hashtag için işlenecek post sayısı
- `like_probability`: Beğenme olasılığı (0.0-1.0)

### Takip Ayarları
- `target_users`: Doğrudan takip edilecek kullanıcılar
- `follow_followers_of`: Bu kullanıcıların takipçilerini takip et
- `follow_probability`: Takip etme olasılığı (0.0-1.0)

## Güvenlik

- Instagram rate limitlerini otomatik olarak takip eder
- Rastgele gecikmeler ekler
- Spam benzeri davranışları önler
- Session health check yapar
- Detaylı loglama ile tüm işlemleri kaydeder

## Loglar

Tüm işlemler `logs/` klasöründe saklanır:
- `instagram_automation.log`: Ana sistem logları
- `likes.json`: Beğenme işlemleri
- `follows.json`: Takip işlemleri

## Session Yönetimi

Sistem mevcut `session_pool.py` ve `session_manager.py` altyapısını kullanır:
- Otomatik session rotasyonu
- Health check ve karantina sistemi
- Çoklu session desteği
- Hata yönetimi

## Komutlar

```bash
# Sistem durumunu kontrol et
python main.py --mode status

# Sadece beğenme işlemlerini çalıştır
python main.py --mode like

# Sadece takip işlemlerini çalıştır  
python main.py --mode follow

# Her ikisini birden çalıştır
python main.py --mode both

# Test modu (gerçek işlem yapmaz)
python main.py --dry-run

# Eski logları temizle
python main.py --clean-logs

# Verbose mod
python main.py --verbose

# Özel konfigürasyon dosyası kullan
python main.py --config custom_config.json
```

## Sorun Giderme

1. **Session problemi**: `python main.py --mode status` ile session durumunu kontrol edin
2. **Rate limit**: Sistem otomatik olarak yönetir, beklemeyi deneyin
3. **Konfigürasyon hatası**: `python main.py --mode init` ile yeni config oluşturun
4. **Loglama**: `--verbose` parametresi ile detaylı log alın