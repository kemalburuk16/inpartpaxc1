# app.py
from seo_instavido.seo_utils import get_meta
from adminpanel.views import admin_bp
import adminpanel  # admin_bp ve tüm admin route'larını yükler (views, ads_views)
import hmac, hashlib, base64, os, re, json, time, io, logging, requests
from urllib.parse import urlparse, urljoin, quote, urlencode
import socket, ipaddress
from typing import Optional, Dict, Any, Tuple, List
from session_logger import log_session_use, notify_download, update_session_counters
from flask import (
    Flask, render_template, request, redirect,
    url_for, session, Response, send_file, jsonify
)
from flask_session import Session
from flask_babelex import Babel, _
from adminpanel.blacklist_admin import blacklist_admin_bp
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from config.redis_helpers import get_redis_client
import random
from datetime import datetime

# --- ENTEGRE --- #
from session_logger import log_session_use, notify_download

# en üste yakın bir yere (global):
_auth_soft_fails = {}

def _bump_soft_fail(sessid):
    if not sessid: return 0
    n = _auth_soft_fails.get(sessid, 0) + 1
    _auth_soft_fails[sessid] = n
    # 900 sn sonra sıfırlamak istersen bir temizlik task'ı yazılabilir
    return n

def _clear_soft_fail(sessid):
    if sessid in _auth_soft_fails:
        _auth_soft_fails.pop(sessid, None)



# ============================================================================#
#                              Proxy / Signature                              #
# ============================================================================#
IMG_PROXY_SECRET   = os.getenv("IMG_PROXY_SECRET", "").strip()
MEDIA_PROXY_SECRET = os.getenv("MEDIA_PROXY_SECRET", "").strip()

def _b64(s: bytes) -> str:
    return base64.urlsafe_b64encode(s).decode().rstrip("=")

def _ub64(s: str) -> bytes:
    s = s + "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s.encode())

def _sign_payload(secret: str, payload: str) -> str:
    return _b64(hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest())

def sign_img_proxy(url: str, ttl_sec: int = 900) -> str:
    """
    <img src="/img_proxy?..."> için imzalı URL üretir: url, exp, nonce, sig
    """
    if not IMG_PROXY_SECRET:
        # dev modda doğrudan kullan; prod’da mutlaka env ver
        return f"/img_proxy?url={quote(url)}"
    exp = str(int(time.time()) + ttl_sec)
    nonce = _b64(os.urandom(8))
    payload = f"url={url}&exp={exp}&nonce={nonce}"
    sig = _sign_payload(IMG_PROXY_SECRET, payload)
    qs = urlencode({"url": url, "exp": exp, "nonce": nonce, "sig": sig})
    return f"/img_proxy?{qs}"

def sign_media_proxy(url: str, fn: str = "instavido", ttl_sec: int = 900) -> str:
    """
    /proxy_download için imzalı URL üretir: url, fn, exp, nonce, sig
    """
    if not MEDIA_PROXY_SECRET:
        return f"/proxy_download?url={quote(url)}&fn={quote(fn)}"
    exp = str(int(time.time()) + ttl_sec)
    nonce = _b64(os.urandom(8))
    payload = f"url={url}&fn={fn}&exp={exp}&nonce={nonce}"
    sig = _sign_payload(MEDIA_PROXY_SECRET, payload)
    qs = urlencode({"url": url, "fn": fn, "exp": exp, "nonce": nonce, "sig": sig})
    return f"/proxy_download?{qs}"

ALLOWED_REFERERS   = ("instavido.com", "www.instavido.com")
def _has_allowed_referer(req) -> bool:
    ref = (req.headers.get("Referer") or "").lower()
    return any(h in ref for h in ALLOWED_REFERERS)

# ===================== Güvenlik & reCAPTCHA & Limitler =====================
RECAPTCHA_SITE_KEY = os.getenv("RECAPTCHA_SITE_KEY", "").strip()
RECAPTCHA_SECRET   = os.getenv("RECAPTCHA_SECRET", "").strip()

RATE_FILE = "/var/www/instavido/.rate_limits.json"
os.makedirs(os.path.dirname(RATE_FILE), exist_ok=True)
if not os.path.exists(RATE_FILE):
    with open(RATE_FILE, "w") as f:
        json.dump({}, f)

class SimpleLimiter:
    """
    Dakika başına max ve burst limiti uygular.
    Döner: (allowed: bool, need_captcha: bool)
    """
    def __init__(self, window_seconds=60, max_requests=60, burst=80):
        self.window = window_seconds
        self.max = max_requests
        self.burst = burst

    def hit(self, key: str):
        now = int(time.time())
        try:
            with open(RATE_FILE, "r+") as f:
                data = json.load(f)
                arr = data.get(key, [])
                arr = [t for t in arr if t > now - self.window]
                arr.append(now)
                data[key] = arr
                f.seek(0)
                json.dump(data, f)
                f.truncate()
            count = len(arr)
            if count > self.burst:
                return (False, True)   # captcha duvarı
            if count > self.max:
                return (False, False)  # kısa blok
            return (True, False)
        except Exception:
            return (True, False)

soft_limiter = SimpleLimiter(window_seconds=60, max_requests=60, burst=80)

# Kara liste dosyası
BLACKLIST_PATH = "/var/www/instavido/adminpanel/data/blacklist.json"

def _load_blacklist():
    if not os.path.exists(BLACKLIST_PATH):
        return {"profiles": [], "links": []}
    try:
        with open(BLACKLIST_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"profiles": [], "links": []}

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())

def _is_blocked(target: str) -> bool:
    if not target:
        return False
    bl = _load_blacklist()
    t = _norm(target)
    profs = [_norm(x) for x in bl.get("profiles", [])]
    links  = [_norm(x) for x in bl.get("links", [])]
    return t in profs or t in links

def _recaptcha_verify(token: str, remote_ip: str) -> bool:
    if not (RECAPTCHA_SECRET and token):
        return False
    try:
        r = requests.post(
            "https://www.google.com/recaptcha/api/siteverify",
            data={"secret": RECAPTCHA_SECRET, "response": token, "remoteip": remote_ip},
            timeout=10
        )
        j = r.json()
        return bool(j.get("success"))
    except Exception:
        return False

def _ensure_gate(lang):
    if not session.get("gate_passed"):
        if not request.path.startswith(f"/{lang}/gate"):
            nxt = request.url
            return redirect(url_for("gate", lang=lang, next=nxt))
    return None

def _ensure_not_blacklisted():
    target = session.get("last_target", "")
    if _is_blocked(target):
        return render_template("policies/blocked.html", target=target), 200
    return None

# --- Güvenli rate-limit sarmalayıcı (MERKEZİ) ---
def _enforce_rate_limit(suffix: str = ""):
    """
    Tüm rate-limit kontrolleri için tek nokta.
    HATA OLURSA: 500 yerine devreye girmeden devam etmek için None döndürür.
    BAŞARILI DURUM: None (devam et)
    LİMİTE TAKILIRSA: Flask Response döndürür (Captcha duvarı veya 429).
    """
    try:
        # Kullanıcıya göre anahtar (IP + session + opsiyonel suffix)
        ip = (request.headers.get("X-Forwarded-For", request.remote_addr) or "0.0.0.0").split(",")[0].strip()
        sid = session.get("_sid") or request.cookies.get("instavido_session") or "-"
        key = f"rl:{ip}:{sid}{suffix}"

        allowed, need_captcha = soft_limiter.hit(key)
    except Exception as e:
        # Herhangi bir hata → limiti es geç (kullanıcıyı düşürmeyelim)
        app.logger.exception("RateLimit bypass (error): %s", e)
        return None

    # İzin verildiyse None döndür (view devam etsin)
    if allowed:
        return None

    # Captcha istiyorsak politika duvarını göster (429 ile)
    if need_captcha:
        try:
            nxt = request.url
            return render_template("policies/captcha_wall.html", sitekey=RECAPTCHA_SITE_KEY, next=nxt), 429
        except Exception:
            pass
        return jsonify({"ok": False, "error": "captcha_required"}), 429

    # Normal rate-limit (kısa blok) → 429
    return jsonify({"ok": False, "error": "rate_limited"}), 429
# --- /Güvenli rate-limit sarmalayıcı ---

# =============================================================================

# ---- Sabitler --------------------------------------------------------------
BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
BLOCKED_COOKIES_PATH = os.path.join(BASE_DIR, "blocked_cookies.json")
SESSION_IDX_PATH = os.path.join(BASE_DIR, "session_index.txt")
SESSIONS_PATH = os.path.join(BASE_DIR, "sessions.json")
SESSION_DIR   = os.path.join(BASE_DIR, ".flask_session")
IG_APP_ID     = "1217981644879628"
UA_MOBILE     = "Instagram 298.0.0.0.0 Android"
UA_DESKTOP    = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                 "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# ---- Fingerprint presetleri (desktop + mobile) ----
_FINGERPRINT_PRESETS = [
    {
        "profile": "desktop_chrome_tr",
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/123.0.0.0 Safari/537.36"
        ),
        "accept_language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
        "sec_ch_ua": '"Chromium";v="123", "Google Chrome";v="123", ";Not A Brand";v="99"',
        "sec_ch_ua_mobile": "?0",
        "sec_ch_ua_platform": '"Windows"',
        "referer": "https://www.instagram.com/",
        "x_ig_app_id": "1217981644879628",
        "x_asbd_id": "129477",
    },
    {
        "profile": "mobile_webview_tr",
        "user_agent": (
            "Mozilla/5.0 (Linux; Android 13; SM-G991B) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/123.0.0.0 Mobile Safari/537.36 Instagram 300.0.0.0"
        ),
        "accept_language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
        "sec_ch_ua": '"Chromium";v="123", "Google Chrome";v="123", ";Not A Brand";v="99"',
        "sec_ch_ua_mobile": "?1",
        "sec_ch_ua_platform": '"Android"',
        "referer": "https://www.instagram.com/",
        "x_ig_app_id": "936619743392459",
        "x_asbd_id": "129477",
    },
]


# ---- Flask & Babel ---------------------------------------------------------
app = Flask(__name__)
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

# --- Proxy imzalama fonksiyonlarını Jinja'ya tanıt ---
# --- Redis Session + güvenli çerezler ---
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "CHANGE_THIS_IN_PROD")

app.config["SESSION_TYPE"] = "redis"
app.config["SESSION_REDIS"] = get_redis_client()
app.config["SESSION_PERMANENT"] = True
app.config["SESSION_USE_SIGNER"] = True
app.config["SESSION_KEY_PREFIX"] = "iv_sess:"
app.config["SESSION_COOKIE_NAME"] = "instavido_session"
app.config["SESSION_COOKIE_SECURE"] = True
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

app.jinja_env.globals.update(
    sign_img_proxy=sign_img_proxy,
    sign_media_proxy=sign_media_proxy,
)

# --- Redis tabanlı rate limiter (ek katman) ---
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0"),
    strategy="fixed-window",
    app=app,
)

# os.makedirs(SESSION_DIR, exist_ok=True)
Session(app)
app.url_map.strict_slashes = False

# --- Ads runtime (server-side fallback) ---
try:
    from ads_manager import ad_html as _ad_func
    app.jinja_env.globals.update(ad_html=_ad_func, get_ad=_ad_func)
except Exception:
    pass

# Logging
logging.basicConfig(level=logging.INFO)
app.logger.setLevel(logging.DEBUG)

app.config['BABEL_DEFAULT_LOCALE'] = 'en'
app.config['BABEL_TRANSLATION_DIRECTORIES'] = os.path.join(BASE_DIR, "translations")
babel = Babel(app)
LANGUAGES = ['en', 'tr', 'hi', 'de', 'fr', 'ko', 'ar', 'es']
app.jinja_env.globals.update(LANGUAGES=LANGUAGES)

# --------------------------------------------------------------------------- #
#  DİL SEÇİMİ                                                                 #
# --------------------------------------------------------------------------- #
@babel.localeselector
def get_locale():
    segments = request.path.strip('/').split('/')
    if segments and segments[0] in LANGUAGES:
        return segments[0]
    if request.view_args and 'lang' in request.view_args and request.view_args['lang'] in LANGUAGES:
        return request.view_args['lang']
    if request.args.get('lang') in LANGUAGES:
        return request.args.get('lang')
    return 'en'

# --- DİL VE META, MENÜ, OTOMATİK SEO CONTEXT ---
PAGE_ROUTES = [
    ('index', 'index.html'),
    ('video', 'video.html'),
    ('photo', 'photo.html'),
    ('reels', 'reels.html'),
    ('igtv', 'igtv.html'),
    ('story', 'story.html'),
    ('privacy', 'privacy.html'),
    ('terms', 'terms.html'),
    ('contact', 'contact.html'),
]

@app.context_processor
def inject_globals():
    lang = get_locale()
    try:
        page = request.endpoint if request.endpoint in dict(PAGE_ROUTES) else "index"
        meta = get_meta(page, lang)
    except Exception:
        meta = {}
    nav_links = [
        {
            'endpoint': page,
            'url': url_for(page, lang=lang),
            'name': _(page.capitalize())
        }
        for page, tmpl in PAGE_ROUTES
        if page not in ('privacy', 'terms', 'contact')
    ]
    return dict(meta=meta,
                nav_links=nav_links,
                get_locale=get_locale,
                LANGUAGES=LANGUAGES,
                RECAPTCHA_SITE_KEY=RECAPTCHA_SITE_KEY)

def _parse_cookie_kv(raw: str) -> dict:
    """
    DevTools'tan kopyalanmış satırlardan (tab/boşluk) veya key=value; ... tek satırdan
    cookie dict üretir.
    """
    kv = {}
    raw = (raw or "").strip()
    if not raw:
        return kv

    # key=value; key=value ... formatıysa
    if ";" in raw and "=" in raw and "\t" not in raw:
        for part in raw.split(";"):
            part = part.strip()
            if not part or "=" not in part:
                continue
            k, v = part.split("=", 1)
            kv[k.strip()] = v.strip()
        return kv

    # DevTools tab/space tablo formatı
    lines = raw.splitlines()
    for line in lines:
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            parts = line.split()
        if not parts:
            continue
        key = parts[0].strip()
        value = parts[1].strip() if len(parts) > 1 else ""
        if key and value:
            kv[key] = value

    return kv




# >>> MEDIA STATE TEMİZLEYİCİ
def _clear_media_state():
    for k in [
        "video_url","image_urls","thumbnail_url","raw_comments","video_title",
        "stories","username",
        "from_story","from_idx","from_video","from_fotograf","from_reels","from_igtv","from_load",
        "download_error"
    ]:
        session.pop(k, None)

@app.before_request
def _refresh():
    session.permanent = True
    now  = time.time()
    last = session.get("last", now)
    if now - last > 900:
        session.clear()
    session["last"] = now
    try:
        if request.cookies.get("age_ok") == "1":
            session["gate_passed"] = True
    except Exception:
        pass

# ----------------------------- Gate Route ------------------------------
@app.route("/<lang>/gate", methods=["GET","POST"])
def gate(lang):
    nxt = request.args.get("next") or request.form.get("next") or url_for("index", lang=lang)
    if request.method == "POST":
        if request.form.get("age13") == "on" and request.form.get("terms") == "on":
            session["gate_passed"] = True
            resp = redirect(nxt)
            try:
                resp.set_cookie(
                    "age_ok", "1",
                    max_age=60*60*24*365,
                    secure=True,
                    samesite="Lax"
                )
            except Exception:
                pass
            return resp
    return render_template("policies/gate.html", lang=lang, next=nxt)

# ------------------------- reCAPTCHA Doğrulama -------------------------
@app.route("/captcha/verify", methods=["POST"])
def captcha_verify():
    token = request.form.get("g-recaptcha-response", "") or request.form.get("recaptcha_token", "")
    ip = (request.headers.get("X-Forwarded-For", request.remote_addr) or "").split(",")[0].strip()
    if RECAPTCHA_SECRET and _recaptcha_verify(token, ip):
        session["captcha_ok_until"] = time.time() + 60*30
        nxt = request.form.get("next") or url_for("index", lang=get_locale())
        return redirect(nxt)
    return render_template("policies/captcha_wall.html", sitekey=RECAPTCHA_SITE_KEY), 400

# --------------------------------------------------------------------------- #
#  Yardımcılar                                                                #
# --------------------------------------------------------------------------- #
def block_session(sessionid, duration_sec=1800):
    now = time.time()
    blocked_until = now + duration_sec
    entry = {"sessionid": sessionid, "blocked_until": blocked_until}
    lst = []
    if os.path.exists(BLOCKED_COOKIES_PATH):
        with open(BLOCKED_COOKIES_PATH, encoding="utf-8") as f:
            try:
                lst = json.load(f)
            except:
                lst = []
    lst = [b for b in lst if b.get("blocked_until", 0) > now]
    if sessionid not in [b.get("sessionid") for b in lst]:
        lst.append(entry)
    with open(BLOCKED_COOKIES_PATH, "w", encoding="utf-8") as f:
        json.dump(lst, f, indent=2)

def _cookie_pool():
    if not os.path.exists(SESSIONS_PATH):
        return []
    with open(SESSIONS_PATH, encoding="utf-8") as f:
        sessions = json.load(f)
    blocked_ids = set()
    now = time.time()
    if os.path.exists(BLOCKED_COOKIES_PATH):
        with open(BLOCKED_COOKIES_PATH, encoding="utf-8") as f:
            for entry in json.load(f):
                if entry.get("blocked_until", 0) > now:
                    blocked_ids.add(entry.get("sessionid"))
    pool = [
        s for s in sessions
        if s.get("status", "active") == "active"
        and s.get("sessionid") not in blocked_ids
        and s.get("session_key") is not None
    ]
    pool.sort(key=lambda s: int(s["session_key"]))
    return pool

def get_next_session():
    pool = _cookie_pool()
    if not pool:
        return None
    idx = 0
    if os.path.exists(SESSION_IDX_PATH):
        try:
            with open(SESSION_IDX_PATH, "r") as f:
                idx = int(f.read().strip())
        except Exception:
            idx = 0
    idx = (idx + 1) % len(pool)
    with open(SESSION_IDX_PATH, "w") as f:
        f.write(str(idx))
    return pool[idx]

def _build_headers(extra: Optional[Dict[str, str]] = None, html: bool=False) -> Dict[str, str]:
    # UA havuzu: tek bir UA’a saplanma → küçük varyasyonlar
    chrome_builds = ["124.0", "125.0", "126.0", "127.0"]
    ua_desktop = (
        f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        f"(KHTML, like Gecko) Chrome/{chrome_builds[int(time.time()) % len(chrome_builds)]} Safari/537.36"
    )
    ig_android_builds = ["296.0.0.0.0", "297.0.0.0.0", "298.0.0.0.0"]
    ua_mobile = f"Instagram {ig_android_builds[int(time.time()/60) % len(ig_android_builds)]} Android"

    h = {
        "User-Agent": ua_desktop if html else ua_mobile,
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.instagram.com/"
    }
    # X-IG-App-ID sadece mobil modda
    if not html:
        h["X-IG-App-ID"] = IG_APP_ID

    if html:
        h["Sec-Fetch-Mode"] = "navigate"
        h["Sec-Fetch-Dest"] = "document"
    if extra:
        h.update(extra)
    return h

def _http_get(url: str, cookies: Optional[Dict[str, str]]=None, html: bool=False, timeout: int=12):
    return requests.get(url, headers=_build_headers(html=html), cookies=cookies or {}, timeout=timeout)


# === Cookie utils: "key1=val1; key2=val2; ..." metnini dict'e çevirir ===

def _load_sessions_list() -> list:
    if not os.path.exists(SESSIONS_PATH):
        return []
    with open(SESSIONS_PATH, encoding="utf-8") as f:
        try:
            return json.load(f)
        except Exception:
            return []

def _save_sessions_list(lst: list):
    with open(SESSIONS_PATH, "w", encoding="utf-8") as f:
        json.dump(lst, f, indent=2, ensure_ascii=False)

def _next_session_key(lst: list) -> str:
    # session_key sayısal string; en büyüğün +1’i
    mx = 0
    for s in lst:
        try:
            mx = max(mx, int(str(s.get("session_key") or "0")))
        except Exception:
            pass
    return str(mx + 1)



# --------------------------------------------------------------------------- #
#  PROFILE Yardımcıları                                                       #
# --------------------------------------------------------------------------- #
def _parse_username_or_url(s: str) -> Optional[str]:
    if not s:
        return None
    s = s.strip()
    m = re.search(r"(?:instagram\.com|instagr\.am)/([A-Za-z0-9_.]+)(?:/)?$", s)
    if m:
        return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9_.]{2,30}", s):
        return s
    return None

def _extract_video_url_from_gql(j: dict) -> Optional[str]:
    info = (
        j.get("data", {}).get("xdt_shortcode_media")
        or j.get("data", {}).get("shortcode_media") or {}
    )
    if not info:
        return None

    if (info.get("__typename", "").lower().endswith("video")):
        return (info.get("video_url")
                or (info.get("video_resources") or [{}])[0].get("src"))

    if "sidecar" in (info.get("__typename", "").lower()):
        for edge in info.get("edge_sidecar_to_children", {}).get("edges", []):
            node = edge.get("node", {})
            if node.get("__typename", "").lower().endswith("video"):
                return (node.get("video_url")
                        or (node.get("video_resources") or [{}])[0].get("src"))
    return None

def _extract_object_from(text: str, key: str) -> Optional[dict]:
    """
    text içinde '"<key>":{' veya '[' ile başlayan JSON’u
    parantez sayarak güvenli çıkarır. Döner: { key: ... } sözlüğü.
    """
    try:
        anchor = f'"{key}":'
        i = text.find(anchor)
        if i == -1:
            return None
        j = i + len(anchor)
        while j < len(text) and text[j] not in "{[":
            j += 1
        if j >= len(text):
            return None
        open_char = text[j]
        close_char = "}" if open_char == "{" else "]"
        depth, k = 0, j
        while k < len(text):
            c = text[k]
            if c == open_char:
                depth += 1
            elif c == close_char:
                depth -= 1
                if depth == 0:
                    blob = text[i:k+1]  # '"key":{...}' veya '"key":[...]'
                    js = "{" + blob + "}"
                    js = js.replace("\\u0026", "&").replace("\\/", "/")
                    return json.loads(js)
            k += 1
        return None
    except Exception as ex:
        logging.exception(f"_extract_object_from error: {ex}")
        return None

def _profile_html_fallback(username: str):
    """
    Cookie yoksa: https://www.instagram.com/<username>/ HTML’inden
    edge_owner_to_timeline_media’yı brace‑count ile çek.
    Döner: (profile_dict, posts_list, reels_list)
    """
    try:
        url = f"https://www.instagram.com/{username}/"
        r = _http_get(url, html=True)
        if r.status_code != 200:
            return None, [], []

        html = r.text

        avatar = None
        mava = re.search(r'"profile_pic_url_hd"\s*:\s*"([^"]+)"', html)
        if mava:
            avatar = mava.group(1).encode('utf-8').decode('unicode_escape')

        obj = _extract_object_from(html, "edge_owner_to_timeline_media")
        if not obj:
            return None, [], []

        media = obj.get("edge_owner_to_timeline_media", {})
        edges = (media.get("edges") or [])[:24]

        posts, reels = [], []
        for e in edges:
            node = (e or {}).get("node", {}) or {}
            is_video = bool(node.get("is_video"))
            display = node.get("display_url") or node.get("thumbnail_src") or ""
            caption = ""
            try:
                cap_edges = (node.get("edge_media_to_caption", {}).get("edges") or [])
                if cap_edges:
                    caption = (cap_edges[0].get("node", {}) or {}).get("text", "")
            except Exception:
                pass

            likes = (
                (node.get("edge_liked_by", {}) or {}).get("count")
                or (node.get("edge_media_preview_like", {}) or {}).get("count")
                or 0
            )
            comments = (node.get("edge_media_to_comment", {}) or {}).get("count", 0)
            views = (node.get("video_view_count") if is_video else 0) or 0
            ts = node.get("taken_at_timestamp") or 0

            item = {
                "type": "video" if is_video else "image",
                "url": display,
                "thumb": display,
                "caption": (caption or "")[:160],
                "download_url": display,
                "like_count": int(likes or 0),
                "comment_count": int(comments or 0),
                "view_count": int(views or 0),
                "timestamp": int(ts or 0)
            }
            posts.append(item)
            if is_video:
                reels.append(item)

        profile = {
            "username": username,
            "full_name": "",
            "avatar": avatar,
            "followers": 0,
            "following": 0,
            "posts_count": len(posts),
            "bio": "",
            "external_url": f"https://instagram.com/{username}"
        }

        return (profile, posts, reels)
    except Exception as ex:
        logging.exception(f"_profile_html_fallback error for {username}: {ex}")
        return None, [], []

def _get_uid(username: str) -> Optional[str]:
    url = f"https://i.instagram.com/api/v1/users/web_profile_info/?username={username}"
    for s in _cookie_pool():
        ck = {k: s.get(k, "") for k in ("sessionid", "ds_user_id", "csrftoken")}
        try:
            r = requests.get(url, headers=_build_headers(), cookies=ck, timeout=10)
            if r.status_code == 200 and "user" in r.text:
                return r.json()["data"]["user"]["id"]
        except Exception:
            continue
    try:
        r = _http_get(f"https://www.instagram.com/{username}/", html=True)
        m = re.search(r'"profilePage_(\d+)"', r.text)
        if m:
            return m.group(1)
    except Exception:
        pass
    return None

def _pick_thumb(node: dict, fallback_url: str = "") -> str:
    """
    Bir medya düğümünden en iyi küçük resmi çıkartır; çoklu fallback.
    """
    if not isinstance(node, dict):
        return fallback_url or ""
    # 1) image_versions2.candidates[0].url
    try:
        cand = (node.get("image_versions2", {}) or {}).get("candidates") or []
        if cand and cand[0].get("url"): 
            return cand[0]["url"]
    except Exception:
        pass
    # 2) additional_candidates.first_frame (video'larda)
    try:
        add = (node.get("image_versions2", {}) or {}).get("additional_candidates", {}) or {}
        if add.get("first_frame"):
            return add["first_frame"]
        if add.get("smart_thumbnail"):
            return add["smart_thumbnail"]
    except Exception:
        pass
    # 3) thumbnail_url
    if node.get("thumbnail_url"):
        return node["thumbnail_url"]
    # 4) display_url (GQL tarafında)
    if node.get("display_url"):
        return node["display_url"]
    # 5) video_versions ilk frame yoksa: video url'i bile olsa göster (son çare)
    if node.get("video_versions"):
        return fallback_url or (node["video_versions"][0].get("url") if node["video_versions"] else "") or ""
    # 6) en sonda fallback param
    return fallback_url or ""


def _normalize_post_item(it: dict) -> Optional[dict]:
    """
    Instagram 'feed/user' ya da 'clips/user' itemlerini tek tipe çevirir.
    Döner: {type, url, thumb, download_url, like_count, comment_count, view_count, timestamp}
    """
    if not it:
        return None

    node = it  # bazı akışlarda it zaten media düğümü
    # carousel
    if it.get("media_type") == 8 and it.get("carousel_media"):
        first = it["carousel_media"][0] or {}
        if first.get("video_versions"):
            u = (first["video_versions"][0] or {}).get("url", "")
            mtype = "video"
        else:
            u = (((first.get("image_versions2", {}) or {}).get("candidates") or [{}])[0]).get("url", "")
            mtype = "image"
        thumb = _pick_thumb(first, u)
    else:
        if it.get("video_versions"):
            u = (it["video_versions"][0] or {}).get("url", "")
            mtype = "video"
        else:
            u = (((it.get("image_versions2", {}) or {}).get("candidates") or [{}])[0]).get("url", "")
            mtype = "image"
        thumb = _pick_thumb(it, u)

    # caption
    cap_txt = ""
    try:
        cap = it.get("caption") or {}
        cap_txt = (cap.get("text") or "").strip()
    except Exception:
        pass

    # sayılar
    like_count = it.get("like_count") or (it.get("like_and_view_counts_disabled") and 0) or it.get("play_count") or 0
    comment_count = it.get("comment_count") or 0
    view_count = it.get("view_count") or it.get("play_count") or (like_count if mtype == "video" else 0)
    ts = it.get("taken_at") or 0

    return {
        "type": mtype,
        "url": u,
        "thumb": thumb or u,  # thumb boş kalmasın
        "caption": (cap_txt or "")[:160],
        "download_url": u,
        "like_count": int(like_count or 0),
        "comment_count": int(comment_count or 0),
        "view_count": int(view_count or 0),
        "timestamp": int(ts or 0)
    }

# ==== Profile pagination state (per visitor, per profile) ====================
def _pf_key(username: str, kind: str) -> str:
    return f"pf::{username}::{kind}"  # kind = feed | reels | highlights

def _pf_get(username: str, kind: str):
    return session.get(_pf_key(username, kind)) or {}

def _pf_set(username: str, kind: str, data: dict):
    session[_pf_key(username, kind)] = data

def _find_session_by_key(sk: str):
    if not sk: return None
    for s in _cookie_pool():
        if s.get("session_key") == sk:
            return s
    return None
def _set_used_session(sess_obj: dict):
    """Kullanılan session bilgilerini Flask session'a yazar (log için)."""
    try:
        if not sess_obj:
            return
        session["sessionid"] = sess_obj.get("sessionid","")
        session["user"]      = sess_obj.get("user","")
    except Exception:
        pass

def _cooldown_for(code: int, soft_n: int) -> int:
    """HTTP koda ve soft-fail sayısına göre dinamik saniye döndürür."""
    # Temel mantık: 401/403 => 10–30dk; 429 => 5–15dk; tekrarlandıkça artar.
    if code == 429:
        base = 300   # 5 dk
        step = 180   # +3 dk
    else:
        base = 600   # 10 dk
        step = 600   # +10 dk
    return min(base + (soft_n-1)*step, 3600)  # max 60 dk

# >>> NEW: Private API JSON GET + user feed & reels fetchers
# --- URL tabanlı JSON GET (cookie ile) --- #
def _api_json(url: str, s: dict, extra_headers: Optional[Dict[str, str]] = None, timeout: int = 12):
    """
    IG private/web API JSON GET.
    's' -> cookie havuzundan session objesi (sessionid, ds_user_id, csrftoken).
    200 -> r.json(), 401/403/429 -> soft-fail + dinamik cooldown (geçici block), diğerleri None.
    """
    if not url or not s:
        return None

    ck = {
        "sessionid":  s.get("sessionid", ""),
        "ds_user_id": s.get("ds_user_id", ""),
        "csrftoken":  s.get("csrftoken", "")
    }
    headers = _build_headers({"X-CSRFToken": ck["csrftoken"]})
    if extra_headers:
        headers.update(extra_headers)

    code = None
    try:
        r = requests.get(url, headers=headers, cookies=ck, timeout=timeout)
        code = r.status_code
        if code == 200:
            _clear_soft_fail(ck["sessionid"])
            try:
                return r.json()
            except Exception:
                return None

        # Sık görülen blok durumları
        if code in (401, 403, 429):
            n = _bump_soft_fail(ck["sessionid"])
            cool = _cooldown_for(code, n)
            try:
                block_session(ck["sessionid"], duration_sec=cool)
            except Exception:
                pass
            app.logger.error(f"_api_json AUTH/RATE {code} user={s.get('user')} n={n} cool={cool}s url={url[:80]}")
            return None

        # Diğer non-200
        app.logger.warning(f"_api_json non-200 {code} url={url}")
        return None

    except requests.Timeout:
        # Timeout → hafif artış (429 kadar değil)
        n = _bump_soft_fail(ck["sessionid"])
        cool = min(120 + (n-1)*60, 600)  # 2–10 dk
        try:
            block_session(ck["sessionid"], duration_sec=cool)
        except Exception:
            pass
        app.logger.warning(f"_api_json timeout user={s.get('user')} cool={cool}s url={url[:80]}")
        return None

    except Exception as e:
        app.logger.error(f"_api_json exception: {e}")
        return None

# ==== PAGED HELPERS (single page fetchers) ==================================
def _fetch_user_feed_page(uid: str, s: dict, max_id: Optional[str] = None, count: int = 12):
    """
    Önce /feed/user/{uid}/, olmazsa /users/{uid}/feed/ dener ve
    dönen öğeleri _normalize_post_item ile grid formatına çevirir.
    """
    def _norm_items(items):
        out = []
        for it in (items or []):
            n = _normalize_post_item(it)
            if n:
                out.append(n)
        return out

    # 1) feed/user
    url1 = f"https://i.instagram.com/api/v1/feed/user/{uid}/?count={count}"
    if max_id: url1 += f"&max_id={max_id}"
    j = _api_json(url1, s)
    if j:
        items = _norm_items(j.get("items") or [])
        next_max_id = j.get("next_max_id")
        if items:
            return items, next_max_id

    # 2) users/{uid}/feed
    url2 = f"https://i.instagram.com/api/v1/users/{uid}/feed/?count={count}"
    if max_id: url2 += f"&max_id={max_id}"
    j2 = _api_json(url2, s)
    if j2:
        items = _norm_items(j2.get("items") or [])
        next_max_id = j2.get("next_max_id")
        if items:
            return items, next_max_id

    return [], None

def _fetch_user_reels_page(uid: str, s: dict, max_id: Optional[str] = None, page_size: int = 50):
    """
    Reels/Clips için çoklu şema + sağlam paging.
    Döner: (normalized_items, next_max_id)
    """
    def _norm_list(lst):
        out = []
        for it in (lst or []):
            media = it.get("media") or it.get("item") or it
            n = _normalize_post_item(media)
            if n and n["type"] == "video":
                out.append(n)
        return out

    # 1) clips/user
    url = f"https://i.instagram.com/api/v1/clips/user/?target_user_id={uid}&page_size={page_size}"
    if max_id: url += f"&max_id={max_id}"
    j = _api_json(url, s)
    if j:
        items = (j.get("items") or j.get("clips") or j.get("clip_items") or [])
        arr = _norm_list(items)
        nxt = (j.get("paging_info") or {}).get("max_id") or j.get("next_max_id") or j.get("next_id")
        if not nxt and (j.get("paging_info") or {}).get("more_available"):
            nxt = (j.get("paging_info") or {}).get("max_id")
        if arr:
            return arr, nxt

    # 2) feed/user filtresi (clips)
    url2 = f"https://i.instagram.com/api/v1/feed/user/{uid}/?count={max(30, page_size)}"
    if max_id: url2 += f"&max_id={max_id}"
    j2 = _api_json(url2, s)
    if j2:
        filt = []
        for it in (j2.get("items") or []):
            if (it.get("product_type") or "").lower() == "clips" or bool(it.get("clips_metadata")):
                n = _normalize_post_item(it)
                if n and n["type"] == "video":
                    filt.append(n)
        nxt = j2.get("next_max_id") or j2.get("max_id") or (j2.get("paging_info") or {}).get("max_id")
        if filt:
            return filt, nxt

    return [], None

def _fetch_user_feed(uid: str, limit: int = 24) -> List[dict]:
    """
    Kullanıcının post (foto/video) akışını çeker: /api/v1/feed/user/{uid}/
    """
    pool = _cookie_pool()
    if not pool or not uid:
        return []

    collected, max_id = [], None
    for _ in range(3):
        for s in pool:
            base = f"https://i.instagram.com/api/v1/feed/user/{uid}/?count=12"
            url = base + (f"&max_id={max_id}" if max_id else "")
            j = _api_json(url, s)
            if not j:
                continue
            items = j.get("items") or []
            for it in items:
                norm = _normalize_post_item(it)
                if norm:
                    collected.append(norm)
                if len(collected) >= limit:
                    return collected[:limit]
            max_id = j.get("next_max_id")
            if not max_id:
                return collected[:limit]
            break
    return collected[:limit]

def _fetch_user_reels(uid: str, limit: int = 24) -> List[dict]:
    """
    Kullanıcının Reels videolarını çeker.
    """
    pool = _cookie_pool()
    if not pool or not uid:
        return []

    collected = []
    next_max_id = None

    for _ in range(3):
        for s in pool:
            base = f"https://i.instagram.com/api/v1/clips/user/?target_user_id={uid}&page_size=12"
            url = base + (f"&max_id={next_max_id}" if next_max_id else "")
            j = _api_json(url, s)
            if not j:
                continue

            items = j.get("items") or j.get("clips") or j.get("clip_items") or []
            for it in items:
                media = it.get("media") or it.get("item") or it
                norm = _normalize_post_item(media)
                if norm and norm["type"] == "video":
                    collected.append(norm)
                if len(collected) >= limit:
                    return collected[:limit]

            next_max_id = j.get("paging_info", {}).get("max_id") or j.get("next_max_id")
            if not next_max_id:
                return collected[:limit]
            break

    return collected[:limit]

def _get_profile_data(username: str):
    """
    Profil üst bilgileri + ilk medya sayfaları (post & reels) + stories + highlights.
    """
    uid = _get_uid(username)

    user = None
    profile = None
    posts, reels, stories, highlights = [], [], [], []

    # USER INFO
    pool = _cookie_pool()
    if pool:
        try:
            url = f"https://i.instagram.com/api/v1/users/web_profile_info/?username={username}"
            for s in pool:
                j = _api_json(url, s)
                if j and j.get("data", {}).get("user"):
                    user = j["data"]["user"]
                    break
        except Exception:
            user = None

    if user:
        profile = {
            "username": user.get("username"),
            "full_name": user.get("full_name") or "",
            "avatar": user.get("profile_pic_url_hd") or user.get("profile_pic_url"),
            "followers": user.get("edge_followed_by", {}).get("count", 0),
            "following": user.get("edge_follow", {}).get("count", 0),
            "posts_count": user.get("edge_owner_to_timeline_media", {}).get("count", 0),
            "bio": (user.get("biography") or "").strip(),
            "external_url": user.get("external_url") or f"https://instagram.com/{user.get('username','')}"
        }

    # İlk sayfa: FEED & REELS (çalışan cookie'yi bul ve pinle)
    if uid and pool:
        # FEED
        feed_items, feed_next, feed_sk = [], None, None
        for s in pool:
            try:
                items, nxt = _fetch_user_feed_page(uid, s, max_id=None, count=12)
                if items:
                    feed_items, feed_next, feed_sk = items, nxt, s.get("session_key")
                    break
            except Exception:
                continue
        if feed_items:
            posts = feed_items
            _set_used_session_by_key(feed_sk)
            _pf_set(username, "feed", {"session_key": feed_sk, "next_max_id": feed_next})
        else:
            _pf_set(username, "feed", {"session_key": None, "next_max_id": None})

        # REELS
        reels_items, reels_next, reels_sk = [], None, None
        for s in pool:
            try:
                items, nxt = _fetch_user_reels_page(uid, s, max_id=None, page_size=12)
                if items:
                    reels_items, reels_next, reels_sk = items, nxt, s.get("session_key")
                    break
            except Exception:
                continue
        if reels_items:
            reels = reels_items
            _set_used_session_by_key(reels_sk)
            _pf_set(username, "reels", {"session_key": reels_sk, "next_max_id": reels_next})
        else:
            _pf_set(username, "reels", {"session_key": None, "next_max_id": None})

    # Fallback HTML (hala boşsa)
    if not posts:
        prof_fb, posts_fb, reels_fb = _profile_html_fallback(username)
        if prof_fb and not profile:
            profile = prof_fb
        posts = posts or posts_fb
        reels = reels or reels_fb

    # STORIES
    if uid:
        st_raw, _sess = _get_stories(uid)
        if _sess:
            _set_used_session(_sess)
        if st_raw:
            for it in st_raw:
                stories.append({
                    "type": it.get("type"),
                    "url": it.get("media_url"),
                    "thumb": it.get("thumb"),
                    "caption": ""
                })

    # HIGHLIGHTS
    if uid:
        highlights = _get_highlights(uid) or []

    if not profile:
        profile = {
            "username": username,
            "full_name": "",
            "avatar": None,
            "followers": 0,
            "following": 0,
            "posts_count": len(posts),
            "bio": "",
            "external_url": f"https://instagram.com/{username}"
        }

    sections = {
        "posts": posts,
        "stories": stories,
        "highlights": highlights,
        "reels": reels or [i for i in posts if i.get("type") == "video"]
    }
    return profile, sections


def _set_used_session_by_key(sk: Optional[str]):
    if not sk:
        return
    sess = _find_session_by_key(sk)
    if sess:
        _set_used_session(sess)

# --------------------------------------------------------------------------- #
#  STORY İşlevleri                                                            #
# --------------------------------------------------------------------------- #

def _get_stories(uid: str):
    """
    Kullanıcının aktif story'lerini çeker.
    Thumb için güçlü fallback:
      - image_versions2.candidates[0].url
      - image_versions2.additional_candidates.first_frame (poster)
    """
    def _first_image(it: dict) -> str:
        # 1) standart candidate
        try:
            cands = (it.get("image_versions2", {}).get("candidates") or [])
            if cands:
                u = (cands[0] or {}).get("url", "")
                if u: return u
        except Exception:
            pass
        # 2) video poster / first_frame
        try:
            u = it.get("image_versions2", {}).get("additional_candidates", {}).get("first_frame", "")
            if u: return u
        except Exception:
            pass
        return ""

    pool = _cookie_pool()
    pool_len = len(pool)
    if pool_len == 0 or not uid:
        return None, None

    endpoints = [
        f"https://i.instagram.com/api/v1/feed/reels_media/?reel_ids={uid}",
        f"https://i.instagram.com/api/v1/feed/user/{uid}/reel_media/"
    ]

    last_key = None
    if os.path.exists(SESSION_IDX_PATH):
        try:
            with open(SESSION_IDX_PATH, "r") as f:
                last_key = f.read().strip()
        except Exception:
            last_key = None

    keys = [s.get("session_key") for s in pool]
    idx = 0
    if last_key and last_key in keys:
        idx = (keys.index(last_key) + 1) % pool_len

    for offset in range(pool_len):
        real_idx = (idx + offset) % pool_len
        s = pool[real_idx]
        ck = {
            "sessionid":  s.get("sessionid", ""),
            "ds_user_id": s.get("ds_user_id", ""),
            "csrftoken":  s.get("csrftoken", "")
        }
        headers = _build_headers({"X-CSRFToken": ck["csrftoken"]})

        for url in endpoints:
            try:
                r = requests.get(url, headers=headers, cookies=ck, timeout=10)
                if r.status_code == 200:
                    j = r.json()
                    items = []
                    if "reels_media" in j:
                        rm = (j.get("reels_media") or [])
                        if rm:
                            items = rm[0].get("items", []) or []
                    else:
                        items = j.get("items", []) or []

                    if not items:
                        continue

                    stories = []
                    for it in items:
                        thumb = _first_image(it)

                        if it.get("video_versions"):
                            media_url = (it["video_versions"][0] or {}).get("url", "")
                            typ = "video"
                            # thumb hâlâ boşsa tekrar deneriz (güvence)
                            if not thumb:
                                thumb = _first_image(it)
                        elif it.get("image_versions2"):
                            media_url = ((it.get("image_versions2", {}).get("candidates") or [{}])[0]).get("url", "")
                            typ = "image"
                        else:
                            continue

                        if not media_url:
                            continue

                        stories.append({
                            "media_url": media_url,
                            "thumb": thumb,
                            "type": typ
                        })

                    if stories:
                        try:
                            with open(SESSION_IDX_PATH, "w") as f:
                                f.write(s.get("session_key", ""))
                        except Exception:
                            pass
                        return stories, s

                else:
                    if r.status_code in (401, 403):
                        block_session(ck["sessionid"])
                        app.logger.error(
                            f"Story session AUTH blocked: {s.get('user')} ({ck.get('sessionid')}) - Status: {r.status_code}"
                        )
                    else:
                        app.logger.warning(
                            f"Story session non-200: {s.get('user')} - Status: {r.status_code}"
                        )

            except Exception as e:
                app.logger.error(
                    f"Story session exception: {s.get('user')} ({ck.get('sessionid')}) - {str(e)}"
                )

    try:
        if pool:
            with open(SESSION_IDX_PATH, "w") as f:
                next_idx = (idx + 1) % pool_len
                f.write(pool[next_idx].get("session_key", ""))
    except Exception:
        pass
    return None, None

def _get_highlights(uid: str):
    """
    Kullanıcının highlight tray listesini alır ve her highlight içinden ilk ~3 medyayı toplar.
    Thumb için güçlü fallback:
      - image_versions2.candidates[0].url
      - image_versions2.additional_candidates.first_frame
    """
    def _pick_thumb(node: dict) -> str:
        # 1) standart candidate
        try:
            cands = (node.get("image_versions2", {}).get("candidates") or [])
            if cands:
                u = (cands[0] or {}).get("url", "")
                if u: return u
        except Exception:
            pass
        # 2) video poster / first_frame
        try:
            u = node.get("image_versions2", {}).get("additional_candidates", {}).get("first_frame", "")
            if u: return u
        except Exception:
            pass
        return ""

    pool = _cookie_pool()
    if not pool or not uid:
        return []

    tray_url = f"https://i.instagram.com/api/v1/highlights/{uid}/highlights_tray/"
    items_all = []
    used_session_key = None

    for s in pool:
        ck = {
            "sessionid":  s.get("sessionid", ""),
            "ds_user_id": s.get("ds_user_id", ""),
            "csrftoken":  s.get("csrftoken", "")
        }
        try:
            r = requests.get(tray_url, headers=_build_headers(), cookies=ck, timeout=10)
            if r.status_code == 200 and "tray" in r.text:
                tray = (r.json().get("tray") or [])[:12]
                used_session_key = s.get("session_key")
                for t in tray:
                    hid = t.get("id") or t.get("reel_id")
                    if not hid:
                        continue
                    rm_url = f"https://i.instagram.com/api/v1/feed/reels_media/?reel_ids=highlight:{hid}"
                    try:
                        rr = requests.get(rm_url, headers=_build_headers(), cookies=ck, timeout=10)
                        if rr.status_code == 200:
                            j = rr.json()
                            reels_media = (j.get("reels_media") or [])
                            if not reels_media:
                                continue
                            media_items = (reels_media[0].get("items") or [])[:3]
                            for it in media_items:
                                thumb = _pick_thumb(it)
                                if it.get("video_versions"):
                                    media_url = (it["video_versions"][0] or {}).get("url", "")
                                    typ = "video"
                                    if not thumb:
                                        thumb = _pick_thumb(it)
                                elif it.get("image_versions2"):
                                    media_url = ((it.get("image_versions2", {}).get("candidates") or [{}])[0]).get("url", "")
                                    typ = "image"
                                else:
                                    continue
                                if not media_url:
                                    continue
                                items_all.append({
                                    "type": typ,
                                    "url": media_url,
                                    "thumb": thumb
                                })
                    except Exception:
                        continue
                break
        except Exception:
            continue

    if used_session_key and pool:
        try:
            with open(SESSION_IDX_PATH, "w") as f:
                f.write(used_session_key)
        except Exception:
            pass
    return items_all


def test_sessions():
    if not os.path.exists(SESSIONS_PATH):
        print("sessions.json yok")
        return
    with open(SESSIONS_PATH) as f:
        sessions = json.load(f)
    for s in sessions:
        ck = {k: s.get(k,"") for k in ("sessionid","ds_user_id","csrftoken")}
        try:
            r = requests.get("https://i.instagram.com/api/v1/accounts/current_user/", cookies=ck, timeout=10)
            print(f"{s.get('user')}: {r.status_code}")
        except Exception as e:
            print(f"{s.get('user')}: ERROR {e}")

# --------------------------------------------------------------------------- #
#  STANDART MEDYA (reel / video / fotoğraf / igtv)                            #
# --------------------------------------------------------------------------- #
def _extract_sc(url: str):
    m = re.search(r"/(reel|p|tv)/([A-Za-z0-9_-]{5,})", url)
    if not m:
        path = re.sub(r"https?://(?:www\.)?instagr\.am", "", url)
        m = re.search(r"/(reel|p|tv)/([A-Za-z0-9_-]{5,})", path)
    return m.group(2) if m else None

def _gql_url(sc: str):
    v = json.dumps({
        "shortcode": sc,
        "fetch_tagged_user_count": None,
        "hoisted_comment_id": None,
        "hoisted_reply_id": None
    })
    return ("https://www.instagram.com/graphql/query/"
            f"?doc_id=8845758582119845&variables={v}")

def _process_media(j: dict):
    info = (
        j.get("data",{}).get("xdt_shortcode_media")
        or j.get("data",{}).get("shortcode_media") or {}
    )
    if not info:
        return False

    typ = info.get("__typename","").lower()
    vurl, iurls = None, []

    if typ.endswith("video"):
        vurl = info.get("video_url") or (info.get("video_resources") or [{}])[0].get("src")
        session["video_url"] = vurl
    elif typ.endswith("image"):
        img = info.get("display_url") or (info.get("display_resources") or [{}])[-1].get("src")
        if img and not img.endswith(".heic"):
            iurls = [img]
        session["image_urls"] = iurls
    elif "sidecar" in typ:
        for edge in info.get("edge_sidecar_to_children",{}).get("edges",[]):
            node = edge.get("node",{})
            if node.get("__typename","").lower().endswith("video"):
                vurl = node.get("video_url") or (node.get("video_resources") or [{}])[0].get("src")
            else:
                iu = node.get("display_url") or (node.get("display_resources") or [{}])[-1].get("src")
                if iu and not iu.endswith(".heic"):
                    iurls.append(iu)
        session["video_url"]  = vurl
        session["image_urls"] = iurls

    session["thumbnail_url"] = (
        info.get("thumbnail_src")
        or (info.get("display_resources") or [{}])[0].get("src")
    )
    raw_title = (
        (info.get("edge_media_to_caption",{}).get("edges") or [{}])[0]
        .get("node",{}).get("text","")
    ) or info.get("owner",{}).get("username") or "instagram"
    title = re.sub(r'[^a-zA-Z0-9_\-]', '_', raw_title)[:50]
    session["video_title"] = title

    comments = [
        f"{e['node']['owner']['username']}: {e['node']['text']}"
        for e in info.get("edge_media_to_parent_comment",{}).get("edges",[])
    ]
    session["raw_comments"] = json.dumps(comments[:40])
    return bool(session.get("video_url") or session.get("image_urls"))

def _fetch_media(gql: str):
    """
    GraphQL medya detayını cookie havuzundan dener.
    """
    pool = _cookie_pool()
    if not pool:
        return None, None

    last_key = None
    if os.path.exists(SESSION_IDX_PATH):
        try:
            with open(SESSION_IDX_PATH, "r") as f:
                last_key = f.read().strip()
        except Exception:
            last_key = None

    keys = [s.get("session_key") for s in pool]
    idx = 0
    if last_key and last_key in keys:
        idx = (keys.index(last_key) + 1) % len(pool)

    for offset in range(len(pool)):
        real_idx = (idx + offset) % len(pool)
        s = pool[real_idx]
        ck = {
            "sessionid":  s.get("sessionid", ""),
            "ds_user_id": s.get("ds_user_id", ""),
            "csrftoken":  s.get("csrftoken", "")
        }
        try:
            r = requests.get(gql, headers=_build_headers(), cookies=ck, timeout=10)
            txt = r.text or ""
            if r.status_code == 200 and ("shortcode_media" in txt or "xdt_shortcode_media" in txt):
                try:
                    with open(SESSION_IDX_PATH, "w") as f:
                        f.write(s.get("session_key", ""))
                except Exception:
                    pass
                return r.json(), s
            else:
                if r.status_code in (401, 403):
                    block_session(ck["sessionid"])
                    app.logger.error(
                        f"Media session AUTH blocked: {s.get('user')} ({ck.get('sessionid')}) - Status: {r.status_code}"
                    )
                else:
                    app.logger.warning(
                        f"Media session non-200: {s.get('user')} - Status: {r.status_code}"
                    )
        except Exception as e:
            app.logger.error(
                f"Media session exception: {s.get('user')} ({ck.get('sessionid')}) - {str(e)}"
            )

    if pool:
        try:
            with open(SESSION_IDX_PATH, "w") as f:
                next_idx = (idx + 1) % len(pool)
                f.write(pool[next_idx].get("session_key", ""))
        except Exception:
            pass
    return None, None

# --------------------------------------------------------------------------- #
#  Flow Yardımcısı                                                            #
# --------------------------------------------------------------------------- #

def _media_flow(template: str, flag: str, lang=None):
    try:
        _clear_media_state()

        url = request.form.get("instagram_url","").strip()
        if not url:
            return render_template(template, error=_("Please enter a link."), lang=lang)

        session["last_target"] = url

        sc = _extract_sc(url)
        if not sc:
            return render_template(template, error=_("Enter a valid Instagram link."), lang=lang)

        data, used_session = _fetch_media(_gql_url(sc))
        if not data or not _process_media(data):
            return render_template(template, error=_("Media could not be retrieved, please try again."), lang=lang)

        if used_session:
            session["sessionid"] = used_session.get("sessionid", "")

        session[flag] = True
        return redirect(url_for("loading", lang=lang))

    except Exception:
        app.logger.exception("Media flow error")
        return render_template(template, error=_("Media could not be retrieved, please try again."), lang=lang)

def _check_referer_origin():
    """
    Same‑origin koruması: Origin/Referer kontrolü
    """
    origin  = (request.headers.get("Origin") or "").lower()
    referer = (request.headers.get("Referer") or "").lower()
    host    = request.host.lower()

    if origin:
        try:
            origin_host = origin.split("://", 1)[-1]
            origin_host = origin_host.split("/", 1)[0]
        except Exception:
            origin_host = origin
        if origin_host != host:
            return False

    if referer and (host not in referer):
        return False

    return True

# --------------------------------------------------------------------------- #
#  ROUTER’lar                                                                 #
# --------------------------------------------------------------------------- #
@app.errorhandler(404)
def not_found(e):
    lang = get_locale()
    return render_template("404.html", lang=lang), 404

# <<< ÖNEMLİ: "/" route TEK >>> #
@app.route("/", methods=["GET", "POST"])
def root():
    """
    - Varsayılan İngilizce içerik / üzerinde.
    - İlk gelişte tarayıcı diline göre /<dil>/ yönlendirmesi (tek seferlik).
    """
    if request.method == "POST":
        _clear_media_state()
        return index(lang="en")

    if not request.referrer:
        browser_lang = request.accept_languages.best_match(LANGUAGES)
        if browser_lang and browser_lang != "en":
            return redirect(url_for("index", lang=browser_lang), code=302)

    meta = get_meta("index", "en")
    return render_template("index.html", lang="en", meta=meta)

@app.route("/<lang>/", methods=["GET", "POST"])
def index(lang=None):
    if lang not in LANGUAGES:
        return redirect("/", code=302)

    meta = get_meta("index", lang)

    if request.method == "POST":
        _clear_media_state()

        raw_url = (request.form.get("instagram_url") or "").strip()
        if not raw_url:
            return render_template("index.html",
                                   error=_("Please enter a link."),
                                   lang=lang, meta=meta)

        url = raw_url.split('?')[0].rstrip('/')
        session["last_target"] = url

        # --- Story link akışı ---
        if "/stories/" in url:
            mh = re.search(r"(?:instagram\.com|instagr\.am)/stories/highlights/(\d+)", url)
            if mh:
                uid = f"highlight:{mh.group(1)}"
                uname = "highlight"
            else:
                m2 = re.search(r"(?:instagram\.com|instagr\.am)/stories/([A-Za-z0-9_.]+)", url)
                uname = m2.group(1) if m2 else None

            if not uname:
                return render_template("index.html",
                                       error=_("Enter a valid story link."),
                                       lang=lang, meta=meta)

            uid = _get_uid(uname)
            if not uid:
                return render_template("index.html",
                                       error=_("User info could not be retrieved."),
                                       lang=lang, meta=meta)

            stories, used_session = _get_stories(uid)
            if not stories:
                return render_template("index.html",
                                       error=_("No active story found."),
                                       lang=lang, meta=meta)

            session["stories"]    = stories
            session["username"]   = uname
            session["from_story"] = True
            if used_session:
                session["sessionid"] = used_session.get("sessionid", "")
            return redirect(url_for("loading", lang=lang))

        # --- PROFIL: /u göstermeden loading→download ile render et ---
        uname = _parse_username_or_url(url)
        if uname:
            session["last_target"] = f"https://instagram.com/{uname}"
            session["pending_profile_username"] = uname  # download'ta karşılayacağız
            return redirect(url_for("loading", lang=lang))

        # --- Standart medya akışı ---
        return _media_flow("index.html", "from_idx", lang=lang)

    return render_template("index.html", lang=lang, meta=meta)

@app.route('/<path:path>', methods=["GET", "POST"])
def catch_all_root(path):
    lang_match = re.fullmatch(r'[a-z]{2}', path.strip('/'))
    if lang_match:
        lang = path.strip('/')
        if lang in LANGUAGES:
            return redirect(url_for("index", lang=lang))
    lang = get_locale() if get_locale() in LANGUAGES else "en"
    return render_template("404.html", lang=lang), 404

# ---------------------------- LOADING / DOWNLOAD -----------------------------
@app.route("/loading", defaults={"lang": "en"})
@app.route("/<lang>/loading")
def loading(lang):
    r = _ensure_gate(lang)
    if r: return r
    r = _ensure_not_blacklisted()
    if r: return r
    r = _enforce_rate_limit(suffix=":loading")
    if r is not None:
        return r

    # --- PROFIL bekleniyor ise ---
    if session.get("pending_profile_username"):
        session["from_load"] = True
        return render_template("loading.html", lang=lang)

    # --- Hikaye / tekil medya flag'leri ---
    if session.get("from_story"):
        session["from_story"] = False
        session["from_load"]  = True
        return render_template("loading.html", lang=lang)

    flags = ["from_idx","from_video","from_fotograf","from_reels","from_igtv"]
    for f in flags:
        if session.get(f):
            session[f] = False
            session["from_load"] = True
            return render_template("loading.html", lang=lang)

    return redirect(url_for("index", lang=lang))

@app.route("/download", defaults={"lang": "en"})
@app.route("/<lang>/download")
@limiter.limit("20 per minute")
def download(lang):
    # --- GATE / BLACKLIST / RATE-LIMIT KONTROLLERİ --- #
    r = _ensure_gate(lang)
    if r is not None:
        return r

    r = _ensure_not_blacklisted()
    if r is not None:
        return r

    # NOT: _enforce_rate_limit() mutlaka "None" (devam) veya
    # bir Flask Response/dict/redirect döndürmeli. True/False döndürürse
    # Flask "bool döndü" hatası verir (TypeError).
    r = _enforce_rate_limit(suffix=":download")
    if r is not None:
        return r
    # --- /KONTROLLER --- #

    # /loading sayfasından gelinmediyse ana sayfaya dön.
    # (Bu kısım mevcut akışınızın bir parçası; bool dönmeyip redirect döndürüyoruz.)
    if not session.get("from_load"):
        return redirect(url_for("index", lang=lang))
    session["from_load"] = False

    # --- PROFİL: loading aşamasında bekletilen profil varsa burada render et

    # --- PROFİL: loading aşamasında bekletilen profil varsa burada render et
    pending = session.pop("pending_profile_username", None)
    if pending:
        try:
            profile, sections = _get_profile_data(pending)
            if not profile:
                return render_template(
                    "profile.html",
                    profile=None,
                    sections=None,
                    error=_("User info could not be retrieved."),
                    lang=lang
                )

            # --- LOG: profil görüntüleme/indirme bildirimi (ayrı try ile güvenli) ---
            try:
                sessid = session.get("sessionid", "")
                actor  = session.get("user", "")  # sessions.json’daki "user" etiketi
                if sessid or actor:
                    log_session_use(sessid, "success")
                    notify_download(actor)
                    if sessid:
                        update_session_counters(sessid, "success")
            except Exception:
                app.logger.exception("profile log error")

            return render_template("profile.html", profile=profile, sections=sections, lang=lang)

        except Exception:
            app.logger.exception("Pending profile render error")
            return render_template(
                "profile.html",
                profile=None,
                sections=None,
                error=_("Profile could not be loaded, please try again."),
                lang=lang
            )

    # --- Eski davranış: Hikaye / tekil medya indirme ekranı ---
    sessionid = session.get("sessionid", "")
    username = session.get("username", "") or session.get("user", "")

    # Username yoksa sessionid'den bulmayı dene (loglar için)
    if not username and sessionid:
        try:
            with open(SESSIONS_PATH, encoding="utf-8") as f:
                all_sessions = json.load(f)
            for s in all_sessions:
                if s.get("sessionid") == sessionid:
                    username = s.get("user", "")
                    break
        except Exception:
            pass

    # Başarılı akış logları
    if sessionid or username:
        try:
            log_session_use(sessionid, "success")
            notify_download(username)
            if sessionid:
                update_session_counters(sessionid, "success")
        except Exception:
            app.logger.exception("download log error")

    # Eğer story listesi varsa story_list.html'ü bas
    if session.get("stories"):
        return render_template(
            "story_list.html",
            stories=session["stories"],
            username=session.get("username", ""),
            lang=lang
        )

    # Tekil medya (video / foto) verilerini hazırla
    vurl   = session.get("video_url")
    imgs   = session.get("image_urls", []) or []
    poster = session.get("thumbnail_url", "")  # poster/thumbnail

    # --- İndirilebilirler listesini oluştur ---
    downloads = []

    # Video → imzalı proxy indir (tarayıcıda açılmaz, direkt indirilir)
    if vurl:
        safe_fn = (session.get("video_title") or "instavido").strip() or "instavido"
        downloads.append({
            "url":   sign_media_proxy(vurl, fn=safe_fn),  # /proxy_download?...sig=...
            "label": _("MP4"),
            "type":  "video",
            "thumb": poster
        })

    # Foto → kendi endpoint'imiz (attachment) /photo_download/<i>
    for i, im in enumerate(imgs):
        downloads.append({
            "url":   url_for("photo_dl", i=i),  # doğrudan attachment döner
            "label": f"IMG {i+1}",
            "type":  "image",
            "thumb": im
        })

    media = {
        "kind": ("video" if vurl else ("post" if downloads else None)),
        "downloads": downloads,
        "poster": poster
    }

    # Yorumlar
    raw_comments = session.get("raw_comments")
    try:
        comments = json.loads(raw_comments) if raw_comments else []
    except Exception:
        comments = []

    return render_template(
        "download.html",
        video_url     = vurl,
        image_urls    = imgs,
        thumbnail_url = poster,
        comments      = comments,
        media         = media,
        lang          = lang
    )


@app.route("/photo_download/<int:i>")
@limiter.limit("60 per minute")
def photo_dl(i):
    r = _enforce_rate_limit(suffix=":photo")
    if r: return r

    try:
        imgs = session.get("image_urls", [])
        if 0 <= i < len(imgs):
            rqs = requests.get(
                imgs[i],
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Referer": "https://www.instagram.com/",
                    "Accept": "*/*",
                    "Accept-Encoding": "identity",  # <<< önemli
                },
                stream=True, timeout=15
            )

            sessionid = session.get("sessionid", "")
            username = session.get("username", "") or session.get("user", "")
            if not username and sessionid:
                try:
                    with open(SESSIONS_PATH, encoding="utf-8") as f:
                        all_sessions = json.load(f)
                    for s in all_sessions:
                        if s.get("sessionid") == sessionid:
                            username = s.get("user", "")
                            break
                except Exception:
                    pass

            if sessionid or username:
                log_session_use(sessionid, "success")
                notify_download(username)
                if sessionid:
                    update_session_counters(sessionid, "success")

            def gen():
                for c in rqs.iter_content(65536):
                    if c: yield c

            resp = Response(
                gen(),
                mimetype=rqs.headers.get("Content-Type","image/jpeg"),
                direct_passthrough=True
            )
            resp.headers["Content-Disposition"] = f"attachment; filename=image_{i+1}.jpg"
            if rqs.headers.get("Content-Length"):
                resp.headers["Content-Length"] = rqs.headers["Content-Length"]
            resp.headers["Cache-Control"] = "no-transform, private, max-age=0"
            return resp
    except Exception:
        app.logger.exception(f"Error in photo_dl index={i}")
        sessionid = session.get("sessionid", "")
        if sessionid:
            update_session_counters(sessionid, "fail")
    return redirect(url_for("index"))

@app.route("/direct_download")
@limiter.limit("20 per minute")
def direct_dl():
    r = _enforce_rate_limit(suffix=":video")
    if r: return r

    try:
        url  = session.get("video_url")
        name = session.get("video_title","instagram_video") + ".mp4"
        if not url:
            return render_template("download.html",
                                   error=_("Video URL not found."),
                                   media={"downloads":[], "kind":None, "poster":""})
        rqs = requests.get(
            url, headers={"User-Agent":"Mozilla/5.0","Referer":"https://www.instagram.com/"},
            stream=True, timeout=10
        )
        if rqs.status_code != 200:
            raise RuntimeError
        sessionid = session.get("sessionid", "")
        username = session.get("username", "") or session.get("user", "")
        if not username and sessionid:
            try:
                with open(SESSIONS_PATH, encoding="utf-8") as f:
                    all_sessions = json.load(f)
                for s in all_sessions:
                    if s.get("sessionid") == sessionid:
                        username = s.get("user", "")
                        break
            except Exception:
                pass

        if sessionid or username:
            log_session_use(sessionid, "success")
            notify_download(username)
            if sessionid:
                update_session_counters(sessionid, "success")
        return Response(
            (c for c in rqs.iter_content(65536) if c),
            content_type=rqs.headers.get("Content-Type","video/mp4"),
            headers={"Content-Disposition": f'attachment; filename="{name}"'}
        )
    except Exception:
        app.logger.exception("Error in direct_dl")
        sessionid = session.get("sessionid", "")
        if sessionid:
            log_session_use(sessionid, "fail")
            update_session_counters(sessionid, "fail")
        return render_template("download.html",
                               error=_("Error occurred during download."),
                               media={"downloads":[], "kind":None, "poster":""})

# --- Safe proxy downloader (same-origin download) ---
@app.route("/proxy_download")
@limiter.limit("20 per minute")
def proxy_download():
    r = _enforce_rate_limit(suffix=":proxy_dl")
    if r: return r

    url   = (request.args.get("url") or "").strip()
    fn    = (request.args.get("fn") or "instavido").strip()
    exp   = (request.args.get("exp") or "").strip()
    nonce = (request.args.get("nonce") or "").strip()
    sig   = (request.args.get("sig") or "").strip()

    if not (MEDIA_PROXY_SECRET and url and fn and exp and nonce and sig):
        return "forbidden", 403
    try:
        if int(exp) < int(time.time()):
            return "expired", 403
    except Exception:
        return "bad exp", 400

    payload = f"url={url}&fn={fn}&exp={exp}&nonce={nonce}"
    good = _sign_payload(MEDIA_PROXY_SECRET, payload)
    if not hmac.compare_digest(good, sig):
        return "invalid signature", 403
    if not _check_referer_origin():
        return "forbidden", 403

    ALLOWED = (
        ".cdninstagram.com", ".fbcdn.net", ".cdninstagram.org",
        "instagram.f", "scontent.cdninstagram.com"
    )
    try:
        host = urlparse(url).hostname or ""
        if not any(host.endswith(dom) for dom in ALLOWED):
            return "domain not allowed", 400
    except Exception:
        pass

    try:
        up_headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://www.instagram.com/",
            "Accept": "*/*",
            "Accept-Encoding": "identity",  # <<< BOZULMAYAN BINARY
        }
        rq = requests.get(url, headers=up_headers, stream=True, timeout=20)
        if rq.status_code != 200:
            return f"upstream {rq.status_code}", 502

        mime = (rq.headers.get("Content-Type") or "application/octet-stream").split(";")[0]
        if "." not in fn:
            if "mp4" in mime: fn += ".mp4"
            elif "jpeg" in mime or "jpg" in mime: fn += ".jpg"
            elif "png" in mime: fn += ".png"

        def gen():
            for chunk in rq.iter_content(65536):
                if chunk:
                    yield chunk

        resp = Response(gen(), mimetype=mime, direct_passthrough=True)
        resp.headers["Content-Disposition"] = f'attachment; filename="{fn}"'
        resp.headers["Cache-Control"] = "no-transform, private, max-age=0"
        if rq.headers.get("Content-Length"):
            resp.headers["Content-Length"] = rq.headers["Content-Length"]
        return resp
    except Exception as e:
        app.logger.exception(f"proxy_download error: {e}")
        return "download error", 500

# --- IMG PROXY (SSRF-hardened & robust) ---
ALLOWED_IMG_HOSTS = (
    ".cdninstagram.com",
    ".fbcdn.net",
    ".cdninstagram.org",
    "instagram.f",
    "scontent.cdninstagram.com",
    "flagcdn.com",
    "i.imgur.com",
)

MAX_IMG_BYTES = 15 * 1024 * 1024
ALLOWED_IMG_MIME_PREFIX = ("image/",)

def _is_private_ip(hostname: str) -> bool:
    try:
        infos = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
        for fam, _, _, _, sockaddr in infos:
            ip = sockaddr[0]
            ip_obj = ipaddress.ip_address(ip)
            if (
                ip_obj.is_private
                or ip_obj.is_loopback
                or ip_obj.is_link_local
                or ip_obj.is_multicast
                or ip_obj.is_reserved
                or ip_obj.is_unspecified
            ):
                return True
        return False
    except Exception:
        return True

def _host_whitelisted(host: str) -> bool:
    host = (host or "").lower()
    return any(host.endswith(suf) for suf in ALLOWED_IMG_HOSTS)

def _safe_get_follow_redirects(url: str, headers: dict, timeout: int, max_hops: int = 3):
    cur = url
    for _ in range(max_hops + 1):
        pu = urlparse(cur)
        if pu.scheme not in ("http", "https"):
            return None, ("invalid scheme", 400)
        host = (pu.hostname or "").lower()
        if not _host_whitelisted(host):
            return None, ("domain not allowed", 400)
        if _is_private_ip(host):
            return None, ("private ip blocked", 400)

        try:
            r = requests.get(cur, headers=headers, timeout=timeout, stream=True, allow_redirects=False)
        except Exception as e:
            return None, (f"upstream error: {e}", 502)

        if r.is_redirect or r.is_permanent_redirect:
            loc = r.headers.get("Location")
            if not loc:
                try: r.close()
                except: pass
                return None, ("redirect without location", 502)
            cur = urljoin(cur, loc)
            continue

        return r, None

    return None, ("too many redirects", 310)

@app.route("/img_proxy", methods=["GET", "HEAD"])
@limiter.limit("120 per minute")
def img_pxy():
    rr = _enforce_rate_limit(suffix=":img_proxy")
    if rr: return rr

    u     = (request.args.get("url") or "").strip()
    exp   = (request.args.get("exp") or "").strip()
    nonce = (request.args.get("nonce") or "").strip()
    sig   = (request.args.get("sig") or "").strip()

    if not (IMG_PROXY_SECRET and u and exp and nonce and sig):
        return "forbidden", 403
    try:
        if int(exp) < int(time.time()):
            return "expired", 403
    except Exception:
        return "bad exp", 400
    payload = f"url={u}&exp={exp}&nonce={nonce}"
    good = _sign_payload(IMG_PROXY_SECRET, payload)
    if not hmac.compare_digest(good, sig):
        return "invalid signature", 403
    if not _check_referer_origin():
        return "forbidden", 403

    pu = urlparse(u)
    if pu.scheme not in ("http", "https"):
        return "invalid scheme", 400
    host = (pu.hostname or "").lower()
    if not _host_whitelisted(host):
        return "domain not allowed", 400
    if _is_private_ip(host):
        return "private ip blocked", 400

    if request.method == "HEAD":
        return ("", 204, {"Content-Type": "image/*"})

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "image/avif,image/webp,image/apng,image/*;q=0.8,*/*;q=0.5",
        "Referer": "https://www.instagram.com/",
        "Accept-Encoding": "identity",
    }

    r, err = _safe_get_follow_redirects(u, headers=headers, timeout=10, max_hops=3)
    if err:
        msg, code = err
        app.logger.warning(f"img_proxy reject: {u} -> {msg}")
        return msg, code

    if r.status_code != 200:
        msg = f"upstream status {r.status_code}"
        try: r.close()
        except: pass
        return msg, r.status_code

    mime = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
    if not any(mime.startswith(p) for p in ALLOWED_IMG_MIME_PREFIX):
        try: r.close()
        except: pass
        return "unsupported content-type", 415

    try:
        clen = int(r.headers.get("Content-Length", "0"))
    except ValueError:
        clen = 0
    if clen and clen > MAX_IMG_BYTES:
        try: r.close()
        except: pass
        return "too large", 413

    try:
        total = 0
        buf = bytearray()
        for chunk in r.iter_content(65536):
            if not chunk:
                continue
            total += len(chunk)
            if total > MAX_IMG_BYTES:
                try: r.close()
                except: pass
                return "too large", 413
            buf.extend(chunk)
    except Exception as e:
        try: r.close()
        except: pass
        app.logger.error(f"img_proxy read error for {u}: {e}")
        return "upstream read error", 502
    finally:
        try: r.close()
        except: pass

    return send_file(io.BytesIO(bytes(buf)), mimetype=(mime or "image/jpeg"))

# kısa yollar
@app.route("/video", defaults={"lang": "en"}, methods=["GET", "POST"])
@app.route("/<lang>/video", methods=["GET", "POST"])
def video(lang):
    meta = get_meta("video", lang)
    if request.method == "POST":
        _clear_media_state()

        raw_url = request.form.get("instagram_url", "").strip()
        if not raw_url:
            return render_template("video.html", error=_("Please enter a link."), lang=lang, meta=meta)

        url = raw_url.split('?')[0].rstrip('/')
        session["last_target"] = url

        if "/stories/" in url:
            mh = re.search(r"(?:instagram\.com|instagr\.am)/stories/highlights/(\d+)", url)
            if mh:
                uid = f"highlight:{mh.group(1)}"
                uname = "highlight"
            else:
                m2 = re.search(r"(?:instagram\.com|instagr\.am)/stories/([A-Za-z0-9_.]+)", url)
                uname = m2.group(1) if m2 else None

            if not uname:
                return render_template("video.html", error=_("Enter a valid story link."), lang=lang, meta=meta)

            uid = _get_uid(uname)
            if not uid:
                return render_template("video.html", error=_("User info could not be retrieved."), lang=lang, meta=meta)

            stories, used_session = _get_stories(uid)
            if not stories:
                return render_template("video.html", error=_("No active story found."), lang=lang, meta=meta)

            session["stories"]    = stories
            session["username"]   = uname
            session["from_story"] = True
            if used_session:
                session["sessionid"] = used_session.get("sessionid", "")
            return redirect(url_for("loading", lang=lang))

        mprof = re.search(r"(?:instagram\.com|instagr\.am)/([A-Za-z0-9_.]+)$", url)
        if mprof:
            uname = mprof.group(1)
            uid = _get_uid(uname)
            if not uid:
                return render_template("video.html", error=_("User info could not be retrieved."), lang=lang, meta=meta)

            stories, used_session = _get_stories(uid)
            if not stories:
                return render_template("video.html", error=_("No active story found."), lang=lang, meta=meta)

            session["stories"]    = stories
            session["username"]   = uname
            session["from_story"] = True
            if used_session:
                session["sessionid"] = used_session.get("sessionid", "")
            return redirect(url_for("loading", lang=lang))

        return _media_flow("video.html", "from_video", lang=lang)

    return render_template("video.html", lang=lang, meta=meta)

@app.route("/photo", defaults={"lang": "en"}, methods=["GET", "POST"])
@app.route("/<lang>/photo", methods=["GET", "POST"])
def photo(lang):
    meta = get_meta("photo", lang)
    if request.method == "POST":
        _clear_media_state()

        raw_url = request.form.get("instagram_url", "").strip()
        if not raw_url:
            return render_template("photo.html", error=_("Please enter a link."), lang=lang, meta=meta)

        url = raw_url.split('?')[0].rstrip('/')
        session["last_target"] = url

        if "/stories/" in url:
            mh = re.search(r"(?:instagram\.com|instagr\.am)/stories/highlights/(\d+)", url)
            if mh:
                uid = f"highlight:{mh.group(1)}"
                uname = "highlight"
            else:
                m2 = re.search(r"(?:instagram\.com|instagr\.am)/stories/([A-Za-z0-9_.]+)", url)
                uname = m2.group(1) if m2 else None

            if not uname:
                return render_template("photo.html", error=_("Enter a valid story link."), lang=lang, meta=meta)

            uid = _get_uid(uname)
            if not uid:
                return render_template("photo.html", error=_("User info could not be retrieved."), lang=lang, meta=meta)

            stories, used_session = _get_stories(uid)
            if not stories:
                return render_template("photo.html", error=_("No active story found."), lang=lang, meta=meta)

            session["stories"]    = stories
            session["username"]   = uname
            session["from_story"] = True
            if used_session:
                session["sessionid"] = used_session.get("sessionid", "")
            return redirect(url_for("loading", lang=lang))

        mprof = re.search(r"(?:instagram\.com|instagr\.am)/([A-Za-z0-9_.]+)$", url)
        if mprof:
            uname = mprof.group(1)
            uid = _get_uid(uname)
            if not uid:
                return render_template("photo.html", error=_("User info could not be retrieved."), lang=lang, meta=meta)

            stories, used_session = _get_stories(uid)
            if not stories:
                return render_template("photo.html", error=_("No active story found."), lang=lang, meta=meta)

            session["stories"]    = stories
            session["username"]   = uname
            session["from_story"] = True
            if used_session:
                session["sessionid"] = used_session.get("sessionid", "")
            return redirect(url_for("loading", lang=lang))

        return _media_flow("photo.html", "from_fotograf", lang=lang)

    return render_template("photo.html", lang=lang, meta=meta)

@app.route("/reels", defaults={"lang": "en"}, methods=["GET", "POST"])
@app.route("/<lang>/reels", methods=["GET", "POST"])
def reels(lang):
    meta = get_meta("reels", lang)
    if request.method == "POST":
        _clear_media_state()

        raw_url = request.form.get("instagram_url", "").strip()
        if not raw_url:
            return render_template("reels.html", error=_("Please enter a link."), lang=lang, meta=meta)

        url = raw_url.split('?')[0].rstrip('/')
        session["last_target"] = url

        if "/stories/" in url:
            mh = re.search(r"(?:instagram\.com|instagr\.am)/stories/highlights/(\d+)", url)
            if mh:
                uid = f"highlight:{mh.group(1)}"
                uname = "highlight"
            else:
                m2 = re.search(r"(?:instagram\.com|instagr\.am)/stories/([A-Za-z0-9_.]+)", url)
                uname = m2.group(1) if m2 else None

            if not uname:
                return render_template("reels.html", error=_("Enter a valid story link."), lang=lang, meta=meta)

            uid = _get_uid(uname)
            if not uid:
                return render_template("reels.html", error=_("User info could not be retrieved."), lang=lang, meta=meta)

            stories, used_session = _get_stories(uid)
            if not stories:
                return render_template("reels.html", error=_("No active story found."), lang=lang, meta=meta)

            session["stories"]    = stories
            session["username"]   = uname
            session["from_story"] = True
            if used_session:
                session["sessionid"] = used_session.get("sessionid", "")
            return redirect(url_for("loading", lang=lang))

        mprof = re.search(r"(?:instagram\.com|instagr\.am)/([A-Za-z0-9_.]+)$", url)
        if mprof:
            uname = mprof.group(1)
            uid = _get_uid(uname)
            if not uid:
                return render_template("reels.html", error=_("User info could not be retrieved."), lang=lang, meta=meta)

            stories, used_session = _get_stories(uid)
            if not stories:
                return render_template("reels.html", error=_("No active story found."), lang=lang, meta=meta)

            session["stories"]    = stories
            session["username"]   = uname
            session["from_story"] = True
            if used_session:
                session["sessionid"] = used_session.get("sessionid", "")
            return redirect(url_for("loading", lang=lang))

        return _media_flow("reels.html", "from_reels", lang=lang)

    return render_template("reels.html", lang=lang, meta=meta)
@app.route("/igtv", defaults={"lang": "en"}, methods=["GET", "POST"])
@app.route("/<lang>/igtv", methods=["GET", "POST"])
def igtv(lang):
    meta = get_meta("igtv", lang)
    if request.method == "POST":
        _clear_media_state()

        raw_url = request.form.get("instagram_url", "").strip()
        if not raw_url:
            return render_template("igtv.html", error=_("Please enter a link."), lang=lang, meta=meta)

        url = raw_url.split('?')[0].rstrip('/')
        session["last_target"] = url

        if "/stories/" in url:
            mh = re.search(r"(?:instagram\.com|instagr\.am)/stories/highlights/(\d+)", url)
            if mh:
                uid = f"highlight:{mh.group(1)}"
                uname = "highlight"
            else:
                m2 = re.search(r"(?:instagram\.com|instagr\.am)/stories/([A-Za-z0-9_.]+)", url)
                uname = m2.group(1) if m2 else None

            if not uname:
                return render_template("igtv.html", error=_("Enter a valid story link."), lang=lang, meta=meta)

            uid = _get_uid(uname)
            if not uid:
                return render_template("igtv.html", error=_("User info could not be retrieved."), lang=lang, meta=meta)

            stories, used_session = _get_stories(uid)
            if not stories:
                return render_template("igtv.html", error=_("No active story found."), lang=lang, meta=meta)

            session["stories"]    = stories
            session["username"]   = uname
            session["from_story"] = True
            if used_session:
                session["sessionid"] = used_session.get("sessionid", "")
            return redirect(url_for("loading", lang=lang))

        mprof = re.search(r"(?:instagram\.com|instagr\.am)/([A-Za-z0-9_.]+)$", url)
        if mprof:
            uname = mprof.group(1)
            uid = _get_uid(uname)
            if not uid:
                return render_template("igtv.html", error=_("User info could not be retrieved."), lang=lang, meta=meta)

            stories, used_session = _get_stories(uid)
            if not stories:
                return render_template("igtv.html", error=_("No active story found."), lang=lang, meta=meta)

            session["stories"]    = stories
            session["username"]   = uname
            session["from_story"] = True
            if used_session:
                session["sessionid"] = used_session.get("sessionid", "")
            return redirect(url_for("loading", lang=lang))

        return _media_flow("igtv.html", "from_igtv", lang=lang)

    return render_template("igtv.html", lang=lang, meta=meta)

@app.route("/story", defaults={"lang": "en"}, methods=["GET", "POST"])
@app.route("/<lang>/story", methods=["GET", "POST"])
def story(lang):
    meta = get_meta("story", lang)
    if request.method == "POST":
        _clear_media_state()

        raw_url = request.form.get("instagram_url", "").strip()
        if not raw_url:
            return render_template("story.html", error=_("Please enter a link."), lang=lang, meta=meta)

        url = raw_url.split('?')[0].rstrip('/')

        session["last_target"] = url

        if "/stories/" in url:
            mh = re.search(
                r"(?:instagram\.com|instagr\.am)/stories/highlights/(\d+)",
                url
            )
            if mh:
                uid = f"highlight:{mh.group(1)}"
                uname = "highlight"
            else:
                m2 = re.search(
                    r"(?:instagram\.com|instagr\.am)/stories/([A-Za-z0-9_.]+)",
                    url
                )
                uname = m2.group(1) if m2 else None

            if not uname:
                return render_template("story.html", error=_("Enter a valid story link."), lang=lang, meta=meta)

        else:
            mprof = re.search(r"(?:instagram\.com|instagr\.am)/([A-Za-z0-9_.]+)$", url)
            if not mprof:
                return render_template("story.html", error=_("Enter a valid profile or story link."), lang=lang, meta=meta)
            uname = mprof.group(1)

        uid = _get_uid(uname)
        if not uid:
            return render_template("story.html", error=_("User info could not be retrieved."), lang=lang, meta=meta)

        stories, used_session = _get_stories(uid)
        if not stories:
            return render_template("story.html", error=_("No active story found."), lang=lang, meta=meta)

        session["stories"]    = stories
        session["username"]   = uname
        session["from_story"] = True
        if used_session:
            session["sessionid"] = used_session.get("sessionid", "")
        return redirect(url_for("loading", lang=lang))

    return render_template("story.html", lang=lang, meta=meta)

@app.route("/story-download/<int:i>")
@limiter.limit("20 per minute")
def story_download(i):
    # İsteğe küçük hız limiti (opsiyonel ama tutarlı olsun)
    r = _enforce_rate_limit(suffix=":story_dl")
    if r:
        return r

    try:
        stories = session.get("stories", [])
        if not stories or i < 0 or i >= len(stories):
            return "Story not found", 404

        story = stories[i]
        media_url = story.get("media_url")
        if not media_url:
            return "Media URL not found", 404

        ext = "mp4" if story.get("type") == "video" else "jpg"

        rqs = requests.get(
            media_url,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://www.instagram.com/",
                "Accept": "*/*",
                "Accept-Encoding": "identity",
            },
            stream=True,
            timeout=15
        )
        if rqs.status_code != 200:
            return "Download error", 502

        # -------- LOG: güvenli try/except içinde -------------
        try:
            sessid = session.get("sessionid", "")
            actor  = session.get("username", "") or session.get("user", "")

            # actor yoksa sessions.json’dan bulmayı dene
            if not actor and sessid:
                try:
                    with open(SESSIONS_PATH, encoding="utf-8") as f:
                        all_sessions = json.load(f)
                    for s in all_sessions:
                        if s.get("sessionid") == sessid:
                            actor = s.get("user", "")
                            break
                except Exception:
                    pass

            if sessid or actor:
                log_session_use(sessid, "success")
                notify_download(actor)
                if sessid:
                    update_session_counters(sessid, "success")
        except Exception:
            app.logger.exception("story_download log error")
        # ------------------------------------------------------

        return Response(
            (c for c in rqs.iter_content(65536) if c),
            content_type=("video/mp4" if ext == "mp4" else "image/jpeg"),
            headers={"Content-Disposition": f'attachment; filename=story_{i}.{ext}'}
        )

    except Exception as e:
        app.logger.error(f"Story download error: {e}")
        # İsteğe bağlı: sayaçları fail olarak güncelle
        try:
            sessionid = session.get("sessionid", "")
            if sessionid:
                update_session_counters(sessionid, "fail")
        except Exception:
            pass
        return "Download error", 500

@app.route("/profile", defaults={"lang": "en"}, methods=["GET", "POST"])
@app.route("/<lang>/profile", methods=["GET", "POST"])
def profile_search(lang):
    r = _ensure_gate(lang)
    if r: return r
    r = _ensure_not_blacklisted()
    if r: return r
    r = _enforce_rate_limit(suffix=":profile_search")
    if r: return r

    if request.method == "POST":
        raw = (request.form.get("instagram_url") or "").strip()
        uname = _parse_username_or_url(raw)
        if not uname:
            return render_template("index.html",
                                   error=_("Enter a valid profile username or URL."),
                                   lang=lang)
        session["last_target"] = f"https://instagram.com/{uname}"
        session["pending_profile_username"] = uname
        return redirect(url_for("loading", lang=lang))

    return render_template("profile.html", profile=None, sections=None, lang=lang)

# --- SONRADAN EKLEME: signing helpers (IMG + MEDIA tek endpoint) ---
@app.route("/api/sign", methods=["POST"])
def api_sign():
    # sadece kendi sayfalarımızdan çağrı
    if not _has_allowed_referer(request):
        return jsonify({"ok": False, "err": "forbidden"}), 403
    try:
        data = request.get_json(force=True) or {}
        url  = (data.get("url") or "").strip()
        fn   = (data.get("fn") or "instavido").strip()
        kind = (data.get("kind") or "media").strip()  # "media" | "img"
        if not url:
            return jsonify({"ok": False, "err": "missing url"}), 400

        if kind == "img":
            signed = sign_img_proxy(url, 900)  # -> "/img_proxy?...sig=..."
        else:
            signed = sign_media_proxy(url, fn=fn, ttl_sec=900)  # -> "/proxy_download?...sig=..."

        return jsonify({"ok": True, "url": signed})
    except Exception as e:
        app.logger.error(f"/api/sign error: {e}")
        return jsonify({"ok": False, "err": "server"}), 500

# ---- Date range helper (YYYY-MM-DD -> epoch) --------------------------------
# ---- Date range helper (YYYY-MM-DD -> epoch) --------------------------------
def _parse_date_range_args():
    """
    Query: ?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD
    Döner: (start_ts, end_ts) — end gün sonu. (start>end ise swap)
    """
    df = (request.args.get("date_from") or "").strip()
    dt = (request.args.get("date_to") or "").strip()

    def _to_ts(s):
        if not s: return None
        try:
            t = time.strptime(s, "%Y-%m-%d")
            return int(time.mktime(t))
        except Exception:
            return None

    start = _to_ts(df)
    end   = _to_ts(dt)
    if end is not None:
        end = end + 86399  # gün sonu

    # start > end ise takas et
    if start is not None and end is not None and start > end:
        start, end = end - 86399, end

    return start, end



# ===========================================================================#
#                          PROFILE AJAX API                                   #
# ===========================================================================#
def _any_session():
    pool = _cookie_pool()
    if not pool:
        return None
    return pool[0]

@app.route("/api/u/<username>/feed")
@limiter.limit("100 per minute")
def api_profile_feed(username):
    uname = _parse_username_or_url(username)
    if not uname:
        return jsonify({"ok": False, "error": "bad_username"}), 400
    uid = _get_uid(uname)
    if not uid:
        return jsonify({"ok": False, "error": "no_uid"}), 404

    pool = _cookie_pool()
    if not pool:
        return jsonify({"ok": False, "error": "no_session"}), 503

    # tarih aralığı (YYYY-MM-DD)
    ts_start, ts_end = _parse_date_range_args()

    st = _pf_get(uname, "feed")
    max_id = request.args.get("max_id") or st.get("next_max_id") or None
    count  = int(request.args.get("count", 12))

    s = _find_session_by_key(st.get("session_key"))
    def _filter_by_date(items):
        if not (ts_start or ts_end): 
            return items
        out = []
        for it in (items or []):
            t = int(it.get("timestamp") or 0)
            if ts_start and t < ts_start: 
                continue
            if ts_end   and t > ts_end:   
                continue
            out.append(it)
        return out

    if s:
        items, nxt = _fetch_user_feed_page(uid, s, max_id=max_id, count=count)
        items = _filter_by_date(items)
        if items:
            _pf_set(uname, "feed", {"session_key": s.get("session_key"), "next_max_id": nxt})
            return jsonify({"ok": True, "items": items, "next_max_id": nxt})

    for s in pool:
        items, nxt = _fetch_user_feed_page(uid, s, max_id=max_id, count=count)
        items = _filter_by_date(items)
        if items or nxt is not None:
            _pf_set(uname, "feed", {"session_key": s.get("session_key"), "next_max_id": nxt})
            return jsonify({"ok": True, "items": items, "next_max_id": nxt})

    _pf_set(uname, "feed", {"session_key": None, "next_max_id": None})
    return jsonify({"ok": True, "items": [], "next_max_id": None})

@app.route("/api/u/<username>/reels")
@limiter.limit("100 per minute")
def api_user_reels(username):
    uname = _parse_username_or_url(username)
    if not uname:
        return jsonify({"ok": False, "error": "bad_username"}), 400

    uid = _get_uid(uname)
    if not uid:
        return jsonify({"ok": False, "error": "no_uid"}), 404

    raw_token  = (request.args.get("max_id") or "").strip()
    page_size  = int(request.args.get("page_size") or 50)
    page_size  = max(10, min(page_size, 50))
    want_debug = request.args.get("debug") == "1"

    # tarih aralığı
    ts_start, ts_end = _parse_date_range_args()

    pool = _cookie_pool()
    if not pool:
        return jsonify({"ok": False, "error": "no_session"}), 503

    def parse_token(t):
        if not t:                  return ("CLIPS", "")
        if t.startswith("CLIPS:"): return ("CLIPS", t[6:])
        if t.startswith("FEED:"):  return ("FEED",  t[5:])
        return ("CLIPS", t)

    src, max_id = parse_token(raw_token)

    def _req(url, s, extra_headers=None):
        ck = {k: s.get(k, "") for k in ("sessionid","ds_user_id","csrftoken")}
        h  = _build_headers({"X-CSRFToken": ck["csrftoken"]})
        if extra_headers: h.update(extra_headers)
        try:
            r = requests.get(url, headers=h, cookies=ck, timeout=12)
            if r.status_code == 200:
                return r.json(), s, url
        except Exception:
            pass
        return None, None, url

    def strip_query(u: str) -> str:
        try:    return (u or "").split("?")[0]
        except: return u or ""

    def first_url(node, key):
        try:
            arr = node.get(key, {}).get("candidates") or []
            return (arr[0] or {}).get("url", "")
        except Exception:
            return ""

    def pick_id(node: dict, fallback_url: str) -> str:
        sid = (node.get("pk") or node.get("id") or node.get("shortcode") or node.get("code"))
        if sid is None:
            sid = strip_query(fallback_url or "")
        return str(sid)

    used = None
    used_url = None
    data = None
    items_raw = []
    next_token = None
    debug_info = {"flow": src, "hit": None}

    # ---- 1) CLIPS flow
    if src == "CLIPS":
        urls = [
            f"https://i.instagram.com/api/v1/clips/user/?target_user_id={uid}&page_size={page_size}"
            + (f"&max_id={max_id}" if max_id else ""),
            f"https://i.instagram.com/api/v1/feed/user/{uid}/clips/?count={page_size}"
            + (f"&max_id={max_id}" if max_id else "")
        ]
        for s in pool:
            for u in urls:
                j, used, used_url = _req(u, s)
                if j and (("items" in j) or ("clips" in j) or ("paging_info" in j) or ("next_max_id" in j)):
                    data = j
                    break
            if data: break

        if data:
            items_raw = data.get("items") or data.get("clips") or []
            next_clips = (
                (data.get("paging_info") or {}).get("max_id")
                or data.get("next_max_id")
                or data.get("max_id")
                or (data.get("paging_info") or {}).get("next_max_id")
                or (data.get("paging_info") or {}).get("next_id")
                or data.get("next_id")
            )
            if isinstance(next_clips, str) and not next_clips.strip():
                next_clips = None
            next_token = f"CLIPS:{next_clips}" if next_clips else "FEED:"
            debug_info.update({"hit": used_url, "keys": list(data.keys()), "len_items": len(items_raw)})

    # ---- 2) FEED fallback
    if (src == "FEED") or (data is None):
        feed_max = max_id if src == "FEED" else ""
        urls = [
            f"https://i.instagram.com/api/v1/feed/user/{uid}/?count={max(30, page_size)}"
            + (f"&max_id={feed_max}" if feed_max else "")
        ]
        if not items_raw:
            for s in pool:
                for u in urls:
                    j, used, used_url = _req(u, s)
                    if j and ("items" in j or "num_results" in j or "more_available" in j):
                        data = j
                        break
                if data: break

            if data:
                items_raw = data.get("items") or []
                feed_next = (
                    data.get("next_max_id")
                    or data.get("max_id")
                    or (data.get("paging_info") or {}).get("max_id")
                    or (data.get("page_info") or {}).get("end_cursor")
                    or data.get("next_id")
                )
                if isinstance(feed_next, str) and not feed_next.strip():
                    feed_next = None
                next_token = f"FEED:{feed_next}" if feed_next else None
                debug_info.update({"flow": "FEED", "hit": used_url, "len_items": len(items_raw)})

    # ---- Normalize + DATE FILTER
    out = []
    seen = set()
    for it in items_raw:
        node = it.get("media", it) or {}
        ptype = node.get("product_type") or it.get("product_type")
        clips_meta = node.get("clips_metadata") or {}
        is_reel = (ptype == "clips") or bool(clips_meta)
        if not is_reel:
            continue

        vvers = node.get("video_versions") or clips_meta.get("video_versions")
        if not vvers:
            continue

        vurl = (vvers[0] or {}).get("url", "")
        if not vurl:
            continue

        thumb = first_url(node, "image_versions2")
        if not thumb:
            thumb = node.get("thumbnail_url") \
                 or node.get("image_versions2",{}).get("additional_candidates",{}).get("first_frame", "")

        ts = int(node.get("taken_at") or it.get("taken_at") or 0)

        # tarih filtresi burada uygulanır
        if ts_start and ts < ts_start:
            continue
        if ts_end and ts > ts_end:
            continue

        _id = pick_id(node, vurl)
        if _id in seen:
            continue
        seen.add(_id)

        likes    = node.get("like_count") or it.get("like_count") or 0
        comments = node.get("comment_count") or it.get("comment_count") or 0
        views    = node.get("view_count") or node.get("play_count") or it.get("view_count") or 0

        out.append({
            "id": _id,
            "type": "video",
            "url": vurl,
            "thumb": thumb,
            "download_url": vurl,
            "like_count": int(likes or 0),
            "comment_count": int(comments or 0),
            "view_count": int(views or 0),
            "timestamp": ts
        })

    if next_token and (next_token == raw_token):
        next_token = None

    try:
        if used:
            with open(SESSION_IDX_PATH, "w") as f:
                f.write(used.get("session_key",""))
    except Exception:
        pass

    resp = {"ok": True, "items": out, "next_max_id": next_token}
    if want_debug:
        resp["debug"] = debug_info
    return jsonify(resp)



@app.route("/api/u/<username>/stories")
@limiter.limit("100 per minute")
def api_profile_stories(username):
    uname = _parse_username_or_url(username)
    if not uname:
        return jsonify({"ok": False, "error": "bad_username"}), 400
    uid = _get_uid(uname)
    if not uid:
        return jsonify({"ok": False, "error": "no_uid"}), 404
    items, _s = _get_stories(uid)
    if not items:
        return jsonify({"ok": True, "items": []})
    out = []
    for it in items:
        out.append({
            "type": it.get("type"),
            "url": it.get("media_url"),
            "thumb": it.get("thumb"),
            "caption": ""
        })
    return jsonify({"ok": True, "items": out})

@app.route("/api/u/<username>/hl_tray")
@limiter.limit("100 per minute")
def api_hl_tray(username):
    """
    Kullanıcının highlight paket listesi (tray):
    [{ id, title, cover }]
    """
    uname = _parse_username_or_url(username)
    if not uname:
        return jsonify({"ok": False, "error": "bad_username"}), 400
    uid = _get_uid(uname)
    if not uid:
        return jsonify({"ok": False, "error": "no_uid"}), 404

    pool = _cookie_pool()
    if not pool:
        return jsonify({"ok": False, "error": "no_session"}), 503

    tray_url = f"https://i.instagram.com/api/v1/highlights/{uid}/highlights_tray/"

    for s in pool:
        tj = _api_json(tray_url, s)
        if not tj:
            continue
        tray = tj.get("tray") or []
        out = []
        for t in tray:
            hid = t.get("id") or t.get("reel_id")
            if not hid:
                continue
            title = (t.get("title") or t.get("name") or "").strip()
            cover = ""
            try:
                cover = (t.get("cover_media", {}).get("cropped_image_version", {}).get("url")
                         or t.get("cover_media", {}).get("image_versions2", {}).get("candidates", [{}])[0].get("url")
                         or "")
            except Exception:
                cover = ""
            out.append({"id": str(hid), "title": title, "cover": cover})
        return jsonify({"ok": True, "items": out})

    return jsonify({"ok": True, "items": []})

@app.route("/api/u/<username>/hl/<hid>")
@limiter.limit("100 per minute")
def api_hl_items(username, hid):
    """
    Bir highlight paketinin içindeki öğeleri döndürür.
    """
    uname = _parse_username_or_url(username)
    if not uname:
        return jsonify({"ok": False, "error": "bad_username"}), 400

    pool = _cookie_pool()
    if not pool:
        return jsonify({"ok": False, "error": "no_session"}), 503

    hid = (hid or "").strip()
    core = hid.split("highlight:", 1)[1] if hid.startswith("highlight:") else hid
    cand_ids = [f"highlight:{core}", core]

    def _req(url, s):
        ck = {
            "sessionid":  s.get("sessionid", ""),
            "ds_user_id": s.get("ds_user_id", ""),
            "csrftoken":  s.get("csrftoken", "")
        }
        h = _build_headers({"X-CSRFToken": ck["csrftoken"]})
        try:
            r = requests.get(url, headers=h, cookies=ck, timeout=10)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return None

    j = None

    for s in pool:
        for cid in cand_ids:
            url = f"https://i.instagram.com/api/v1/feed/reels_media/?reel_ids={cid}"
            j = _req(url, s)
            if j:
                break
        if j:
            break

    if not j:
        for s in pool:
            for cid in cand_ids:
                url = f"https://i.instagram.com/api/v1/feed/reels_tray/?reel_ids={cid}"
                j = _req(url, s)
                if j:
                    break
            if j:
                break

    if not j:
        return jsonify({"ok": True, "items": []})

    def _extract_items(payload: dict):
        if not payload:
            return []
        if isinstance(payload.get("reels_media"), list):
            rms = payload["reels_media"]
            for rm in rms:
                rid = str(rm.get("id") or rm.get("reel_id") or "")
                if rid in (core, f"highlight:{core}"):
                    return rm.get("items", []) or []
            return (rms[0] or {}).get("items", []) or []
        reels = payload.get("reels")
        if isinstance(reels, dict):
            node = reels.get(f"highlight:{core}") or reels.get(core) or next(iter(reels.values()), {})
            return node.get("items", []) or []
        if isinstance(payload.get("items"), list):
            return payload["items"]
        return []

    raw_items = _extract_items(j) or []

    out = []
    for it in raw_items:
        try:
            thumb = (((it.get("image_versions2", {}) or {}).get("candidates") or [{}])[0]).get("url", "")
            if it.get("video_versions"):
                media_url = (it["video_versions"][0] or {}).get("url", "")
                typ = "video"
            else:
                media_url = (((it.get("image_versions2", {}) or {}).get("candidates") or [{}])[0]).get("url", "")
                typ = "image"
            if media_url:
                out.append({"type": typ, "url": media_url, "thumb": thumb, "caption": ""})
        except Exception:
            continue

    return jsonify({"ok": True, "items": out})
# -------------------------- DEBUG: Profil Teşhis --------------------------
@app.route("/__dbg_feed/<username>")
def __dbg_feed(username):
    uname = _parse_username_or_url(username)
    if not uname:
        return jsonify({"ok": False, "err": "bad_username"}), 400
    uid = _get_uid(uname)
    if not uid:
        return jsonify({"ok": False, "err": "no_uid"}), 404

    pool = _cookie_pool()
    if not pool:
        return jsonify({"ok": False, "err": "no_session"}), 503

    rep = []
    for s in pool[:5]:
        row = {"user": s.get("user")}
        u1 = f"https://i.instagram.com/api/v1/feed/user/{uid}/?count=3"
        j1 = _api_json(u1, s)
        row["feed_user_ok"] = bool(j1)
        if j1:
            row["feed_user_status"] = j1.get("status","ok")
            row["feed_user_items"]  = len(j1.get("items") or [])
        else:
            row["feed_user_status"] = "none"

        u2 = f"https://i.instagram.com/api/v1/users/{uid}/feed/?count=3"
        j2 = _api_json(u2, s)
        row["users_feed_ok"] = bool(j2)
        if j2:
            row["users_feed_status"] = j2.get("status","ok")
            row["users_feed_items"]  = len(j2.get("items") or [])
        else:
            row["users_feed_status"] = "none"

        rep.append(row)

    return jsonify({"ok": True, "uid": uid, "tries": rep})

# === Güvenlik başlıkları ===
@app.after_request
def _set_security_headers(resp):
    if os.getenv("ENV","prod").lower() == "prod":
        resp.headers.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains; preload")
    resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    resp.headers.setdefault("Content-Security-Policy",
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://www.googletagmanager.com; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
        "img-src 'self' data: blob: https://*.cdninstagram.com https://*.fbcdn.net https://*.cdninstagram.org https://flagcdn.com https://i.imgur.com https://cdn.jsdelivr.net; "
        "media-src 'self' blob: https://*.cdninstagram.com https://*.fbcdn.net https://*.cdninstagram.org; "
        "font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net data:; "
        "connect-src 'self'; "
        "frame-ancestors 'self'; "
    )
    resp.headers.setdefault("Permissions-Policy",
        "geolocation=(), microphone=(), camera=(), usb=(), payment=()")
    resp.headers.setdefault("Cross-Origin-Resource-Policy", "same-site")
    resp.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    return resp

@app.route("/privacy-policy", defaults={"lang": "en"})
@app.route("/<lang>/privacy-policy")
def privacy(lang="en"):
    meta = get_meta("privacy", lang)
    return render_template("privacy.html", lang=lang, meta=meta)

@app.route("/terms", defaults={"lang": "en"})
@app.route("/<lang>/terms")
def terms(lang="en"):
    meta = get_meta("terms", lang)
    return render_template("terms.html", lang=lang, meta=meta)

@app.route("/contact", defaults={"lang": "en"})
@app.route("/<lang>/contact")
def contact(lang="en"):
    meta = get_meta("contact", lang)
    return render_template("contact.html", lang=lang, meta=meta)

app.register_blueprint(admin_bp, url_prefix='/srdr-proadmin')
app.register_blueprint(blacklist_admin_bp)

@app.route('/robots.txt')
def robots_txt():
    return send_file('robots.txt', mimetype='text/plain')

@app.route('/cookie-policy')
def cookie_policy():
    return render_template('cookie_policy.html')

@app.route("/srdr-proadmin/api/session/ingest", methods=["POST"])
def api_admin_session_ingest():
    """
    Body (JSON):
      {
        "raw": "sessionid=...; ds_user_id=...; csrftoken=...; ...",  # DevTools ham kopya da olur
        "label": "ops-01",           # opsiyonel, gösterim adı
        "status": "active",          # opsiyonel
        "session_key": "15",         # opsiyonel
        "proxy": "http://user:pass@ip:port"  # opsiyonel
      }
    """
    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return jsonify({"ok": False, "error": "bad_json"}), 400

    raw = (data.get("raw") or "").strip()
    if not raw:
        return jsonify({"ok": False, "error": "empty_raw"}), 400

    kv = _parse_cookie_kv(raw)

    sessionid  = kv.get("sessionid", "")
    ds_user_id = kv.get("ds_user_id", "")
    csrftoken  = kv.get("csrftoken", "")

    if not (sessionid and ds_user_id and csrftoken):
        return jsonify({"ok": False, "error": "missing_required", "have": list(kv.keys())}), 400

    label  = (data.get("label") or kv.get("ig_user_id") or kv.get("mid") or "").strip()
    status = (data.get("status") or "active").strip()
    proxy  = (data.get("proxy") or "").strip()

    lst = _load_sessions_list()

    # Upsert
    found = None
    for s in lst:
        if s.get("sessionid") == sessionid or s.get("ds_user_id") == ds_user_id:
            found = s
            break

    # rastgele fingerprint preset
    fp = random.choice(_FINGERPRINT_PRESETS)

    # geniş cookies
    full_cookies = {}
    for k in ("sessionid","ds_user_id","csrftoken","ig_did","rur","mid","datr","dpr","wd"):
        if kv.get(k):
            full_cookies[k] = kv[k]

    if not found:
        sk = (data.get("session_key") or "").strip()
        if not sk:
            sk = _next_session_key(lst)
        newrow = {
            "user": label or "",
            "sessionid": sessionid,
            "ds_user_id": ds_user_id,
            "csrftoken": csrftoken,
            "status": status,
            "session_key": sk,
            "cookies": full_cookies,
            "fingerprint": fp,
        }
        if kv.get("ig_did"): newrow["ig_did"] = kv["ig_did"]
        if kv.get("rur"):    newrow["rur"]    = kv["rur"]
        if kv.get("mid"):    newrow["mid"]    = kv["mid"]

        if proxy:
            newrow["proxy"] = proxy

        lst.append(newrow)
        _save_sessions_list(lst)
        return jsonify({"ok": True, "mode": "insert", "entry": newrow})
    else:
        found["sessionid"]  = sessionid
        found["ds_user_id"] = ds_user_id
        found["csrftoken"]  = csrftoken
        if label:
            found["user"] = label
        if data.get("status"):
            found["status"] = status

        if full_cookies:
            found["cookies"] = full_cookies
        if not found.get("fingerprint"):
            found["fingerprint"] = fp
        if proxy:
            found["proxy"] = proxy

        for extra_k in ("ig_did","rur","mid","ig_nrcb"):
            if kv.get(extra_k):
                found[extra_k] = kv[extra_k]

        _save_sessions_list(lst)
        return jsonify({"ok": True, "mode": "update", "entry": found})

@app.route("/_health/redis")
def _health_redis():
    try:
        return {"ok": bool(app.config["SESSION_REDIS"].ping())}, 200
    except Exception as e:
        return {"ok": False, "err": str(e)}, 500

from flask import session as _sess

@app.route("/_session_test")
def _session_test():
    _sess["hello"] = "world"
    return {"set": "ok"}, 200

@app.route("/_session_get")
def _session_get():
    return {"hello": _sess.get("hello")}, 200

# Rate-limit'i bilerek tetiklemek icin basit bir endpoint:
@app.route("/_limit_test")
@limiter.limit("10 per minute")
def _limit_test():
    return {"ok": True}, 200

if __name__ == "__main__":
    app.run(debug=True)
