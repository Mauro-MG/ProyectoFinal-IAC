"""
Prepara las sesiones de los usuarios virtuales de Locust. Se corre DENTRO del contenedor de ms-seguridad:

    docker exec -i ms-seguridad python - < tests/carga/emitir_sesiones.py > tests/carga/resultados/sesiones.json

Usa el mismo código que el login (sesiones.emitir_tokens): cada token tiene su sesión en Redis y se puede
revocar. No se pasa por POST /auth/login porque ese endpoint limita a 10 intentos por minuto y por IP
(protección contra fuerza bruta), y todos los usuarios virtuales salen de la misma IP. El login se mide
aparte, en el escenario «Autenticacion», respetando ese límite.
Solo toma cuentas de los datos masivos (*@masivo.abastored.test).
"""
import json
import sys

sys.path.insert(0, '/srv')
from app import app  # noqa: E402

from abasto_dominio import sesiones  # noqa: E402
from abasto_dominio.modelos.usuario import Usuario  # noqa: E402

with app.app_context():
    def emitir(usuarios, origen):
        return [{'email': u.email, 'token': sesiones.emitir_tokens(u, origen=origen, con_refresh=False)['access_token']}
                for u in usuarios]

    masivos = (Usuario.query.filter(Usuario.email.like('comercio%@masivo.abastored.test'), Usuario.activo)
               .order_by(Usuario.email).limit(300).all())
    def de(patron):
        return Usuario.query.filter(Usuario.email.like(patron), Usuario.activo).order_by(Usuario.email).all()

    print(json.dumps({
        'comerciantes': emitir(masivos, 'movil'),
        'analistas': emitir(de('analista%@masivo.abastored.test') + de('coordinador%@masivo.abastored.test'),
                            'escritorio'),
        'auditores': emitir(de('auditor%@masivo.abastored.test'), 'web'),
    }))
