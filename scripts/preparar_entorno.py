"""
Prepara el entorno local antes del primer «docker compose up».

    python scripts/preparar_entorno.py

- Crea .env a partir de .env.example si no existe (configuración sin secretos).
- Genera en secrets/ un archivo por secreto con un valor aleatorio de 256 bits.
  Docker los monta en /run/secrets/<nombre> sólo en los contenedores que los
  necesitan; nunca se suben al repositorio (secrets/ está en .gitignore).

Un secreto que ya existe no se cambia: las bases de datos se inicializan con
él la primera vez. Para empezar de cero: docker compose down -v, borra
secrets/ y vuelve a correr este script.
"""
import secrets
import shutil
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SECRETOS = (
    'secret_key',          # firma de la sesión de Flask (web)
    'jwt_secret_key',      # firma de los JWT (web y microservicios)
    'postgres_password',   # superusuario de PostgreSQL (sólo inicialización y migraciones)
    'mongo_password',      # usuario raíz de MongoDB
    'redis_password',      # contraseña de Redis
)


def main():
    env = RAIZ / '.env'
    if not env.exists():
        shutil.copy(RAIZ / '.env.example', env)
        print('Creado .env a partir de .env.example')
    else:
        print('.env ya existe (no se modifica)')

    carpeta = RAIZ / 'secrets'
    carpeta.mkdir(exist_ok=True)
    nuevos = 0
    for nombre in SECRETOS:
        archivo = carpeta / f'{nombre}.txt'
        # Si se corrió «docker compose up» antes que este script, Docker crea carpetas vacías con
        # el nombre de cada secreto; se quitan para poder escribir el archivo.
        if archivo.is_dir() and not any(archivo.iterdir()):
            archivo.rmdir()
        if archivo.is_file() and archivo.read_text(encoding='utf-8').strip():
            continue
        archivo.write_text(secrets.token_urlsafe(32), encoding='utf-8')
        nuevos += 1
    print(f'secrets/: {nuevos} secretos nuevos, {len(SECRETOS) - nuevos} ya existían')
    if nuevos and nuevos < len(SECRETOS):
        print('Aviso: si cambiaste la contraseña de una base de datos ya inicializada, corre '
              '«docker compose down -v» para que se vuelva a crear con la nueva.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
