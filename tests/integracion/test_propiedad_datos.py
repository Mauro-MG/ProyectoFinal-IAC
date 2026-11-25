"""
Propiedad de datos en la base de datos (retroalimentación del avance 2).

Cada servicio entra a PostgreSQL con su propio usuario (db/postgres/05_roles.sql). Estas pruebas
comprueban, preguntándole a PostgreSQL, que:

  * cada tabla tiene exactamente un servicio que puede escribirla (la tabla de docs/propiedad_de_datos.md);
  * el web es de solo lectura;
  * auditoria_eventos es de solo inserción para todos;
  * un servicio que intenta escribir en una tabla ajena recibe «permission denied»;
  * los servicios en marcha están conectados con su usuario y no con el superusuario.

Se conectan como lo haría un administrador: desde el anfitrión con `docker exec` (conexión local del
contenedor) o, desde el contenedor de pruebas, por la red con la contraseña de cada usuario.
"""
import shutil
import subprocess

import pytest

from apoyo import MODO, RAIZ, sesion_de

# Especificación: tabla -> servicio dueño (el único que escribe). Debe coincidir con docs/propiedad_de_datos.md
DUENOS = {
    'usuarios': 'seguridad', 'roles': 'seguridad',
    'comercios': 'comercios', 'responsables_comercio': 'comercios',
    'productos_maestros': 'catalogo', 'categorias': 'catalogo', 'marcas': 'catalogo', 'unidades_medida': 'catalogo',
    'variantes_producto': 'catalogo', 'equivalencias_producto': 'catalogo',
    'inventario_comercio': 'inventario', 'movimientos_inventario': 'inventario', 'reservas_inventario': 'inventario',
    'transferencias_inventario': 'inventario',
    'precios_comercio': 'precios', 'promociones': 'precios',
    'pedidos_abasto': 'pedidos', 'detalle_pedidos': 'pedidos', 'historial_pedido': 'pedidos',
    'proveedores': 'proveedores', 'proveedor_zonas': 'proveedores', 'catalogo_proveedor': 'proveedores',
    'precios_mayoreo': 'proveedores', 'evaluaciones_proveedor': 'proveedores', 'salidas_catalogo': 'proveedores',
    'solicitudes_cotizacion': 'abastecimiento', 'necesidades_solicitud': 'abastecimiento',
    'cotizaciones': 'abastecimiento', 'partidas_cotizacion': 'abastecimiento', 'ordenes_compra': 'abastecimiento',
    'partidas_orden': 'abastecimiento',
    'zonas_municipales': 'geolocalizacion', 'colonias': 'geolocalizacion',
    'ventas': 'ventas', 'detalle_ventas': 'ventas', 'devoluciones': 'ventas', 'detalle_devoluciones': 'ventas',
    'entregas': 'entregas', 'eventos_entrega': 'entregas', 'incidencias_entrega': 'entregas',
    'configuracion_sistema': 'configuracion', 'catalogos_administrativos': 'configuracion',
}


def _base_datos():
    for linea in (RAIZ / '.env').read_text(encoding='utf-8').splitlines() if (RAIZ / '.env').exists() else []:
        if linea.startswith('POSTGRES_DB='):
            return linea.split('=', 1)[1].strip()
    return 'abastored'


@pytest.fixture(scope='module')
def sql():
    """sql(consulta, usuario='abastored_web') -> filas (listas de texto) o lanza RuntimeError con el error."""
    base = _base_datos()
    if MODO == 'interno':
        import psycopg2

        def ejecutar(consulta, usuario='abastored_web'):
            clave = (RAIZ / 'secrets' / f'pg_{usuario}.txt').read_text(encoding='utf-8').strip()
            conexion = psycopg2.connect(host='abastored-postgres', dbname=base, user=usuario, password=clave)
            try:
                with conexion.cursor() as cursor:
                    cursor.execute(consulta)
                    return [[str(c) for c in fila] for fila in cursor.fetchall()] if cursor.description else []
            except psycopg2.Error as error:
                raise RuntimeError(str(error))
            finally:
                conexion.rollback()
                conexion.close()
        return ejecutar

    if not shutil.which('docker'):
        pytest.skip('No aplica: requiere el CLI de Docker en el equipo anfitrión para consultar PostgreSQL')

    def ejecutar(consulta, usuario='abastored_web'):
        r = subprocess.run(['docker', 'exec', 'abastored-postgres', 'psql', '-U', usuario, '-d', base, '-v',
                            'ON_ERROR_STOP=1', '-tA', '-F', '|', '-c', f'BEGIN; {consulta}; ROLLBACK;'],
                           capture_output=True, text=True, timeout=30)
        if r.returncode:
            raise RuntimeError(r.stderr.strip())
        return [linea.split('|') for linea in r.stdout.splitlines() if linea and linea not in ('BEGIN', 'ROLLBACK')]
    return ejecutar


# Quién puede escribir cada tabla, según PostgreSQL (has_table_privilege no cuenta permisos por columna)
ESCRITORES = """
    SELECT t.tablename, r.rolname FROM pg_tables t CROSS JOIN pg_roles r
    WHERE t.schemaname = 'public' AND (r.rolname LIKE 'ms\\_%' OR r.rolname = 'abastored_web')
      AND (has_table_privilege(r.rolname, 'public.' || t.tablename, 'INSERT')
           OR has_table_privilege(r.rolname, 'public.' || t.tablename, 'UPDATE')
           OR has_table_privilege(r.rolname, 'public.' || t.tablename, 'DELETE'))"""


def _privilegios(sql, rol, tabla):
    filas = sql(f"SELECT p FROM unnest(ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE']) p "
                f"WHERE has_table_privilege('{rol}', 'public.{tabla}', p)")
    return {f[0] for f in filas}


def test_cada_tabla_la_escribe_solo_su_servicio_dueno(sql):
    filas = sql(ESCRITORES)
    escritores = {}
    for tabla, rol in filas:
        escritores.setdefault(tabla, set()).add(rol)
    todos = {f'ms_{s}' for s in DUENOS.values()}
    auditoria = escritores.pop('auditoria_eventos', set())
    assert escritores == {tabla: {f'ms_{dueno}'} for tabla, dueno in DUENOS.items()}
    assert todos <= auditoria   # todos registran su evento en la transacción de su operación


def test_auditoria_es_de_solo_insercion(sql):
    for servicio in ('ventas', 'auditoria', 'busqueda'):
        assert _privilegios(sql, f'ms_{servicio}', 'auditoria_eventos') == {'SELECT', 'INSERT'}


def test_el_web_es_de_solo_lectura(sql):
    assert not [f for f in sql(ESCRITORES) if f[1] == 'abastored_web']
    assert _privilegios(sql, 'abastored_web', 'comercios') == {'SELECT'}
    with pytest.raises(RuntimeError, match='permission denied for table comercios'):
        sql('UPDATE comercios SET nombre_comercio = nombre_comercio WHERE false')


def test_un_servicio_no_puede_escribir_en_una_tabla_ajena(sql):
    # ms-ventas sí escribe sus ventas, pero no el inventario: para descontar existencias llama a ms-inventario
    sql('UPDATE ventas SET id = id WHERE false', usuario='ms_ventas')
    with pytest.raises(RuntimeError, match='permission denied for table inventario_comercio'):
        sql('UPDATE inventario_comercio SET existencia = 0 WHERE false', usuario='ms_ventas')
    # Excepción documentada: ms-precios cambia SOLO la columna precio_venta del renglón de inventario
    sql('UPDATE inventario_comercio SET precio_venta = precio_venta WHERE false', usuario='ms_precios')
    with pytest.raises(RuntimeError, match='permission denied for table inventario_comercio'):
        sql('UPDATE inventario_comercio SET existencia = existencia WHERE false', usuario='ms_precios')


def test_los_servicios_se_conectan_con_su_propio_usuario(sql):
    # Una consulta real a ms-ventas (con su comercio) abre su conexión aunque ninguna prueba anterior lo haya usado
    comerciante = sesion_de('comerciante')
    comercio = comerciante.get('comercios', '/comercios').json()['items'][0]
    assert comerciante.get('ventas', '/ventas', params={'comercio_id': comercio['id']}).status_code == 200
    usuarios = {f[0] for f in sql("SELECT DISTINCT usename FROM pg_stat_activity "
                                  "WHERE datname = current_database()")}  # procesos internos: sin base
    assert 'ms_ventas' in usuarios
    assert usuarios <= {f'ms_{s}' for s in set(DUENOS.values()) | _solo_lectura()} | {'abastored_web'}, usuarios


def _solo_lectura():
    from abasto_dominio.registro_servicios import NOMBRES
    return set(NOMBRES)
