from .session_activity import session_activity_bp
from .session_status import session_status_bp
# Scheduler ve backup modülleri doğrudan import edilir

def register_blueprints(app):
    app.register_blueprint(session_activity_bp)
    app.register_blueprint(session_status_bp)