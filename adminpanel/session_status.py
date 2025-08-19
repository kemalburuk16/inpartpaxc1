from flask import Blueprint, jsonify
from app import _cookie_pool, _find_session_by_key

session_status_bp = Blueprint('session_status_bp', __name__)

@session_status_bp.route("/srdr-proadmin/api/session/<session_key>/status", methods=["GET"])
def session_status(session_key):
    sess = _find_session_by_key(session_key)
    if not sess:
        return jsonify({"ok": False, "error": "not_found"}), 404

    status = {
        "user": sess.get("user"),
        "status": sess.get("status"),
        "proxy": sess.get("proxy"),
        "fingerprint": sess.get("fingerprint"),
        "last_activity": sess.get("activity_log", [])[-1] if sess.get("activity_log") else None,
        "ban_risk": sess.get("soft_fail_count", 0) > 3,
        "cooldown": sess.get("cooldown_until", 0),
        "online": True
    }
    return jsonify({"ok": True, "status": status})

@session_status_bp.route("/srdr-proadmin/api/session/<session_key>/logs", methods=["GET"])
def session_logs(session_key):
    sess = _find_session_by_key(session_key)
    if not sess:
        return jsonify({"ok": False, "error": "not_found"}), 404
    logs = sess.get("activity_log", [])
    return jsonify({"ok": True, "logs": logs[-24:]})
