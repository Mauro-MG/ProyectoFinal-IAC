"""
Cuentas exclusivas de una corrida de carga contra el despliegue (se ejecuta DENTRO de ms-seguridad en la VM):

    docker exec -i -e PREFIJO=gcp20261126a -e COMERCIANTES=90 -e ANALISTAS=30 -e AUDITORES=15 \
        ms-seguridad python - < preparar_cuentas_vm.py > sesiones.json

- Correos  <prefijo>-com001@carga.abastored.test, <prefijo>-ana001@..., <prefijo>-aud001@...
- La contraseña es aleatoria y no se guarda: nadie puede iniciar sesión con estas cuentas.
- Los tokens se emiten con el mismo código del login (sesiones.emitir_tokens): cada uno tiene su sesión en
  Redis, pasa por la misma validación que un token normal y se puede revocar. No se usa POST /auth/login
  porque ese endpoint limita a 10 intentos por minuto y por IP, y todos los usuarios virtuales salen de una
  sola IP. El login queda fuera de la medición.
- Con LIMPIAR=1 revoca las sesiones de las cuentas del prefijo y las desactiva (no borra datos).
La salida (stdout) contiene tokens: no se publica ni se versiona.
"""
import json
import os
import re
import secrets
import sys

sys.path.insert(0, '/srv')
from app import app  # noqa: E402

import bcrypt  # noqa: E402

from abasto_dominio import sesiones  # noqa: E402
from abasto_dominio.extensiones import db  # noqa: E402
from abasto_dominio.modelos.rol import Rol  # noqa: E402
from abasto_dominio.modelos.usuario import Usuario  # noqa: E402

PREFIJO = os.environ['PREFIJO']
if not re.fullmatch(r'[a-z0-9]{6,24}', PREFIJO):
    sys.exit('PREFIJO: de 6 a 24 letras minúsculas o dígitos')
DOMINIO = 'carga.abastored.test'
PERFILES = (('com', 'Comerciante Informal', 'movil', int(os.environ.get('COMERCIANTES', 90))),
            ('ana', 'Analista de Mercado', 'escritorio', int(os.environ.get('ANALISTAS', 30))),
            ('aud', 'Auditor', 'web', int(os.environ.get('AUDITORES', 15))))

with app.app_context():
    cuentas = Usuario.query.filter(Usuario.email.like(f'{PREFIJO}-%@{DOMINIO}'))
    if os.environ.get('LIMPIAR') == '1':
        n = 0
        for u in cuentas.all():
            sesiones.revocar_todas(u.id)
            u.activo = False
            n += 1
        db.session.commit()
        print(json.dumps({'prefijo': PREFIJO, 'desactivadas': n}))
        sys.exit(0)
    if cuentas.count():
        sys.exit(f'Ya existen cuentas con el prefijo {PREFIJO}: usa un prefijo nuevo por corrida')

    salida = {'prefijo': PREFIJO}
    hash_inutil = bcrypt.hashpw(secrets.token_urlsafe(24).encode(), bcrypt.gensalt(rounds=10)).decode()
    for corto, patron_rol, origen, n in PERFILES:
        rol = Rol.query.filter(Rol.nombre.like(f'{patron_rol}%')).one()
        usuarios = []
        for i in range(1, n + 1):
            u = Usuario(email=f'{PREFIJO}-{corto}{i:03d}@{DOMINIO}', password_hash=hash_inutil, nombre='Carga',
                        apellido_paterno=f'{corto.upper()} {i:03d}', apellido_materno=PREFIJO, rol_id=rol.id,
                        activo=True, email_verificado=True)
            db.session.add(u)
            usuarios.append(u)
        db.session.commit()
        salida[corto] = [{'email': u.email, 'id': str(u.id),
                          'token': sesiones.emitir_tokens(u, origen=origen, con_refresh=False)['access_token']}
                         for u in usuarios]
    print(json.dumps(salida))
