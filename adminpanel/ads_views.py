# -*- coding: utf-8 -*-
# /var/www/instavido/adminpanel/ads_views.py
import os
import json
from flask import Blueprint, render_template, request, jsonify, Response
from adminpanel import admin_bp   # mevcut admin blueprint
from functools import wraps

from ads_manager import (
    load_config, save_config,
    set_slot, toggle_slot, get_slot,
    set_interstitial
)

# --- Basit login kontrolü: adminpanel/views.py'deki login_required ile aynı davranış ---
from flask import session as login_session, redirect, url_for

def login_required(f):
    @wraps(f)
    def _d(*args, **kwargs):
        if not login_session.get("logged_in"):
            return redirect(url_for("admin.login"))
        return f(*args, **kwargs)
    return _d

# ---------------------------
# SAYFA: Reklam Yönetimi
# ---------------------------
@admin_bp.route("/ads", methods=["GET"])
@login_required
def ads_page():
    cfg = load_config()  # ads_manager’daki JSON
    slots = cfg.get("slots", {})
    inter = cfg.get("interstitial", {"enabled": False, "min_after_first": 2, "max_after_first": 5, "cooldown_minutes": 30})
    # Şablona sade dict gönderelim
    view_slots = []
    for key in sorted(slots.keys()):
        s = slots[key] or {}
        view_slots.append({
            "key": key,
            "label": s.get("label") or key,
            "enabled": bool(s.get("active") or s.get("enabled")),  # her iki anahtar da destekli
            "code": s.get("html") or s.get("code") or ""
        })
    return render_template("admin/ads.html", slots=view_slots, inter=inter)

# ---------------------------
# API: Tek slot HTML’i getir (makro için)
# ---------------------------
@admin_bp.route("/ads/api/slot/<slot>.html", methods=["GET"])
def api_slot_html(slot):
    """templates/ads/macros.html makrosu buradan HTML çeker.
       Slot pasifse 204 döndürür."""
    s = get_slot(slot)
    if not s:
        return Response("", status=204)
    enabled = bool(s.get("active") or s.get("enabled"))
    html = s.get("html") or s.get("code") or ""
    if not enabled or not html.strip():
        return Response("", status=204)
    # HTML olarak döndür
    return Response(html, mimetype="text/html; charset=utf-8")

# ---------------------------
# KAYDET: Tek/çoklu form kaydı
# ---------------------------
@admin_bp.route("/ads/save", methods=["POST"])
@login_required
def ads_save():
    """
    Form verisi:
      slots[<key>][enabled] = "on" (opsiyon)
      slots[<key>][label]   = "..."
      slots[<key>][code]    = "..."
    Tek slot butonundan da, 'Tümünü kaydet'ten de çalışır.
    """
    # Form’u parse et
    # slots[header_top][code] gibi anahtarlar gelir
    data = request.form
    # Tüm anahtarları dolaşalım
    # slot isimlerini topla
    keys = set()
    for k in data.keys():
        if k.startswith("slots[") and "][" in k and k.endswith("]"):
            # slots[header_top][code] -> header_top
            inside = k[len("slots["):-1]
            slot_key = inside.split("][", 1)[0]
            keys.add(slot_key)

    for key in keys:
        enabled = data.get(f"slots[{key}][enabled]", "")
        label   = data.get(f"slots[{key}][label]", "").strip() or None
        code    = data.get(f"slots[{key}][code]", "")
        set_slot(key, html=code, active=(enabled == "on"), label=label)

    return ("OK", 200)

# ---------------------------
# TOGGLE: listeden aktif/pasif
# ---------------------------
@admin_bp.route("/ads/toggle/<key>", methods=["POST"])
@login_required
def ads_toggle(key):
    try:
        payload = request.get_json(force=True, silent=True) or {}
        enabled = bool(payload.get("enabled"))
        toggle_slot(key, enabled)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 400

# ---------------------------
# YENİ SLOT EKLE
# ---------------------------
@admin_bp.route("/ads/add", methods=["POST"])
@login_required
def ads_add():
    payload = request.get_json(force=True, silent=True) or {}
    key   = (payload.get("key") or "").strip()
    label = (payload.get("label") or key).strip()
    code  = payload.get("code") or ""
    enabled = bool(payload.get("enabled"))

    if not key or any(ch in key for ch in " /\\?&%#@"):
        return jsonify({"ok": False, "msg": "Geçerli bir anahtar girin (harf/rakam/altçizgi)."}), 400

    # Var olanı ezmeden set_slot zaten güvenli davranır (create/update)
    set_slot(key, html=code, active=enabled, label=label)
    return jsonify({"ok": True})

# ---------------------------
# SLOT SİL
# ---------------------------
@admin_bp.route("/ads/delete/<key>", methods=["POST"])
@login_required
def ads_delete(key):
    cfg = load_config()
    slots = cfg.get("slots", {})
    if key in slots:
        del slots[key]
        save_config(cfg)
        return ("OK", 200)
    return ("Not Found", 404)

# ---------------------------
# INTERSTITIAL KAYDET
# ---------------------------
@admin_bp.route("/ads/interstitial/save", methods=["POST"])
@login_required
def ads_interstitial_save():
    enabled = request.form.get("enabled") == "on"
    min_after = int(request.form.get("min_after_first") or 2)
    max_after = int(request.form.get("max_after_first") or 5)
    cooldown  = int(request.form.get("cooldown_minutes") or 30)
    set_interstitial(enabled, min_after, max_after, cooldown)
    return ("OK", 200)
