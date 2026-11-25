"""
Planes de ejecución de las consultas reales de la aplicación con los datos masivos cargados.

    python tests/carga/medir_consultas.py <etiqueta>      # p. ej. «antes_indices» o «despues_indices»

Corre EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) en el PostgreSQL local (docker exec) y guarda en
tests/carga/resultados/<fecha>_<etiqueta>/ el plan original de cada consulta y un resumen con tiempo,
filas y tipo de recorrido. Los DELETE se ejecutan dentro de BEGIN ... ROLLBACK: miden cuánto tarda la
revisión de llaves foráneas sin borrar nada.

Las consultas son las mismas que arman los servicios (se cita de dónde sale cada una), con parámetros
reales: el comercio con más ventas, el proveedor con más pedidos y una zona con comercios.
"""
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PG = ['docker', 'exec', '-i', 'abastored-postgres', 'psql', '-v', 'ON_ERROR_STOP=1', '-U', 'abastored_admin',
      '-d', 'abastored', '-At', '-q']
RAIZ = Path(__file__).resolve().parent


def sql(consulta):
    r = subprocess.run(PG + ['-c', consulta], capture_output=True, text=True, encoding='utf-8')
    if r.returncode:
        sys.exit(f'psql: {r.stderr.strip()[:600]}')
    return r.stdout.strip()


def explicar(consulta, revertir=False):
    cuerpo = f'EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {consulta}'
    if revertir:
        r = subprocess.run(PG + ['-c', 'BEGIN', '-c', cuerpo, '-c', 'ROLLBACK'], capture_output=True, text=True,
                           encoding='utf-8')
        if r.returncode:
            sys.exit(f'psql: {r.stderr.strip()[:600]}')
        salida = r.stdout.strip()
    else:
        salida = sql(cuerpo)
    return json.loads(salida[salida.index('['):salida.rindex(']') + 1])[0]


def nodos(plan, acumulado=None):
    acumulado = [] if acumulado is None else acumulado
    acumulado.append(f"{plan['Node Type']}{' on ' + plan['Relation Name'] if 'Relation Name' in plan else ''}"
                     f"{' (' + plan['Index Name'] + ')' if 'Index Name' in plan else ''}")
    for hijo in plan.get('Plans', []):
        nodos(hijo, acumulado)
    return acumulado


def main(etiqueta):
    comercio = sql("SELECT comercio_id FROM ventas GROUP BY 1 ORDER BY count(*) DESC LIMIT 1")
    proveedor = sql("SELECT proveedor_id FROM pedidos_abasto GROUP BY 1 ORDER BY count(*) DESC LIMIT 1")
    pedido = sql(f"SELECT id FROM pedidos_abasto WHERE proveedor_id = '{proveedor}' LIMIT 1")
    venta = sql(f"SELECT id FROM ventas WHERE comercio_id = '{comercio}' LIMIT 1")
    producto = sql("SELECT id FROM productos_maestros WHERE nombre = 'Arroz blanco 1 kg'")
    consultas = {
        'ventas_productos_mas_vendidos': ('ms-ventas GET /ventas/productos (app.py, mas_vendidos)', f"""
            SELECT d.producto_id, p.nombre, sum(d.cantidad - d.cantidad_devuelta) AS unidades,
                   sum((d.cantidad - d.cantidad_devuelta) * d.precio_unitario) AS importe, count(DISTINCT v.id)
            FROM detalle_ventas d JOIN ventas v ON v.id = d.venta_id JOIN productos_maestros p ON p.id = d.producto_id
            WHERE v.comercio_id = '{comercio}' AND v.fecha_venta >= now() - interval '90 days'
            GROUP BY d.producto_id, p.nombre ORDER BY unidades DESC LIMIT 10""", False),
        'reporte_ventas_por_dia': ('ms-reportes generadores.ventas', f"""
            SELECT v.fecha_venta::date AS dia, count(DISTINCT v.id), sum(d.cantidad - d.cantidad_devuelta),
                   sum((d.cantidad - d.cantidad_devuelta) * d.precio_unitario)
            FROM ventas v JOIN detalle_ventas d ON d.venta_id = v.id
            WHERE v.comercio_id = '{comercio}' AND v.fecha_venta >= now() - interval '90 days' GROUP BY 1 ORDER BY 1""",
                                   False),
        'inventario_de_un_comercio': ('ms-inventario GET /comercios/{id}/inventario', f"""
            SELECT i.*, p.nombre FROM inventario_comercio i JOIN productos_maestros p ON p.id = i.producto_id
            WHERE i.comercio_id = '{comercio}' AND i.activo ORDER BY p.nombre""", False),
        'pedidos_de_un_proveedor': ('ms-pedidos GET /pedidos (vista del proveedor)', f"""
            SELECT * FROM pedidos_abasto WHERE proveedor_id = '{proveedor}' AND estado = 'ENVIADO'
            ORDER BY created_at DESC LIMIT 20""", False),
        'analisis_oferta_por_zona_producto': ('analisis._oferta_por_zona_producto (GET /analisis/zonas)', """
            SELECT c.zona_id, i.producto_id, count(i.id), count(i.id) FILTER (WHERE i.existencia > 0),
                   coalesce(sum(i.existencia), 0), max(i.updated_at)
            FROM inventario_comercio i JOIN comercios c ON i.comercio_id = c.id
            WHERE i.activo AND c.activo AND c.estado_registro = 'VERIFICADO' GROUP BY c.zona_id, i.producto_id""",
                                              False),
        'analisis_ventas_por_zona_producto': ('analisis._ventas_por_zona_producto (GET /analisis/zonas)', """
            SELECT c.zona_id, i.producto_id, sum(m.cantidad) FROM movimientos_inventario m
            JOIN inventario_comercio i ON m.inventario_id = i.id JOIN comercios c ON i.comercio_id = c.id
            WHERE m.tipo = 'SALIDA' AND m.created_at >= now() - make_interval(0, 0, 0, 30)
            GROUP BY c.zona_id, i.producto_id""", False),
        'analisis_precio_promedio_zona': ('analisis._precio_promedio_por_zona_producto', """
            SELECT c.zona_id, pc.producto_id, avg(pc.precio) FROM precios_comercio pc
            JOIN comercios c ON pc.comercio_id = c.id
            WHERE pc.estado_validacion = 'VALIDADO' AND pc.activo AND pc.fecha_registro >= now() - interval '30 days'
            GROUP BY c.zona_id, pc.producto_id""", False),
        'disponibilidad_publica_producto': ('ms-disponibilidad GET /disponibilidad?producto_id=', f"""
            SELECT c.id, c.nombre_comercio, c.zona_id, i.existencia, i.precio_venta
            FROM inventario_comercio i JOIN comercios c ON c.id = i.comercio_id
            WHERE i.producto_id = {producto} AND i.activo AND i.existencia > 0 AND c.activo
              AND c.estado_registro = 'VERIFICADO' ORDER BY i.precio_venta LIMIT 50""", False),
        'borrar_un_pedido (revision FK)': ('borrado de un pedido: revisa movimientos_inventario.pedido_id', f"""
            DELETE FROM pedidos_abasto WHERE id = '{pedido}'""", True),
        'borrar_una_venta (revision FK)': ('borrado de una venta: revisa detalle_ventas.venta_id y devoluciones', f"""
            WITH partidas AS (DELETE FROM detalle_ventas WHERE venta_id = '{venta}')
            DELETE FROM ventas WHERE id = '{venta}'""", True),
    }
    salida = RAIZ / 'resultados' / f"{datetime.now():%Y%m%d_%H%M}_{etiqueta}"
    salida.mkdir(parents=True, exist_ok=True)
    resumen = []
    for nombre, (origen, consulta, revertir) in consultas.items():
        plan = explicar(' '.join(consulta.split()), revertir)
        (salida / f"{nombre.split(' ')[0]}.json").write_text(json.dumps(plan, indent=2), encoding='utf-8')
        disparadores = sum(t.get('Time', 0) for t in plan.get('Triggers', []))
        recorridos = [n for n in nodos(plan['Plan']) if 'Scan' in n]
        resumen.append({'consulta': nombre, 'origen': origen, 'ms_ejecucion': round(plan['Execution Time'], 2),
                        'ms_disparadores_fk': round(disparadores, 2), 'filas': plan['Plan'].get('Actual Rows'),
                        'recorridos': recorridos})
    commit = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], capture_output=True, text=True).stdout.strip()
    tamanos = sql("SELECT string_agg(relname || '=' || n_live_tup, ', ' ORDER BY n_live_tup DESC) FROM "
                  "pg_stat_user_tables WHERE n_live_tup > 10000")
    (salida / 'resumen.json').write_text(json.dumps({'fecha': datetime.now().isoformat(timespec='seconds'),
                                                    'commit': commit, 'etiqueta': etiqueta, 'tablas': tamanos,
                                                    'consultas': resumen}, indent=2, ensure_ascii=False),
                                         encoding='utf-8')
    print(f'{"consulta":36} {"ms":>9} {"ms FK":>8}  recorridos')
    for r in resumen:
        print(f"{r['consulta']:36} {r['ms_ejecucion']:>9} {r['ms_disparadores_fk']:>8}  {'; '.join(r['recorridos'])[:110]}")
    print('Resultados en', salida)


if __name__ == '__main__':
    os.chdir(RAIZ.parents[1])
    main(sys.argv[1] if len(sys.argv) > 1 else 'medicion')
