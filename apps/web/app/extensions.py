"""Extensiones propias del web (formularios y sesión de navegador).

Las conexiones a PostgreSQL, Redis y MongoDB son las de la biblioteca de
dominio, compartidas con los microservicios.
"""
from flask_login import LoginManager
from flask_wtf import CSRFProtect

from abasto_dominio.extensiones import db  # noqa: F401  (se importa desde aquí en las rutas)

csrf = CSRFProtect()

login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.login_message = 'Inicia sesión para acceder a esta página.'
login_manager.login_message_category = 'warning'
