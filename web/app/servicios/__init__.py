"""
Lógica de negocio independiente de Flask.

Las funciones de este paquete reciben modelos y datos ya validados y dejan los
cambios en la sesión de SQLAlchemy; la vista que las llama decide cuándo hacer
commit. Así una operación y su registro de auditoría se guardan juntos.
"""


class ReglaNegocioError(Exception):
    """Operación rechazada por una regla de negocio (el mensaje se muestra al usuario)."""
