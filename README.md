# Session Otomasyon ve Yönetim Sistemi – Entegrasyon Rehberi

Bu modüller adminpanel/ altında yer alır ve Flask ana uygulamasına blueprint ile eklenir.

## Entegrasyon Adımları

1. `adminpanel/` klasöründeki dosyaları repoya ekle.
2. Ana `app.py` dosyanın sonuna aşağıdaki satırı ekle:
   ```python
   from adminpanel import register_blueprints
   register_blueprints(app)
   ```
3. Gerektiğinde panel frontend’de bu endpointleri çağırarak session status, log, aktivite tetikleme, yedekleme vs. işlemlerini yapabilirsin.

## Endpointler

- **Session Aktivite**: `/srdr-proadmin/api/session/<session_key>/activity` [POST]
- **Session Durum**: `/srdr-proadmin/api/session/<session_key>/status` [GET]
- **Session Logları**: `/srdr-proadmin/api/session/<session_key>/logs` [GET]

## Otomasyon

- Scheduler otomatik olarak arka planda çalışır, sessionlara insana özgü davranışlar uygular.

## Yedekleme

- Yedekleme fonksiyonuyla session.json dosyasını istediğin zaman yedekleyebilirsin.

---

### Notlar

- Bu modüller app.py ve session.json yapını bozmadan eklenmiştir.
- IG API/Selenium entegrasyonu için ilgili kısımlara istediğin kodu ekleyebilirsin.
- Panelde frontend entegrasyonu için REST endpointlere istek göndermek yeterlidir.