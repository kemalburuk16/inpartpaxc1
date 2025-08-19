# /var/www/instavido/session_pool.py
# -*- coding: utf-8 -*-
import os, json, time, random, threading, logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SESSIONS_PATH = os.path.join(BASE_DIR, "sessions.json")
BLOCKED_PATH  = os.path.join(BASE_DIR, "blocked_cookies.json")  # ORTAK: app.py ve admin ile aynı
SESSION_IDX_PATH = os.path.join(BASE_DIR, "session_index.txt")

# --- Jitter (istekler arası insanî gecikme) ---
# Varsayılan: 400–1200 ms, ancak ortam değişkeni ile override edilebilir:
#   export INSTAVIDO_JITTER="800,1800"
def _load_jitter() -> tuple[int, int]:
    val = os.environ.get("INSTAVIDO_JITTER", "").strip()
    if val and "," in val:
        try:
            lo, hi = [int(x) for x in val.split(",", 1)]
            if lo > 0 and hi > lo:
                return (lo, hi)
        except Exception:
            pass
    return (400, 1200)

JITTER_RANGE_MS = _load_jitter()

# Karantina süreleri (dk)
KARANTINA_DK       = 30   # 401/403/419
KARANTINA_429_DK   = 12   # 429 için daha kısa throttle

# requests için default timeout
REQ_TIMEOUT = (10, 35)  # (connect, read)

log = logging.getLogger("session_pool")
log.setLevel(logging.INFO)


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _atomic_write(path: str, content: str):
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(content)
    os.replace(tmp, path)


def _read_blocked_list() -> List[dict]:
    """
    Ortak format (liste):
      [
        {"sessionid": "...", "blocked_until": 1723512345.12},  # epoch seconds
        ...
      ]
    Eski dict formatını da otomatik listeye çevirir.
    """
    if not os.path.exists(BLOCKED_PATH):
        return []
    try:
        data = json.loads(open(BLOCKED_PATH, "r", encoding="utf-8").read())
        if isinstance(data, list):
            return data
        # Eski olası dict formatını listeye göç et (eski uyum)
        # {"<ds_user_id>": {"blocked_until": "YYYY-mm-dd HH:MM:SS"}}
        if isinstance(data, dict):
            out = []
            for _k, v in (data or {}).items():
                try:
                    ts = v.get("blocked_until")
                    # string ise epoch'a çevir
                    if isinstance(ts, str):
                        dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
                        ts = time.mktime(dt.timetuple())
                    out.append({"sessionid": _k, "blocked_until": float(ts or 0)})
                except Exception:
                    continue
            return out
    except Exception:
        pass
    return []


def _write_blocked_list(rows: List[dict]):
    # Aynı sessionid için tek kayıt bırak; süresi geçenleri at.
    merged = {}
    now = time.time()
    for r in rows:
        sid = (r or {}).get("sessionid")
        bu  = (r or {}).get("blocked_until", 0)
        if not sid:
            continue
        if float(bu or 0) <= now:
            continue
        prev = merged.get(sid)
        if (not prev) or (float(bu) > float(prev.get("blocked_until", 0))):
            merged[sid] = {"sessionid": sid, "blocked_until": float(bu)}
    out = list(merged.values())
    _atomic_write(BLOCKED_PATH, json.dumps(out, ensure_ascii=False, indent=2))


class SessionPool:
    """
    - sessions.json içinden oturumları yükler
    - round-robin ile sıradaki oturumu verir
    - 401/403/419/429 hatalarda karantinaya alır (blocked=true, unblock_at)
    - tam cookie seti + fingerprint + proxy saha bilgilerini destekler
    - http_get/http_post ile otomatik header/cookie/proxy ve retry yönetimi yapar
    """
    def __init__(self,
                 path_sessions: str = SESSIONS_PATH,
                 path_blocked: str = BLOCKED_PATH,
                 path_idx: str = SESSION_IDX_PATH):
        self.path_sessions = path_sessions
        self.path_blocked  = path_blocked
        self.path_idx      = path_idx
        self.lock = threading.Lock()
        self.sessions: List[Dict[str, Any]] = []
        self.idx = 0
        self._load()

    # ---------- public API ----------
    def http_get(self, url: str, params: Optional[dict] = None,
                 extra_headers: Optional[dict] = None,
                 allow_redirects: bool = True) -> requests.Response:
        return self._http_request("GET", url, params=params, data=None,
                                  extra_headers=extra_headers,
                                  allow_redirects=allow_redirects)

    def http_post(self, url: str, data: Optional[dict] = None,
                  extra_headers: Optional[dict] = None,
                  json_body: Optional[dict] = None) -> requests.Response:
        return self._http_request("POST", url, params=None, data=data,
                                  json_body=json_body,
                                  extra_headers=extra_headers)

    def next_account_hint(self) -> Optional[str]:
        """UI/log için sıradaki kullanıcı adını döndürür."""
        with self.lock:
            if not self.sessions:
                return None
            s = self.sessions[self.idx % len(self.sessions)]
            return s.get("user") or s.get("ds_user_id")

    # ---------- iç işler ----------
    def _load(self):
        with self.lock:
            if os.path.exists(self.path_sessions):
                try:
                    self.sessions = json.loads(open(self.path_sessions, "r", encoding="utf-8").read())
                except Exception:
                    self.sessions = []
            else:
                self.sessions = []

            # index
            if os.path.exists(self.path_idx):
                try:
                    self.idx = int(open(self.path_idx, "r", encoding="utf-8").read().strip() or "0")
                except Exception:
                    self.idx = 0
            else:
                self.idx = 0

            # BLOK KONTROL (ortak format liste)
            blocked_list = _read_blocked_list()
            now = time.time()

            # normalize alanlar
            for s in self.sessions:
                s.setdefault("fail_count", 0)
                s.setdefault("success_count", 0)
                s.setdefault("status", "active")
                s.setdefault("blocked", False)
                s.setdefault("last_used", None)
                # geniş cookie seti (opsiyonel)
                s.setdefault("cookies", {})     # full cookie dict
                s.setdefault("fingerprint", {}) # UA, sec-ch, lang, tz, dpr, wd vb.
                s.setdefault("proxy", None)     # "http://user:pass@ip:port"
                s.setdefault("unblock_at", None)

                # blok eşlemesi sessionid üzerinden
                sid = s.get("sessionid")
                if not sid:
                    continue
                for b in blocked_list:
                    if b.get("sessionid") == sid and float(b.get("blocked_until", 0)) > now:
                        s["blocked"] = True
                        # içeriye insan okunur da yazalım
                        s["unblock_at"] = datetime.fromtimestamp(float(b["blocked_until"])).strftime("%Y-%m-%d %H:%M:%S")
                        break

    def _save(self):
        with self.lock:
            _atomic_write(self.path_sessions, json.dumps(self.sessions, ensure_ascii=False, indent=2))
            _atomic_write(self.path_idx, str(self.idx))

            # blocked_cookies.json’u ORTAK liste formatında güncelle
            now = time.time()
            existing = _read_blocked_list()  # mevcutları al, süresi geçmişleri _write temizliyor zaten
            extra = []
            for s in self.sessions:
                if s.get("blocked"):
                    # iç veri 'unblock_at' string olabilir → epoch’a çevir
                    ts = None
                    if s.get("unblock_at"):
                        try:
                            dt = datetime.strptime(s["unblock_at"], "%Y-%m-%d %H:%M:%S")
                            ts = time.mktime(dt.timetuple())
                        except Exception:
                            ts = None
                    if not ts:
                        # karantina varsayılan süresi kadar
                        ts = now + KARANTINA_DK * 60
                    extra.append({"sessionid": s.get("sessionid"), "blocked_until": float(ts)})

            _write_blocked_list(existing + extra)

    def _sleep_jitter(self):
        t_ms = random.randint(*JITTER_RANGE_MS)
        time.sleep(t_ms / 1000.0)

    def _pick_session(self) -> Optional[Dict[str, Any]]:
        with self.lock:
            if not self.sessions:
                return None

            N = len(self.sessions)
            start = self.idx % N
            now = time.time()
            blocked_list = _read_blocked_list()

            for offset in range(N):
                i = (start + offset) % N
                s = self.sessions[i]

                # Karantinayı kontrol et (dosya hakikati → state’i senkronla)
                sid = s.get("sessionid")
                is_blocked = False
                unblock_epoch = None
                for b in blocked_list:
                    if b.get("sessionid") == sid:
                        unblock_epoch = float(b.get("blocked_until", 0))
                        if unblock_epoch > now:
                            is_blocked = True
                        break

                if is_blocked:
                    # içeride de işaretli tut
                    s["blocked"] = True
                    s["unblock_at"] = datetime.fromtimestamp(unblock_epoch).strftime("%Y-%m-%d %H:%M:%S")
                    continue
                else:
                    # süresi dolmuşsa bayrakları temizle
                    if s.get("blocked"):
                        s["blocked"] = False
                        s["unblock_at"] = None

                # aktif/uygun session
                self.idx = i + 1
                s["last_used"] = _now_str()
                self._save()
                return s

            return None

    def _report_success(self, s: Dict[str, Any]):
        with self.lock:
            s["success_count"] = int(s.get("success_count", 0)) + 1
            s["status"] = "active"
            self._save()

    def _report_failure(self, s: Dict[str, Any], *, status_code: Optional[int] = None, block: bool = False):
        with self.lock:
            s["fail_count"] = int(s.get("fail_count", 0)) + 1
            s["status"] = "error"

            # Status'a göre karantina süresi
            block_minutes = None
            if block:
                if status_code in (401, 403, 419):
                    block_minutes = KARANTINA_DK
                elif status_code == 429:
                    block_minutes = KARANTINA_429_DK
                else:
                    block_minutes = KARANTINA_DK  # emniyet

            if block_minutes:
                s["blocked"] = True
                unblock_at_dt = datetime.now() + timedelta(minutes=block_minutes)
                s["unblock_at"] = unblock_at_dt.strftime("%Y-%m-%d %H:%M:%S")

            # hafif log
            try:
                log.info("Session fail user=%s code=%s blocked=%s until=%s",
                         s.get("user") or s.get("ds_user_id"),
                         status_code, s.get("blocked"), s.get("unblock_at"))
            except Exception:
                pass

            self._save()

    def _build_headers(self, s: Dict[str, Any], extra: Optional[dict]) -> dict:
        fp = s.get("fingerprint") or {}
        ua = fp.get("user_agent") or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/123.0.0.0 Safari/537.36"
        )
        sec_ua = fp.get("sec_ch_ua") or '"Chromium";v="123", "Google Chrome";v="123", ";Not A Brand";v="99"'
        sec_ua_m = fp.get("sec_ch_ua_mobile") or "?0"
        sec_plat = fp.get("sec_ch_ua_platform") or '"Windows"'
        accept_lang = fp.get("accept_language") or "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7"
        referer = fp.get("referer") or "https://www.instagram.com/"
        x_ig_app_id = fp.get("x_ig_app_id") or "1217981644879628"
        asbd_id = fp.get("x_asbd_id") or "129477"

        headers = {
            "User-Agent": ua,
            "Accept": "*/*",
            "Accept-Language": accept_lang,
            "Referer": referer,
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
            "sec-ch-ua": sec_ua,
            "sec-ch-ua-mobile": sec_ua_m,
            "sec-ch-ua-platform": sec_plat,
            "X-IG-App-ID": x_ig_app_id,
            "X-ASBD-ID": asbd_id,
        }
        if extra:
            headers.update(extra)
        return headers

    def _build_cookies(self, s: Dict[str, Any]) -> dict:
        # Geniş cookie setini destekle, yoksa eski alanlardan derle
        ck = dict(s.get("cookies") or {})
        # geriye dönük uyumluluk
        for k in ("sessionid", "ds_user_id", "csrftoken"):
            if s.get(k) and k not in ck:
                ck[k] = s[k]
        return ck

    def _build_proxies(self, s: Dict[str, Any]) -> Optional[dict]:
        p = s.get("proxy")
        if not p:
            return None
        return {"http": p, "https": p}

    def _http_request(self, method: str, url: str,
                      params: Optional[dict], data: Optional[dict],
                      json_body: Optional[dict] = None,
                      extra_headers: Optional[dict] = None,
                      allow_redirects: bool = True) -> requests.Response:
        # round-robin ile session seç
        s = self._pick_session()
        if not s:
            raise RuntimeError("SessionPool: kullanılabilir oturum yok.")

        self._sleep_jitter()

        headers = self._build_headers(s, extra_headers)
        cookies = self._build_cookies(s)
        proxies = self._build_proxies(s)

        try:
            if method == "GET":
                resp = requests.get(
                    url, params=params, headers=headers, cookies=cookies,
                    proxies=proxies, timeout=REQ_TIMEOUT, allow_redirects=allow_redirects
                )
            else:
                resp = requests.post(
                    url, params=params, data=data, json=json_body,
                    headers=headers, cookies=cookies, proxies=proxies,
                    timeout=REQ_TIMEOUT, allow_redirects=allow_redirects
                )
        except requests.RequestException:
            self._report_failure(s, status_code=None, block=False)
            raise

        # Başarı
        if resp.status_code in (200, 206):
            self._report_success(s)
            return resp

        # Rate-limit/oturum sorunları
        if resp.status_code in (401, 403, 419, 429):
            # Karantina (status'a göre süre)
            self._report_failure(s, status_code=resp.status_code, block=True)
        else:
            self._report_failure(s, status_code=resp.status_code, block=False)

        # Bir kez daha farklı session ile dene (hızlı fallback)
        alt = self._pick_session()
        if not alt:
            return resp  # yapacak bir şey yok, orijinali dön

        self._sleep_jitter()
        headers = self._build_headers(alt, extra_headers)
        cookies = self._build_cookies(alt)
        proxies = self._build_proxies(alt)
        try:
            if method == "GET":
                r2 = requests.get(
                    url, params=params, headers=headers, cookies=cookies,
                    proxies=proxies, timeout=REQ_TIMEOUT, allow_redirects=allow_redirects
                )
            else:
                r2 = requests.post(
                    url, params=params, data=data, json=json_body,
                    headers=headers, cookies=cookies, proxies=proxies,
                    timeout=REQ_TIMEOUT, allow_redirects=allow_redirects
                )
        except requests.RequestException:
            self._report_failure(alt, status_code=None, block=False)
            return resp

        if r2.status_code in (200, 206):
            self._report_success(alt)
            return r2

        if r2.status_code in (401, 403, 419, 429):
            self._report_failure(alt, status_code=r2.status_code, block=True)
        else:
            self._report_failure(alt, status_code=r2.status_code, block=False)

        return r2


# Global havuz (app.py içinden direkt import edip kullanabilirsiniz)
pool = SessionPool()

