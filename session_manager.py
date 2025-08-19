import json
import os
import time
from datetime import datetime

SESSIONS_FILE = "sessions.json"
BLOCKED_FILE = "blocked_cookies.json"

def load_json(path):
    if not os.path.exists(path):
        return []
    with open(path, "r") as f:
        return json.load(f)

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def normalize_session(entry):
    # Anahtar uyumsuzluklarını normalize et
    if "username" in entry:
        entry["user"] = entry["username"]
        del entry["username"]
    if "country" in entry:
        del entry["country"]
    # default alanlar
    entry.setdefault("fail_count", 0)
    entry.setdefault("success_count", 0)
    entry.setdefault("last_used", None)
    entry.setdefault("status", "active")

def _blocked_set_with_expiry() -> set:
    """
    blocked_cookies.json ortak format:
      [{"sessionid":"...", "blocked_until": 1723512345.12}, ...]
    Sadece süresi HENÜZ dolmamış olanları set olarak döndür.
    """
    now = time.time()
    out = set()
    try:
        data = load_json(BLOCKED_FILE)
        if isinstance(data, list):
            for row in data:
                sid = (row or {}).get("sessionid")
                bu  = float((row or {}).get("blocked_until", 0))
                if sid and bu > now:
                    out.add(sid)
    except Exception:
        pass
    return out

def detect_status(entry, active_blocked_sids: set):
    sid = entry.get("sessionid", "")
    # aktif blok → invalid
    if sid in active_blocked_sids:
        return "invalid"
    # blok yok ama ardışık hatalar → pending/invalid kademesi
    fc = int(entry.get("fail_count", 0))
    if fc >= 3:
        return "invalid"
    if fc > 0:
        return "pending"
    return "active"

def update_sessions():
    sessions = load_json(SESSIONS_FILE)
    active_blocked = _blocked_set_with_expiry()

    for s in sessions:
        normalize_session(s)
        s["status"] = detect_status(s, active_blocked)

    save_json(SESSIONS_FILE, sessions)
    print(f"✔ Güncellendi: {len(sessions)} session")

if __name__ == "__main__":
    update_sessions()
