"""
ms-analisis: indicadores comerciales, cobertura territorial, brechas e índice de acceso.

Agrupa en un solo servicio los algoritmos que comparten los mismos datos de
entrada (oferta por zona y producto, ventas, proveedores por zona): separarlos
obligaría a repetir esas consultas en varios servicios.

Servicio de CONSULTA sobre PostgreSQL (lee comercios, inventario, movimientos, proveedores y zonas;
no escribe en ellos). Es DUEÑO de la colección ejecuciones_analisis. Las recomendaciones por
comercio pasaron a ms-recomendaciones.
Redis: resultados en caché con versión (`analisis:v{n}:*`); cualquier cambio de inventario
o comercio incrementa `analisis:version`.
MongoDB: ejecuciones_analisis (resultado de cada corrida para ver la evolución por zona).
"""
from pathlib import Path
from uuid import UUID

from flask import g

from abasto_api import ErrorApi, Servicio, no_encontrado, sobre_lista, tiene, usuario_actual
from abasto_dominio.servicios import analisis, historicos
from abasto_dominio.servicios.cache import obtener_o_calcular

from esquemas import (CONTRATOS_XML, BrechasConsulta, EvolucionConsulta, GraficaConsulta, MapaConsulta,
                      OportunidadesConsulta)

srv = Servicio('analisis', 'Análisis territorial',
               'Cobertura por zona, índice de acceso a la canasta básica y ranking de zonas, detección de brechas '
               'de surtido, zonas desatendidas, estadísticas territoriales por municipio, oportunidades de abasto, '
               'historial de ejecuciones y datos listos para Highcharts.',
               xsd=Path(__file__).parent / 'xsd' / 'analisis.xsd', contratos=CONTRATOS_XML)
app = srv.app


@srv.ruta('/analisis/zonas', 'GET', resumen='Cobertura e índice de acceso por zona', etiqueta='Cobertura',
          permisos=['analisis.ver', 'recomendaciones.ver'], raiz_xml='zonas')
def zonas():
    """Índice de acceso = promedio de la cobertura de la canasta básica. Ranking 1 = peor acceso (prioridad)."""
    lista = analisis.indicadores_zonas()
    return {'umbrales': dict(zip(('alta', 'media', 'baja'), analisis.umbrales())), 'zonas': lista}


@srv.ruta('/analisis/brechas', 'GET', resumen='Brechas de surtido por zona y producto', etiqueta='Brechas',
          permisos=['analisis.ver'], consulta=BrechasConsulta, raiz_xml='brechas')
def brechas(q):
    """Cobertura = comercios con existencia / comercios de la zona. Nivel ALTA < 30 %, MEDIA < 60 %, BAJA < 80 %.
    Déficit = puntos de venta que la población requiere − puntos con existencia. Paginado."""
    filas = analisis.brechas(q.zona_id, q.categoria_id, q.producto_id, q.canasta_basica, q.nivel)
    inicio = (q.pagina - 1) * q.por_pagina
    totales = {n: sum(1 for f in filas if f['nivel'] == n) for n in ('ALTA', 'MEDIA', 'BAJA', 'SIN_BRECHA')}
    return {**sobre_lista(filas[inicio:inicio + q.por_pagina], len(filas), q.pagina, q.por_pagina, 'brechas'),
            'totales': totales}


@srv.ruta('/analisis/mapa', 'GET', resumen='Puntos para el mapa de cobertura', etiqueta='Cobertura',
          permisos=['analisis.ver'], consulta=MapaConsulta, raiz_xml='mapa')
def mapa(q):
    return obtener_o_calcular(f'mapa:{q.producto_id or "todos"}', lambda: analisis.puntos_mapa(q.producto_id))


@srv.ruta('/analisis/oportunidades', 'GET', resumen='Oportunidades de abasto', etiqueta='Brechas',
          permisos=['reportes.ver', 'pedidos.atender'], consulta=OportunidadesConsulta, raiz_xml='oportunidades')
def oportunidades(q):
    """Zona y producto con brecha ALTA o MEDIA y demanda. Analistas ven todo; un proveedor sólo sus zonas de
    entrega y sólo con plan DESTACADO (modelo de negocio)."""
    zona_ids = None
    if not tiene('reportes.ver'):
        empresa = usuario_actual().proveedor_vinculado
        if not empresa or empresa.plan != 'DESTACADO':
            raise ErrorApi(403, 'plan_requerido', 'El reporte de oportunidades es parte del plan Destacado.')
        zona_ids = {z.id for z in empresa.zonas}
    filas = [f for f in analisis.brechas() if f['nivel'] in ('ALTA', 'MEDIA')
             and (f['canasta_basica'] or f['ventas'] > 0) and (zona_ids is None or f['zona_id'] in zona_ids)]
    campos = ('zona_id', 'zona', 'producto_id', 'producto', 'cobertura', 'nivel', 'sin_disponibilidad',
              'comercios_analizados', 'ventas', 'proveedores', 'precio_mayoreo_min', 'precio_promedio')
    return {'total': len(filas), 'oportunidades': [{k: f[k] for k in campos} for f in filas[:q.limite]]}


@srv.ruta('/analisis/ejecuciones', 'POST', resumen='Ejecutar y guardar el análisis de cobertura',
          etiqueta='Históricos (MongoDB)', permisos=['analisis.ver'], status=201, raiz_xml='ejecucion')
def ejecutar():
    """Calcula los indicadores por zona y guarda el resultado como documento en MongoDB (ejecuciones_analisis)."""
    indicadores = analisis.indicadores_zonas()
    ejecucion_id = historicos.registrar_ejecucion_analisis(indicadores, UUID(g.claims['sub']))
    return {'id': ejecucion_id, 'zonas': len(indicadores),
            'criticas': sum(1 for z in indicadores if z['clasificacion'] == 'Crítico')}


@srv.ruta('/analisis/ejecuciones/evolucion', 'GET', resumen='Evolución del índice de acceso (agregación MongoDB)',
          etiqueta='Históricos (MongoDB)', permisos=['analisis.ver'], consulta=EvolucionConsulta, raiz_xml='evolucion')
def evolucion(q):
    return {'dias': q.dias, 'zona_id': q.zona_id, 'datos': historicos.evolucion_indice(q.zona_id, q.dias)}


@srv.ruta('/analisis/municipios', 'GET', resumen='Estadísticas territoriales por municipio', etiqueta='Cobertura',
          permisos=['analisis.ver'], raiz_xml='municipios')
def municipios():
    """Agrupa los indicadores de las zonas por municipio: población, comercios, proveedores, habitantes por comercio,
    índice de acceso promedio y zonas en situación crítica (zonas desatendidas)."""
    agrupado = {}
    for z in analisis.indicadores_zonas():
        m = agrupado.setdefault(z['municipio'], {'municipio': z['municipio'], 'zonas': 0, 'poblacion': 0, 'comercios': 0,
                                                 'formales': 0, 'informales': 0, 'proveedores': 0, 'indices': [],
                                                 'zonas_criticas': 0})
        m['zonas'] += 1
        for campo in ('poblacion', 'comercios', 'formales', 'informales'):
            m[campo] += z[campo] or 0
        m['proveedores'] = max(m['proveedores'], z['proveedores'])
        if z['indice_acceso'] is not None:
            m['indices'].append(z['indice_acceso'])
        m['zonas_criticas'] += z['clasificacion'] in ('Crítico', 'Sin comercios')
    lista = []
    for m in agrupado.values():
        indices = m.pop('indices')
        lista.append({**m, 'habitantes_por_comercio': round(m['poblacion'] / m['comercios'], 1) if m['comercios'] else None,
                      'indice_acceso_promedio': round(sum(indices) / len(indices), 1) if indices else None})
    return {'municipios': sorted(lista, key=lambda m: (m['indice_acceso_promedio'] is None, m['indice_acceso_promedio'] or 0))}


GRAFICAS = ('cobertura', 'brechas', 'sectores', 'evolucion')


@srv.ruta('/analisis/graficas/<grafica>', 'GET', resumen='Datos listos para Highcharts', etiqueta='Gráficas',
          permisos=['analisis.ver'], consulta=GraficaConsulta, raiz_xml='grafica', errores=(401, 403, 404, 422))
def grafica(grafica, q):
    """`categories` y `series` con el formato de Highcharts (xAxis.categories y series[].data):
    cobertura (índice de acceso por zona), brechas (renglones ALTA/MEDIA/BAJA por zona), sectores (comercios formales e
    informales por zona) y evolucion (índice de acceso por fecha de ejecución, MongoDB)."""
    if grafica not in GRAFICAS:
        raise no_encontrado(f'La gráfica {grafica}; usa {", ".join(GRAFICAS)}')
    zonas_ = [z for z in analisis.indicadores_zonas() if not q.zona_id or z['id'] == q.zona_id]
    nombres = [z['nombre'] for z in zonas_]
    if grafica == 'cobertura':
        return {'grafica': grafica, 'titulo': 'Índice de acceso a la canasta básica por zona', 'tipo': 'bar',
                'categories': nombres, 'series': [{'name': 'Índice de acceso', 'data': [z['indice_acceso'] for z in zonas_]}]}
    if grafica == 'sectores':
        return {'grafica': grafica, 'titulo': 'Comercios por sector y zona', 'tipo': 'column', 'categories': nombres,
                'series': [{'name': 'Formales', 'data': [z['formales'] for z in zonas_]},
                           {'name': 'Informales', 'data': [z['informales'] for z in zonas_]}]}
    if grafica == 'brechas':
        filas = analisis.brechas(zona_id=q.zona_id)
        series = []
        for nivel in ('ALTA', 'MEDIA', 'BAJA'):
            conteo = {}
            for f in filas:
                if f['nivel'] == nivel:
                    conteo[f['zona']] = conteo.get(f['zona'], 0) + 1
            series.append({'name': f'Brecha {nivel.lower()}', 'data': [conteo.get(n, 0) for n in nombres]})
        return {'grafica': grafica, 'titulo': 'Productos con brecha por zona', 'tipo': 'column', 'categories': nombres,
                'series': series}
    datos = historicos.evolucion_indice(q.zona_id, q.dias)
    fechas = sorted({d['dia'] for d in datos})
    por_zona = {}
    for d in datos:
        por_zona.setdefault(d['zona'], {})[d['dia']] = d['indice_acceso']
    return {'grafica': grafica, 'titulo': 'Evolución del índice de acceso', 'tipo': 'line', 'categories': fechas,
            'series': [{'name': zona, 'data': [valores.get(f) for f in fechas]} for zona, valores in por_zona.items()]}
