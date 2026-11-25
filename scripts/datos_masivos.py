"""
Datos masivos coherentes con el dominio, con semilla reproducible, para medir volumen y rendimiento.

    python scripts/datos_masivos.py generar [--semilla 2026] [--escala 1.0]
    python scripts/datos_masivos.py contar
    python scripts/datos_masivos.py limpiar

Solo para el entorno LOCAL de pruebas (Docker en este equipo): carga directo en las bases con COPY y
mongoimport a través de `docker exec`, como administrador. No usa las APIs, porque cargar un millón de
filas por HTTP mediría el cliente y no la base. Todo lo generado queda marcado para poder borrarlo:
  - usuarios con correo *@masivo.abastored.test (contraseña común: Masivo2026!);
  - comercios y proveedores con nombre «MASIVO ...»;
  - documentos de MongoDB con el campo masivo: true.
Las tablas dependientes (inventario, precios, movimientos, ventas, pedidos) cuelgan de esos comercios.

Con --escala 1.0 (por omisión) se generan aproximadamente:
  4 000 comerciantes con su comercio, 120 proveedores, ~66 000 renglones de inventario, ~200 000 precios
  históricos, ~260 000 movimientos, 120 000 ventas (~240 000 partidas), 15 000 pedidos (~45 000 partidas),
  300 000 peticiones en la bitácora y 50 000 búsquedas en MongoDB.
"""
import argparse
import csv
import io
import json
import math
import random
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt

PG = ['docker', 'exec', '-i', 'abastored-postgres', 'psql', '-v', 'ON_ERROR_STOP=1', '-U', 'abastored_admin',
      '-d', 'abastored', '-q']
MONGO = ['docker', 'exec', '-i', 'abastored-mongo', 'sh', '-c']
MONGO_AUTH = '-u "$MONGO_INITDB_ROOT_USERNAME" -p "$(cat /run/secrets/mongo_password)" --authenticationDatabase admin'
DOMINIO = 'masivo.abastored.test'
CLAVE = 'Masivo2026!'

# Precio base por producto (promedio observado en los datos semilla); el precio de cada comercio varía alrededor
PRECIOS_BASE = {
    'Tortilla de maíz': 23.5, 'Café soluble 120 g': 76.2, 'Sardina en tomate 425 g': 37.5, 'Atún en agua 140 g': 22.6,
    'Pasta para sopa 200 g': 11.4, 'Harina de maíz 1 kg': 24.5, 'Sal de mesa 1 kg': 14.5,
    'Azúcar estándar 1 kg': 33.7, 'Aceite vegetal 1 L': 44.3, 'Frijol pinto 1 kg': 39.2, 'Arroz blanco 1 kg': 31.2,
    'Manzana golden': 47.5, 'Plátano tabasco': 23.4, 'Limón con semilla': 37.4, 'Chile jalapeño': 33.6,
    'Papa blanca': 28.9, 'Cebolla blanca': 23.6, 'Tomate saladette': 25.6, 'Queso fresco': 146.7,
    'Leche entera 1 L': 28.7, 'Carne molida de res': 170.1, 'Pollo entero': 70.0, 'Huevo blanco 12 pzas': 49.1,
    'Agua purificada 1.5 L': 15.5, 'Coca-Cola 600 ml': 19.3, 'Jabón de lavandería 400 g': 22.8,
    'Detergente en polvo 1 kg': 45.5, 'Papel higiénico 4 rollos': 33.4,
}
TIPOS_INFORMALES = ['INFORMAL_TIANGUIS', 'INFORMAL_FIJO', 'INFORMAL_AMBULANTE']
TIPOS_FORMALES = ['FORMAL_ABARROTES', 'FORMAL_MINISUPER', 'FORMAL_RECAUDERIA']
NOMBRES = ['María', 'José', 'Guadalupe', 'Juan', 'Rosa', 'Luis', 'Ana', 'Carlos', 'Leticia', 'Jorge', 'Patricia',
           'Miguel', 'Verónica', 'Francisco', 'Laura', 'Alejandro', 'Silvia', 'Roberto', 'Elena', 'Ricardo']
APELLIDOS = ['Hernández', 'García', 'Martínez', 'López', 'González', 'Rodríguez', 'Pérez', 'Sánchez', 'Ramírez',
             'Cruz', 'Flores', 'Gómez', 'Treviño', 'Garza', 'Villarreal', 'Cantú', 'Salinas', 'Elizondo']
ESTADOS_PEDIDO = [('ENTREGADO', 55), ('CANCELADO', 8), ('RECHAZADO', 5), ('ENVIADO', 10), ('ACEPTADO', 8),
                  ('EN_PREPARACION', 6), ('ENVIADO_A_COMERCIO', 5), ('BORRADOR', 3)]
SERVICIOS = ['seguridad', 'comercios', 'catalogo', 'inventario', 'precios', 'pedidos', 'analisis', 'notificaciones',
             'proveedores', 'abastecimiento', 'disponibilidad', 'geolocalizacion', 'sincronizacion', 'documentos',
             'reportes', 'recomendaciones', 'demanda', 'ventas', 'entregas', 'auditoria', 'integraciones',
             'configuracion', 'monitoreo', 'busqueda']


def psql(sql, entrada=None):
    r = subprocess.run(PG + ['-At', '-c', sql], input=entrada, capture_output=True, text=True, encoding='utf-8')
    if r.returncode:
        sys.exit(f'psql falló: {r.stderr.strip()[:500]}')
    return r.stdout.strip()


def copiar(tabla, columnas, filas):
    """COPY ... FROM STDIN con las filas en CSV. Devuelve (filas, segundos)."""
    buf = io.StringIO()
    csv.writer(buf, lineterminator='\n').writerows(filas)
    inicio = time.perf_counter()
    r = subprocess.run(PG + ['-c', f"\\copy {tabla} ({', '.join(columnas)}) FROM STDIN WITH (FORMAT csv, NULL '')"],
                       input=buf.getvalue(), capture_output=True, text=True, encoding='utf-8')
    if r.returncode:
        sys.exit(f'COPY {tabla} falló: {r.stderr.strip()[:800]}')
    return len(filas), time.perf_counter() - inicio


def mongo_importar(coleccion, documentos):
    lineas = '\n'.join(json.dumps(d, ensure_ascii=False) for d in documentos)
    inicio = time.perf_counter()
    r = subprocess.run(MONGO + [f'mongoimport --quiet {MONGO_AUTH} --db abastored --collection {coleccion} '
                                f'--numInsertionWorkers 4'],
                       input=lineas, capture_output=True, text=True, encoding='utf-8')
    if r.returncode:
        sys.exit(f'mongoimport {coleccion} falló: {r.stderr.strip()[:500]}')
    return len(documentos), time.perf_counter() - inicio


def mongo_eval(js):
    r = subprocess.run(MONGO + [f'mongosh --quiet {MONGO_AUTH} abastored --eval \'{js}\''],
                       capture_output=True, text=True, encoding='utf-8')
    if r.returncode:
        sys.exit(f'mongosh falló: {r.stderr.strip()[:500]}')
    return r.stdout.strip()


def fecha_json(d):
    return {'$date': d.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'}


def generar(semilla, escala):
    if psql(f"SELECT count(*) FROM usuarios WHERE email LIKE '%@{DOMINIO}'") != '0':
        sys.exit('Ya hay datos masivos cargados: corre «limpiar» primero.')
    rng = random.Random(semilla)
    uid = lambda: str(uuid.UUID(int=rng.getrandbits(128), version=4))   # noqa: E731  (reproducible)
    ahora = datetime(2026, 11, 25, 12, 0, 0)            # fecha fija: mismos datos en cada corrida
    n_com, n_prov = int(4000 * escala), max(int(120 * escala), 10)
    n_ventas, n_pedidos = int(120_000 * escala), int(15_000 * escala)
    n_bitacora, n_busquedas = int(300_000 * escala), int(50_000 * escala)

    productos = {}
    for linea in psql('SELECT id, nombre FROM productos_maestros').splitlines():
        pid, nombre = linea.split('|', 1)
        if nombre in PRECIOS_BASE:
            productos[int(pid)] = PRECIOS_BASE[nombre]
    zonas = [tuple(float(x) if i else int(x) for i, x in enumerate(l.split('|')))
             for l in psql("SELECT id, latitud_centro, longitud_centro, radio_km FROM zonas_municipales "
                           "WHERE activa AND nombre NOT LIKE 'Zona %' ORDER BY id").splitlines()]
    municipios = dict(l.split('|') for l in psql('SELECT id, municipio FROM zonas_municipales').splitlines())
    admin = psql("SELECT id FROM usuarios WHERE email = 'admin@abastored.mx'")
    hash_clave = bcrypt.hashpw(CLAVE.encode(), bcrypt.gensalt(rounds=10)).decode()
    medidas = {}

    # --- usuarios y comercios -------------------------------------------------------------------------
    usuarios, comercios = [], []
    for i in range(n_com):
        u, c = uid(), uid()
        informal = rng.random() < 0.62
        zona, lat0, lon0, radio = rng.choice(zonas)
        # posición dentro del radio de la zona (en grados, ~111 km por grado)
        r, ang = radio * math.sqrt(rng.random()) / 111.0, rng.random() * 2 * math.pi
        lat, lon = lat0 + r * math.cos(ang), lon0 + r * math.sin(ang) / math.cos(math.radians(lat0))
        nombre, ap1, ap2 = rng.choice(NOMBRES), rng.choice(APELLIDOS), rng.choice(APELLIDOS)
        creado = ahora - timedelta(days=rng.randint(30, 400))
        usuarios.append([u, f'comercio{i:05d}@{DOMINIO}', hash_clave, nombre, ap1, ap2, 2 if informal else 3,
                         'true', 'true', creado])
        tipo = rng.choice(TIPOS_INFORMALES if informal else TIPOS_FORMALES)
        estado = 'VERIFICADO' if rng.random() < 0.85 else rng.choice(['PENDIENTE', 'SUSPENDIDO'])
        comercios.append([c, u, f'MASIVO {tipo.split("_")[1].title()} {nombre} {ap1} {i:05d}', tipo,
                          f'Calle {rng.randint(1, 400)} #{rng.randint(100, 2999)}', municipios[str(zona)],
                          'Nuevo León', f'{lat:.7f}', f'{lon:.7f}', zona, estado,
                          admin if estado == 'VERIFICADO' else '', creado if estado == 'VERIFICADO' else '', creado])
    proveedores, usuarios_prov = [], []
    for i in range(n_prov):
        u, p = uid(), uid()
        zona, lat0, lon0, _ = rng.choice(zonas)
        usuarios_prov.append([u, f'proveedor{i:04d}@{DOMINIO}', hash_clave, rng.choice(NOMBRES), rng.choice(APELLIDOS),
                              rng.choice(APELLIDOS), 4, 'true', 'true', ahora - timedelta(days=rng.randint(60, 500))])
        proveedores.append([p, u, f'MASIVO Distribuidora {rng.choice(APELLIDOS)} {i:04d}', municipios[str(zona)],
                            f'{lat0 + rng.uniform(-.02, .02):.7f}', f'{lon0 + rng.uniform(-.02, .02):.7f}',
                            rng.choice([300, 350, 500, 800, 1000]), rng.randint(1, 3), 'VERIFICADO', admin, ahora])
    personal = []                       # analistas, coordinadores y auditores para los escenarios de carga
    for rol, prefijo, n in ((6, 'analista', 30), (7, 'coordinador', 10), (8, 'auditor', 10)):
        for i in range(n):
            personal.append([uid(), f'{prefijo}{i:03d}@{DOMINIO}', hash_clave, rng.choice(NOMBRES), rng.choice(APELLIDOS),
                             rng.choice(APELLIDOS), rol, 'true', 'true', ahora - timedelta(days=rng.randint(30, 300))])
    cols_u = ['id', 'email', 'password_hash', 'nombre', 'apellido_paterno', 'apellido_materno', 'rol_id', 'activo',
              'email_verificado', 'created_at']
    medidas['usuarios'] = copiar('usuarios', cols_u, usuarios + usuarios_prov + personal)
    medidas['comercios'] = copiar('comercios', ['id', 'usuario_id', 'nombre_comercio', 'tipo_comercio', 'direccion',
                                                'municipio', 'estado', 'latitud', 'longitud', 'zona_id',
                                                'estado_registro', 'verificado_por', 'fecha_verificacion',
                                                'created_at'], comercios)
    medidas['proveedores'] = copiar('proveedores', ['id', 'usuario_id', 'nombre_empresa', 'municipio', 'latitud',
                                                    'longitud', 'pedido_minimo', 'tiempo_entrega_dias',
                                                    'estado_verificacion', 'verificado_por', 'fecha_verificacion'],
                                    proveedores)
    psql(f"UPDATE usuarios u SET proveedor_id = p.id FROM proveedores p WHERE p.usuario_id = u.id "
         f"AND u.email LIKE '%@{DOMINIO}'")

    # --- inventario, precios y movimientos ----------------------------------------------------------
    base_inv = 50_000_000                      # ids explícitos lejos de la secuencia (no chocan con altas normales)
    inventario, precios, movimientos = [], [], []
    por_comercio = {}
    for com in comercios:
        c, u, creado = com[0], com[1], com[-1]
        factor = 0.92 if com[3].startswith('INFORMAL') else 1.06     # informales algo más baratos
        elegidos = rng.sample(sorted(productos), rng.randint(8, 25))
        por_comercio[c] = []
        for pid in elegidos:
            iid = base_inv + len(inventario)
            precio = round(productos[pid] * factor * rng.uniform(0.85, 1.15), 2)
            minimo = rng.choice([2, 3, 5, 10])
            existencia = max(0, round(rng.gauss(minimo * 3, minimo * 2)))
            inventario.append([iid, c, pid, existencia, minimo, precio, creado])
            por_comercio[c].append((iid, pid, precio))
            anterior = None
            for k in range(3):                              # historial de precios
                p = round(precio * rng.uniform(0.9, 1.1), 2) if k < 2 else precio
                precios.append([c, pid, p, anterior if anterior else '',
                                creado + timedelta(days=k * rng.randint(20, 90)), 'MANUAL', 'VALIDADO', u])
                anterior = p
            nivel = 0
            for k in range(4):                              # movimientos
                tipo = 'ENTRADA' if k == 0 or rng.random() < 0.4 else 'SALIDA'
                cant = rng.randint(1, 20)
                nuevo = nivel + cant if tipo == 'ENTRADA' else max(nivel - cant, 0)
                movimientos.append([iid, tipo, abs(nuevo - nivel), nivel, nuevo, 'Carga masiva de prueba', u,
                                    creado + timedelta(days=rng.randint(0, 200), minutes=k)])
                nivel = nuevo
    medidas['inventario_comercio'] = copiar('inventario_comercio', ['id', 'comercio_id', 'producto_id', 'existencia',
                                                                    'stock_minimo', 'precio_venta', 'created_at'],
                                            inventario)
    medidas['precios_comercio'] = copiar('precios_comercio', ['comercio_id', 'producto_id', 'precio', 'precio_anterior',
                                                              'fecha_registro', 'metodo_captura', 'estado_validacion',
                                                              'usuario_registro_id'], precios)
    medidas['movimientos_inventario'] = copiar('movimientos_inventario', ['inventario_id', 'tipo', 'cantidad',
                                                                          'existencia_anterior', 'existencia_nueva',
                                                                          'motivo', 'usuario_id', 'created_at'],
                                               movimientos)

    # --- ventas ------------------------------------------------------------------------------------
    ventas, detalle_ventas = [], []
    claves = [c[0] for c in comercios]
    duenos = {c[0]: c[1] for c in comercios}
    for _ in range(n_ventas):
        c = rng.choice(claves)
        v = uid()
        partidas = rng.sample(por_comercio[c], min(len(por_comercio[c]), rng.randint(1, 3)))
        total = 0
        for iid, pid, precio in partidas:
            cant = rng.randint(1, 4)
            total += cant * precio
            detalle_ventas.append([v, iid, pid, cant, precio, round(cant * precio, 2)])
        fecha = ahora - timedelta(days=rng.randint(0, 180), minutes=rng.randint(0, 1440))
        ventas.append([v, c, duenos[c], round(total, 2), rng.choices(['EFECTIVO', 'TARJETA', 'TRANSFERENCIA', 'FIADO'],
                                                                     [70, 12, 13, 5])[0],
                       rng.choices(['web', 'android', 'escritorio'], [35, 60, 5])[0], fecha, fecha])
    medidas['ventas'] = copiar('ventas', ['id', 'comercio_id', 'usuario_id', 'total', 'metodo_pago', 'origen',
                                          'fecha_venta', 'created_at'], ventas)
    medidas['detalle_ventas'] = copiar('detalle_ventas', ['venta_id', 'inventario_id', 'producto_id', 'cantidad',
                                                          'precio_unitario', 'subtotal'], detalle_ventas)

    # --- pedidos de abasto -------------------------------------------------------------------------
    pedidos, detalle_pedidos, eventos_pedido = [], [], []
    estados, pesos = zip(*ESTADOS_PEDIDO)
    for _ in range(n_pedidos):
        c = rng.choice(claves)
        prov = rng.choice(proveedores)
        pid_pedido = uid()
        estado = rng.choices(estados, pesos)[0]
        creado = ahora - timedelta(days=rng.randint(0, 180), minutes=rng.randint(0, 1440))
        subtotal = 0
        for pid in rng.sample(sorted(productos), rng.randint(2, 4)):
            cant, precio = rng.randint(5, 40), round(productos[pid] * 0.78 * rng.uniform(0.9, 1.1), 2)
            subtotal += cant * precio
            detalle_pedidos.append([pid_pedido, pid, cant, precio, round(cant * precio, 2)])
        envio = creado + timedelta(minutes=rng.randint(1, 120)) if estado != 'BORRADOR' else ''
        entrega = creado + timedelta(days=rng.randint(1, 4)) if estado == 'ENTREGADO' else ''
        pedidos.append([pid_pedido, c, prov[0], estado, envio, entrega, round(subtotal, 2),
                        round(subtotal * 0.02, 2), duenos[c], creado, creado])
        eventos_pedido.append({'pedido_id': pid_pedido, 'proveedor_id': prov[0], 'estado_anterior': None,
                               'estado_nuevo': estado, 'fecha': fecha_json(creado), 'masivo': True})
    medidas['pedidos_abasto'] = copiar('pedidos_abasto', ['id', 'comercio_id', 'proveedor_id', 'estado',
                                                          'fecha_envio', 'fecha_entrega_real', 'subtotal',
                                                          'comision_plataforma', 'usuario_creacion_id',
                                                          'created_at', 'updated_at'], pedidos)
    medidas['detalle_pedidos'] = copiar('detalle_pedidos', ['pedido_id', 'producto_id', 'cantidad', 'precio_unitario',
                                                            'subtotal'], detalle_pedidos)
    medidas['eventos_pedido (Mongo)'] = mongo_importar('eventos_pedido', eventos_pedido)

    # --- MongoDB: bitácora de peticiones (últimos 25 días; la colección vence a los 30) y búsquedas ------
    todos_usuarios = [u[0] for u in usuarios]
    rutas = ['/api/v1/inventario', '/api/v1/precios', '/api/v1/pedidos', '/api/v1/comercios', '/api/v1/ventas',
             '/api/v1/recomendaciones', '/api/v1/disponibilidad', '/api/v1/notificaciones/contador']
    reciente = datetime.now(timezone.utc)
    bitacora = []
    for _ in range(n_bitacora):
        estado = rng.choices([200, 201, 400, 401, 403, 404, 429, 500], [80, 8, 3, 2, 2, 3, 1, 1])[0]
        bitacora.append({'servicio': rng.choice(SERVICIOS), 'metodo': rng.choices(['GET', 'POST', 'PATCH'], [75, 20, 5])[0],
                         'ruta': rng.choice(rutas), 'endpoint': 'masivo', 'status': estado,
                         'codigo_error': None if estado < 400 else 'masivo',
                         'duracion_ms': round(rng.lognormvariate(2.7, 0.6), 1), 'usuario_id': rng.choice(todos_usuarios),
                         'rol': 'Comerciante Informal', 'ip': f'10.{rng.randint(0, 255)}.{rng.randint(0, 255)}.{rng.randint(1, 254)}',
                         'formato': rng.choices(['json', 'xml'], [85, 15])[0], 'correlation_id': uid().replace('-', ''),
                         'fecha': fecha_json(reciente - timedelta(seconds=rng.randint(0, 25 * 86400))), 'masivo': True})
    medidas['bitacora_peticiones (Mongo)'] = mongo_importar('bitacora_peticiones', bitacora)
    textos = list(PRECIOS_BASE) + ['tortillas', 'leche deslactosada', 'chile serrano', 'pan dulce', 'garrafón']
    busquedas = [{'texto': rng.choice(textos).lower(), 'producto_id': None, 'zona_id': rng.choice(zonas)[0],
                  'resultados': rng.randint(0, 30), 'origen': 'busqueda', 'encontrado': rng.random() < 0.8,
                  'usuario_id': None, 'fecha': fecha_json(reciente - timedelta(seconds=rng.randint(0, 60 * 86400))),
                  'masivo': True} for _ in range(n_busquedas)]
    medidas['demanda_busquedas (Mongo)'] = mongo_importar('demanda_busquedas', busquedas)

    psql('ANALYZE')
    total = sum(n for n, _ in medidas.values())
    print(f'Semilla {semilla}, escala {escala}: {total:,} filas/documentos')
    print(f'{"tabla":34} {"filas":>10} {"segundos":>9} {"filas/s":>9}')
    for tabla, (n, s) in medidas.items():
        print(f'{tabla:34} {n:>10,} {s:>9.1f} {n / s if s else 0:>9,.0f}')
    print('Tamaño de la base PostgreSQL:', psql("SELECT pg_size_pretty(pg_database_size('abastored'))"))


def contar():
    print(psql(f"""SELECT 'usuarios', count(*) FROM usuarios WHERE email LIKE '%@{DOMINIO}'
        UNION ALL SELECT 'usuarios activos', count(*) FROM usuarios WHERE email LIKE '%@{DOMINIO}' AND activo
        UNION ALL SELECT 'comercios', count(*) FROM comercios WHERE nombre_comercio LIKE 'MASIVO %'
        UNION ALL SELECT 'inventario_comercio', count(*) FROM inventario_comercio WHERE id >= 50000000
        UNION ALL SELECT 'ventas', count(*) FROM ventas v JOIN comercios c ON c.id = v.comercio_id
                  WHERE c.nombre_comercio LIKE 'MASIVO %'
        UNION ALL SELECT 'pedidos_abasto', count(*) FROM pedidos_abasto p JOIN comercios c ON c.id = p.comercio_id
                  WHERE c.nombre_comercio LIKE 'MASIVO %'"""))
    print(mongo_eval('["bitacora_peticiones","demanda_busquedas","eventos_pedido"].forEach(c => '
                     'print(c + "|" + db.getCollection(c).countDocuments({masivo: true})))'))
    print('Tamaño de la base PostgreSQL:', psql("SELECT pg_size_pretty(pg_database_size('abastored'))"))


def limpiar():
    """Borra lo generado (y lo que esas cuentas crearon durante la carga en tablas de comercio)."""
    inicio = time.perf_counter()
    comercios = f"SELECT id FROM comercios WHERE nombre_comercio LIKE 'MASIVO %'"
    usuarios = f"SELECT id FROM usuarios WHERE email LIKE '%@{DOMINIO}'"
    psql(f"""BEGIN;
        DELETE FROM detalle_ventas WHERE venta_id IN (SELECT id FROM ventas WHERE comercio_id IN ({comercios}));
        DELETE FROM ventas WHERE comercio_id IN ({comercios});
        DELETE FROM detalle_pedidos WHERE pedido_id IN (SELECT id FROM pedidos_abasto WHERE comercio_id IN ({comercios}));
        DELETE FROM historial_pedido WHERE pedido_id IN (SELECT id FROM pedidos_abasto WHERE comercio_id IN ({comercios}));
        DELETE FROM pedidos_abasto WHERE comercio_id IN ({comercios});
        DELETE FROM movimientos_inventario WHERE inventario_id IN (SELECT id FROM inventario_comercio WHERE comercio_id IN ({comercios}));
        DELETE FROM precios_comercio WHERE comercio_id IN ({comercios});
        DELETE FROM inventario_comercio WHERE comercio_id IN ({comercios});
        DELETE FROM comercios WHERE id IN ({comercios});
        UPDATE usuarios SET proveedor_id = NULL WHERE id IN ({usuarios});
        DELETE FROM proveedores WHERE usuario_id IN ({usuarios});
        DELETE FROM usuarios WHERE id IN ({usuarios}) AND id NOT IN (SELECT usuario_id FROM auditoria_eventos
                                                                     WHERE usuario_id IS NOT NULL);
        -- La bitácora de auditoría es de solo inserción (trigger): las cuentas que actuaron durante la carga
        -- no se borran, se desactivan y conservan su rastro.
        UPDATE usuarios SET activo = false WHERE id IN ({usuarios});
        COMMIT;""")
    quedan = psql(f"SELECT count(*) FROM usuarios WHERE email LIKE '%@{DOMINIO}'")
    print(f'Cuentas masivas conservadas (desactivadas) por tener eventos de auditoría: {quedan}')
    print(mongo_eval('["bitacora_peticiones","demanda_busquedas","eventos_pedido"].forEach(c => '
                     'print(c + " borrados: " + db.getCollection(c).deleteMany({masivo: true}).deletedCount))'))
    psql('VACUUM ANALYZE')
    print(f'Datos masivos eliminados en {time.perf_counter() - inicio:.1f} s')


if __name__ == '__main__':
    argumentos = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    argumentos.add_argument('accion', choices=['generar', 'contar', 'limpiar'])
    argumentos.add_argument('--semilla', type=int, default=2026)
    argumentos.add_argument('--escala', type=float, default=1.0)
    a = argumentos.parse_args()
    {'generar': lambda: generar(a.semilla, a.escala), 'contar': contar, 'limpiar': limpiar}[a.accion]()
