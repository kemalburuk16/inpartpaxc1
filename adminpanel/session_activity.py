from flask import Blueprint, request, jsonify
import time
import json
from app import _cookie_pool, _find_session_by_key, _save_sessions_list

session_activity_bp = Blueprint('session_activity_bp', __name__)

@session_activity_bp.route("/srdr-proadmin/api/session/<session_key>/activity", methods=["POST"])
def session_activity(session_key):
    """
    Body: {
        "action": "download"|"like"|"follow"|"upload"|"sleep"|"wake"|"proxy_change",
        "params": {...}
    }
    """
    try:
        data = request.get_json(force=True) or {}
        action = data.get("action")
        params = data.get("params", {})

        sess = _find_session_by_key(session_key)
        if not sess:
            return jsonify({"ok": False, "error": "not_found"}), 404

        # Log activity: append to sess['activity_log']
        now = int(time.time())
        act_entry = {
            "timestamp": now,
            "action": action,
            "params": params
        }
        sess.setdefault('activity_log', []).append(act_entry)
        sess['activity_log'] = sess['activity_log'][-100:]

        # Save session list
        lst = _cookie_pool()
        for s in lst:
            if s.get('session_key') == session_key:
                s.update(sess)
        _save_sessions_list(lst)

        # Burada gerçek IG API/Selenium fonksiyonunu çağırabilirsin.

        return jsonify({"ok": True, "result": f"{action} triggered"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
