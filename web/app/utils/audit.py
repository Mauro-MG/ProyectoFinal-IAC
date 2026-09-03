from flask import request
from app.extensions import db
from app.models.auditoria import AuditoriaEvento
from flask_login import current_user

def registrar_evento(usuario_id, tipo_evento, entidad, entidad_id, descripcion, datos_anteriores=None, datos_nuevos=None):
    ip_address = request.remote_addr if request else None
    user_agent = request.user_agent.string if request else None
    
    evento = AuditoriaEvento(
        usuario_id=usuario_id,
        tipo_evento=tipo_evento,
        entidad=entidad,
        entidad_id=str(entidad_id) if entidad_id else None,
        descripcion=descripcion,
        datos_anteriores=datos_anteriores,
        datos_nuevos=datos_nuevos,
        ip_address=ip_address,
        user_agent=user_agent
    )
    db.session.add(evento)
    db.session.commit()
