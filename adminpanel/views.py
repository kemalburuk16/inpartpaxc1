import os
import json
import time
import random
from functools import wraps
from datetime import datetime
import requests

from flask import render_template, request, redirect, url_for, session as login_session, jsonify
from adminpanel import admin_bp
import adminpanel  # admin_bp ve tüm admin route'larını yükler (views, ads_views)
from adminpanel.analytics_data import get_summary_7days, get_realtime_users

# ---------------- Paths & Consts ----------------
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SESSIONS_FILE = os.path.join(BASE_DIR, "sessions.json")
LOG_FILE   = os.path.join(BASE_DIR, "adminpanel/session_updater.log")
NOTIF_FILE = os.path.join(os.path.dirname(__file__), "static/notif_log.json")
BLOCKED_COOKIES_FILE = os.path.join(os.path.dirname(__file__), "../blocked_cookies.json")

NOTIF_LOG = os.path.join(os.path.dirname(__file__), "../data/notif_log.json")
SESSION_USE_LOG = os.path.join(os.path.dirname(__file__), "../data/session_use_log.json")

ADMIN_USERNAME = "srdr"
ADMIN_PASSWORD = "gizlisifre"

# ---------------- Helpers ----------------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not login_session.get("logged_in"):
            return redirect(url_for("admin.login"))
        return f(*args, **kwargs)
    return decorated_function

def load_json(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def get_blocked_sessions():
    """Bloklu sessionid'leri set olarak döner (süresi dolmamış olanlar)."""
    blocked_ids = set()
    now = time.time()
    if os.path.exists(BLOCKED_COOKIES_FILE):
        with open(BLOCKED_COOKIES_FILE, encoding="utf-8") as f:
            try:
                entries = json.load(f)
                # ortak format: [{"sessionid": "...", "blocked_until": 1723512345.0}, ...]
                for entry in entries:
                    if entry.get("blocked_until", 0) > now and entry.get("sessionid"):
                        blocked_ids.add(entry["sessionid"])
            except Exception:
                pass
    return blocked_ids

def generate_unique_session_key(all_sessions):
    """Eşsiz 8 haneli session_key üretir."""
    while True:
        new_key = ''.join(random.choices('0123456789', k=8))
        if not any(str(sess.get("session_key")) == new_key for sess in all_sessions):
            return new_key

# ---------------- Cookie parsers + fingerprint presets ----------------
def _parse_cookie_kv(raw: str) -> dict:
    """'k=v; a=b; ...' tek satır cookie string'ini dict'e çevirir."""
    kv = {}
    for part in (raw or "").split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        k, v = part.split("=", 1)
        kv[k.strip()] = v.strip()
    return kv

def _parse_cookie_table_dump(text: str) -> dict:
    """
    F12 → Application → Cookies tablosundan kopyalanan çok satırlı veriyi ayrıştırır.
    Beklenen satır: <ad>\t<değer>\t<domain>\t<path>...
    """
    kv = {}
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        # Sekmeli tablo
        if "\t" in line:
            parts = line.split("\t")
            if len(parts) >= 2:
                name = parts[0].strip()
                value = parts[1].strip()
                if name:
                    kv[name] = value
        else:
            # Emniyet: "ad boşluk değer" gibi durumlar
            parts = line.split(None, 1)
            if len(parts) == 2 and "=" not in line:
                name = parts[0].strip()
                value = parts[1].strip()
                if name:
                    kv[name] = value
    return kv

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

# ---------------- Auth views ----------------
@admin_bp.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get("username")
        password = request.form.get("password")
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            login_session["logged_in"] = True
            return redirect(url_for("admin.dashboard"))
    return render_template("admin/login.html")

@admin_bp.route('/logout')
def logout():
    login_session.clear()
    return redirect(url_for("admin.login"))

@admin_bp.route('/dashboard')
@login_required
def dashboard():
    return render_template("admin/dashboard.html")

# ---------------- Sessions page ----------------
@admin_bp.route('/sessions')
@login_required
def sessions():
    session_list = load_json(SESSIONS_FILE)
    blocked = get_blocked_sessions()
    # Eksik session_key'leri tamamla + blok bayrağı
    changed = False
    for sess in session_list:
        sess['blocked'] = sess.get('sessionid') in blocked
        if not sess.get('session_key'):
            sess['session_key'] = generate_unique_session_key(session_list)
            changed = True
    if changed:
        save_json(SESSIONS_FILE, session_list)
    return render_template("admin/sessions.html", sessions=session_list)

@admin_bp.route('/get-user-sessions/<username>')
@login_required
def get_user_sessions(username):
    all_sessions = load_json(SESSIONS_FILE)
    user_sessions = [s for s in all_sessions if s.get("user") == username]
    return json.dumps(user_sessions), 200, {'Content-Type': 'application/json'}

@admin_bp.route('/add-user-session/<username>', methods=["POST"])
@login_required
def add_user_session(username):
    # Yeni alanlar: proxy, cookie_dump (çok satır/sekme) veya cookie_raw (tek satır)
    proxy = (request.form.get("proxy") or "").strip()
    cookie_dump = (request.form.get("cookie_dump") or "").strip()
    cookie_raw  = (request.form.get("cookie_raw") or "").strip()

    kv = {}
    if cookie_dump:
        kv = _parse_cookie_table_dump(cookie_dump)
    elif cookie_raw:
        kv = _parse_cookie_kv(cookie_raw)

    sessionid = request.form.get("sessionid") or kv.get("sessionid")
    ds_user_id = request.form.get("ds_user_id") or kv.get("ds_user_id")
    csrftoken = request.form.get("csrftoken") or kv.get("csrftoken")

    if not (sessionid and ds_user_id and csrftoken):
        return "Gerekli alanlar eksik (sessionid, ds_user_id, csrftoken).", 400

    all_sessions = load_json(SESSIONS_FILE)
    # Aynı kullanıcıya aynı sessionid eklenemesin
    for s in all_sessions:
        if s.get("user") == username and s.get("sessionid") == sessionid:
            return "Bu kullanıcıya ait session zaten var.", 400

    # rastgele fingerprint preset
    fp = random.choice(_FINGERPRINT_PRESETS)

    # cookies haritası
    cookies_map = {
        "sessionid": sessionid,
        "ds_user_id": ds_user_id,
        "csrftoken": csrftoken,
    }
    # tablo/tek satırdan gelen ekstra çerezler
    for k, v in (kv or {}).items():
        if k not in cookies_map:
            cookies_map[k] = v

    new_entry = {
        "user": username,
        "sessionid": sessionid,
        "ds_user_id": ds_user_id,
        "csrftoken": csrftoken,
        "fail_count": 0,
        "success_count": 0,
        "last_used": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": "active",
        "session_key": generate_unique_session_key(all_sessions),
        "cookies": cookies_map,
        "fingerprint": fp,
        "proxy": proxy or None,
        "blocked": False,
        "unblock_at": None,
    }

    all_sessions.append(new_entry)
    save_json(SESSIONS_FILE, all_sessions)

    # opsiyonel bildirim listesi
    notif_data = load_json(NOTIF_FILE) if os.path.exists(NOTIF_FILE) else []
    notif_data.append({
        "user": username,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })
    save_json(NOTIF_FILE, notif_data[-50:])  # son 50 kayıt

    return "OK", 200

@admin_bp.route('/session-log')
@login_required
def session_log():
    if not os.path.exists(LOG_FILE):
        return "Log dosyası yok."
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        return f.read()

@admin_bp.route('/delete-log')
@login_required
def delete_log():
    try:
        open(LOG_FILE, "w").close()
    except Exception as e:
        return f"HATA: {str(e)}", 500
    return redirect(url_for("admin.dashboard"))

# ---------------- Live notifications API ----------------
@admin_bp.route("/api/live_notifications")
@login_required
def api_live_notifications():
    notif_data = []
    try:
        if os.path.exists(NOTIF_LOG):
            with open(NOTIF_LOG, encoding="utf-8") as f:
                notif_data = json.load(f)
    except Exception:
        notif_data = []
    last_session = {}
    try:
        if os.path.exists(SESSION_USE_LOG):
            with open(SESSION_USE_LOG, encoding="utf-8") as f:
                session_log = json.load(f)
            last_session = session_log[-1] if session_log else {}
    except Exception:
        last_session = {}
    return jsonify({
        "notifications": notif_data[-20:],  # Son 20 bildirim
        "last_session": last_session
    })

@admin_bp.route('/get-latest-notif')
@login_required
def get_latest_notif():
    notif_path = os.path.join(os.path.dirname(__file__), 'data/notif_log.json')
    if not os.path.exists(notif_path):
        return json.dumps({}), 200, {'Content-Type': 'application/json'}
    with open(notif_path, "r", encoding="utf-8") as f:
        notifs = json.load(f)
    return json.dumps(notifs[-1] if notifs else {}), 200, {'Content-Type': 'application/json'}

@admin_bp.route('/get-last-100-notifs')
@login_required
def get_last_100_notifs():
    notif_path = os.path.join(os.path.dirname(__file__), 'data/notif_log.json')
    if not os.path.exists(notif_path):
        return json.dumps([]), 200, {'Content-Type': 'application/json'}
    with open(notif_path, "r", encoding="utf-8") as f:
        notifs = json.load(f)
    return json.dumps(notifs[-100:]), 200, {'Content-Type': 'application/json'}

# ---------------- Session Test API (tekli & toplu) ----------------
def _merge_cookies(sess: dict) -> dict:
    """
    sessions.json satırındaki cookies'i üst seviye alanlarla birleştirir.
    """
    ck = dict(sess.get("cookies") or {})
    for k in ("sessionid", "ds_user_id", "csrftoken"):
        if not ck.get(k) and sess.get(k):
            ck[k] = sess.get(k)
    return ck

def _test_cookie_entry(sess: dict) -> dict:
    """
    Verilen session objesini Instagram 'current_user' ile test eder.
    Döner: { ok, status: active|blocked|invalid, http, error?, who? , session_key, user }
    """
    sk = str(sess.get("session_key", ""))
    user = sess.get("user", "")
    ck = _merge_cookies(sess)

    if not (ck.get("sessionid") and ck.get("ds_user_id") and ck.get("csrftoken")):
        return {"ok": False, "status": "invalid", "http": 0, "error": "missing_cookies",
                "session_key": sk, "user": user}

    headers = {
        "User-Agent": "Instagram 298.0.0.0.0 Android",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9,tr;q=0.8",
        "X-IG-App-ID": "1217981644879628",
        "X-CSRFToken": ck.get("csrftoken", ""),
        "Referer": "https://www.instagram.com/",
    }

    proxies = {}
    proxy = (sess.get("proxy") or "").strip()
    if proxy:
        proxies = {"http": proxy, "https": proxy}

    url = "https://i.instagram.com/api/v1/accounts/current_user/"
    try:
        r = requests.get(url, headers=headers, cookies=ck, timeout=12,
                         proxies=proxies, allow_redirects=False)
        code = r.status_code
    except Exception as e:
        return {"ok": False, "status": "invalid", "http": -1, "error": f"request_error:{str(e)[:120]}",
                "session_key": sk, "user": user}

    # 200 → JSON bekleniyor; HTML/boş dönerse non_json_200
    if code == 200:
        try:
            j = r.json()
            if j.get("user") or j.get("status") == "ok":
                who = (j.get("user") or {}).get("username")
                return {"ok": True, "status": "active", "http": code, "who": who,
                        "session_key": sk, "user": user}
            return {"ok": False, "status": "invalid", "http": code, "error": "json_missing_user",
                    "session_key": sk, "user": user}
        except Exception:
            return {"ok": False, "status": "invalid", "http": code, "error": "non_json_200",
                    "session_key": sk, "user": user}

    if code in (401, 403):
        return {"ok": False, "status": "invalid", "http": code, "error": "unauthorized",
                "session_key": sk, "user": user}

    if code in (429, 418):
        return {"ok": False, "status": "blocked", "http": code, "error": "rate_limited",
                "session_key": sk, "user": user}

    if code in (301, 302, 303, 307, 308):
        loc = r.headers.get("Location", "")
        return {"ok": False, "status": "invalid", "http": code, "error": f"redirect:{loc}",
                "session_key": sk, "user": user}

    return {"ok": False, "status": "invalid", "http": code, "error": "unknown",
            "session_key": sk, "user": user}

@admin_bp.route('/api/session/test/<session_key>')
@login_required
def api_session_test(session_key):
    """
    Tek bir session'ı test eder (TEK route).
    """
    all_sessions = load_json(SESSIONS_FILE)
    target = next((s for s in all_sessions if str(s.get("session_key")) == str(session_key)), None)
    if not target:
        return jsonify({"ok": False, "error": "not_found"}), 404

    res = _test_cookie_entry(target)

    # Görsel kolaylık için status alanını basitçe güncelle
    target["status"] = "active" if res.get("status") == "active" else "invalid"
    save_json(SESSIONS_FILE, all_sessions)

    return jsonify(res), 200

@admin_bp.route('/api/session/test_all')
@login_required
def api_session_test_all():
    """
    Tüm session'ları sırayla test eder, özet döner.
    """
    all_sessions = load_json(SESSIONS_FILE)
    summary = {"active": 0, "blocked": 0, "invalid": 0, "total": len(all_sessions)}
    results = []

    for s in all_sessions:
        res = _test_cookie_entry(s)
        results.append(res)
        st = res.get("status")
        if st in summary:
            summary[st] += 1
        s["status"] = "active" if st == "active" else "invalid"

    save_json(SESSIONS_FILE, all_sessions)
    return jsonify({"ok": True, "summary": summary, "results": results}), 200

# ---------------- Update/Delete session ----------------
@admin_bp.route('/update-user-session/<username>/<session_key>', methods=["POST"])
@login_required
def update_user_session(username, session_key):
    all_sessions = load_json(SESSIONS_FILE)

    proxy = (request.form.get("proxy") or "").strip()
    cookie_dump = (request.form.get("cookie_dump") or "").strip()
    cookie_raw  = (request.form.get("cookie_raw") or "").strip()

    kv = {}
    if cookie_dump:
        kv = _parse_cookie_table_dump(cookie_dump)
    elif cookie_raw:
        kv = _parse_cookie_kv(cookie_raw)

    for sess in all_sessions:
        if sess.get("user") == username and str(sess.get("session_key")) == str(session_key):
            # alanları ya formdan ya cookie’lerden çek
            sessionid  = request.form.get('sessionid')  or kv.get("sessionid")  or sess.get("sessionid")
            ds_user_id = request.form.get('ds_user_id') or kv.get("ds_user_id") or sess.get("ds_user_id")
            csrftoken  = request.form.get('csrftoken')  or kv.get("csrftoken")  or sess.get("csrftoken")

            if not (sessionid and ds_user_id and csrftoken):
                return "Gerekli alanlar eksik.", 400

            sess['sessionid']  = sessionid
            sess['ds_user_id'] = ds_user_id
            sess['csrftoken']  = csrftoken

            # cookies birleştir
            cookies = dict(sess.get("cookies") or {})
            if kv:
                cookies.update(kv)
            cookies["sessionid"]  = sessionid
            cookies["ds_user_id"] = ds_user_id
            cookies["csrftoken"]  = csrftoken
            sess["cookies"] = cookies

            # fingerprint yoksa ata
            if not sess.get("fingerprint"):
                sess["fingerprint"] = random.choice(_FINGERPRINT_PRESETS)

            # proxy güncelle (geldiyse)
            if proxy:
                sess["proxy"] = proxy

            save_json(SESSIONS_FILE, all_sessions)
            return "OK", 200

    return "Hatalı index", 400

@admin_bp.route('/delete-session/<session_key>', methods=["POST"])
@login_required
def delete_session(session_key):
    all_sessions = load_json(SESSIONS_FILE)
    new_sessions = [sess for sess in all_sessions if str(sess.get("session_key")) != str(session_key)]
    if len(all_sessions) == len(new_sessions):
        return "Bulunamadı", 404
    save_json(SESSIONS_FILE, new_sessions)
    return "OK", 200

# ---------------- Analytics ----------------
@admin_bp.route('/analytics')
@login_required
def analytics():
    return render_template("admin/analytics.html")

@admin_bp.route('/api/analytics/summary')
@login_required
def api_analytics_summary():
    return jsonify(get_summary_7days())

@admin_bp.route('/api/analytics/realtime')
@login_required
def api_analytics_realtime():
    return jsonify({"active_users": get_realtime_users()})
