from apscheduler.schedulers.background import BackgroundScheduler
import time
from app import _cookie_pool, _save_sessions_list

def session_auto_activity():
    pool = _cookie_pool()
    for sess in pool:
        # Örnek: her aktif session'a rastgele aktivite uygula
        pass

scheduler = BackgroundScheduler()
scheduler.add_job(session_auto_activity, 'interval', minutes=15)
scheduler.start()