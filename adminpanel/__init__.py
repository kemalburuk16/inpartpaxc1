# /var/www/instavido/adminpanel/__init__.py
from flask import Blueprint

# Admin blueprint'i tek yerde tanımla
admin_bp = Blueprint(
    "admin",
    __name__,
    template_folder="templates",
    static_folder="static"
)

# Route'ları kaydetmek için en sonda import et
# (Bu importlar admin_bp tanımını KULLANIR, tekrar blueprint tanımlamaz)
from . import views  # noqa: E402,F401
from . import ads_views  # noqa: E402,F401
