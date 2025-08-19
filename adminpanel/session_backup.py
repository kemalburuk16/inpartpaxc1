import shutil
import time
from app import SESSIONS_PATH

def backup_sessions():
    ts = time.strftime("%Y%m%d_%H%M%S")
    backup_path = f"sessions_backup_{ts}.json"
    shutil.copyfile(SESSIONS_PATH, backup_path)
    return backup_path
