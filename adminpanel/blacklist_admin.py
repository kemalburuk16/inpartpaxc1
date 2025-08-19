# -*- coding: utf-8 -*-
# /var/www/instavido/adminpanel/blacklist_admin.py

import os, json, re, time, traceback
from flask import Blueprint, render_template, request, jsonify, current_app, session as flask_session

# ŞABLON YOLU:
# Bu blueprint __name__ = "adminpanel.blacklist_admin" altında çalışır.
# template_folder="templates" => /var/www/instavido/adminpanel/templates
# Biz de admin/blacklist.html çağıracağız: adminpanel/templates/admin/blacklist.html
blacklist_admin_bp = Blueprint(
    "blacklist_admin",
    __name__,
    url_prefix="/srdr-proadmin/blacklist",
    template_folder="templates"
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
BLACKLIST_FILE = os.path.join(DATA_DIR, "blacklist.json")

def _ensure_store():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(BLACKLIST_FILE):
        with open(BLACKLIST_FILE, "w", encoding="utf-8") as f:
            json.dump({"profiles": [], "links": []}, f, ensure_ascii=False, indent=2)

def _load():
    _ensure_store()
    try:
        with open(BLACKLIST_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        # dosya bozulduysa kurtar
        try:
            return {"profiles": [], "links": []}
        finally:
            with open(BLACKLIST_FILE, "w", encoding="utf-8") as f:
                json.dump({"profiles": [], "links": []}, f, ensure_ascii=False, indent=2)

def _save(payload: dict):
    payload = payload or {"profiles": [], "links": []}
    payload.setdefault("profiles", [])
    payload.setdefault("links", [])
    with open(BLACKLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())

def _is_admin_logged_in() -> bool:
    # Admin panelinde giriş flag’i adminpanel/views.py’de "logged_in" olarak tutuluyor
    return bool(flask_session.get("logged_in"))

# ---- Basit login kontrol decorator’u ----
def admin_required(fn):
    from functools import wraps
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not _is_admin_logged_in():
            # admin login’e yönlendir
            from flask import redirect, url_for
            try:
                return redirect(url_for("admin.login"))
            except Exception:
                # URL build sorunu olursa fallback
                return redirect("/srdr-proadmin/")
        return fn(*args, **kwargs)
    return wrapper

# ------------------- TEŞHİS / SAĞLIK -------------------

@blacklist_admin_bp.route("/health")
def health():
    """
    500 olduğunda önce bunu deneyin:
    https://.../srdr-proadmin/blacklist/health
    """
    try:
        info = {
            "base_dir": BASE_DIR,
            "data_dir_exists": os.path.isdir(DATA_DIR),
            "file_exists": os.path.isfile(BLACKLIST_FILE),
            "logged_in": _is_admin_logged_in(),
        }
        # dosyayı da okumayı deneyelim
        data = _load()
        info["profiles_count"] = len(data.get("profiles", []))
        info["links_count"] = len(data.get("links", []))
        return jsonify({"ok": True, "info": info})
    except Exception as e:
        return jsonify({"ok": False, "err": str(e), "trace": traceback.format_exc()}), 500

# ------------------- SAYFA -------------------

@blacklist_admin_bp.route("/", methods=["GET"])
@admin_required
def page():
    try:
        data = _load()
        profiles = data.get("profiles", [])
        links = data.get("links", [])
        # Not: template yolu -> adminpanel/templates/admin/blacklist.html
        return render_template("admin/blacklist.html", profiles=profiles, links=links)
    except Exception as e:
        # 500 olduğunda sebebi log’a yaz
        current_app.logger.exception("Blacklist page render error")
        return f"Blacklist render error: {e}", 500

# ------------------- API: EKLE/SİL -------------------

@blacklist_admin_bp.route("/add", methods=["POST"])
@admin_required
def add():
    try:
        j = request.get_json(silent=True) or {}
        mode  = (j.get("mode") or "").strip()
        value = (j.get("value") or "").strip()

        if not mode or not value:
            return jsonify({"ok": False, "msg": "Eksik parametre"}), 400

        payload = _load()
        if mode == "profile":
            v = _norm(value)
            if v.startswith("@"): v = v[1:]
            if not v:
                return jsonify({"ok": False, "msg": "Geçersiz kullanıcı adı"}), 400
            if v not in [ _norm(x) for x in payload.get("profiles", []) ]:
                payload["profiles"].append(v)
            _save(payload)
            return jsonify({"ok": True, "added": v})

        elif mode == "link":
            # Tam URL bekliyoruz
            if not value.lower().startswith("http"):
                return jsonify({"ok": False, "msg": "Tam URL girin"}), 400
            v = value.strip()
            if v not in payload.get("links", []):
                payload["links"].append(v)
            _save(payload)
            return jsonify({"ok": True, "added": v})

        else:
            return jsonify({"ok": False, "msg": "Geçersiz mod"}), 400
    except Exception as e:
        current_app.logger.exception("Blacklist add error")
        return jsonify({"ok": False, "msg": str(e)}), 500

@blacklist_admin_bp.route("/delete", methods=["POST"])
@admin_required
def delete():
    try:
        j = request.get_json(silent=True) or {}
        mode  = (j.get("mode") or "").strip()
        value = (j.get("value") or "").strip()
        if not mode or not value:
            return jsonify({"ok": False, "msg": "Eksik parametre"}), 400

        payload = _load()
        if mode == "profile":
            v = _norm(value)
            if v.startswith("@"): v = v[1:]
            payload["profiles"] = [x for x in payload.get("profiles", []) if _norm(x) != v]
            _save(payload)
            return jsonify({"ok": True})

        elif mode == "link":
            v = value.strip()
            payload["links"] = [x for x in payload.get("links", []) if x != v]
            _save(payload)
            return jsonify({"ok": True})

        else:
            return jsonify({"ok": False, "msg": "Geçersiz mod"}), 400
    except Exception as e:
        current_app.logger.exception("Blacklist delete error")
        return jsonify({"ok": False, "msg": str(e)}), 500

# ------------------- KULLANICIYA GÖRÜNECEK BLOK MESAJI -------------------
# Bunu kullanıcıya gösteriyorsun: templates/policies/blocked.html kullanılıyor.
# app.py içindeki _is_blocked() ile uyumlu.
