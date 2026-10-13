"""
ms-analisis: cobertura territorial, brechas de surtido, índice de acceso y recomendaciones.

Agrupa en un solo servicio los algoritmos que comparten los mismos datos de
entrada (oferta por zona y producto, ventas, proveedores por zona): separarlos
obligaría a repetir esas consultas en varios servicios.

PostgreSQL: lectura de comercios, inventario, movimientos, proveedores, zonas.
Redis: resultados en caché con versión (`analisis:v{n}:*`); cualquier cambio de inventario
o comercio incrementa `analisis:version`.
MongoDB: ejecuciones_analisis (resultado de cada corrida para ver la evolución por zona).
"""
from pathlib import Path
from uuid import UUID

from flask import g

from abasto_api import ErrorApi, Servicio, no_encontrado, prohibido, sobre_lista, tiene, usuario_actual
from abasto_dominio.extensiones import db
from abasto_dominio.modelos import Comercio
from abasto_dominio.servicios import analisis, historicos
from abasto_dominio.servicios.cache import obtener_o_calcular
from abasto_dominio.servicios.parametros import parametro

from esquemas import CONTRATOS_XML, BrechasConsulta, EvolucionConsulta, MapaConsulta, OportunidadesConsulta

srv = Servicio('analisis', 'Análisis territorial',
               'Cobertura por zona, índice de acceso a la canasta básica y ranking de zonas, detección de brechas '
               'de surtido, recomendaciones de surtido por reglas, oportunidades de abasto e historial de ejecuciones.',
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


@srv.ruta('/analisis/recomendaciones/<uuid:comercio_id>', 'GET', resumen='Recomendación de surtido para un comercio',
          etiqueta='Recomendaciones', permisos=['recomendaciones.ver', 'analisis.ver'], raiz_xml='recomendaciones',
         )
def recomendaciones(comercio_id):
    """Se recomienda un producto si el comercio no lo vende, su cobertura en la zona es baja, hay demanda
    (canasta básica o ventas) y algún proveedor lo entrega en la zona (RN-003). Ordenado por puntaje."""
    comercio = db.session.get(Comercio, comercio_id)
    if not comercio or not comercio.activo:
        raise no_encontrado('El comercio')
    if str(comercio.usuario_id) != g.claims['sub'] and not tiene('analisis.ver'):
        raise prohibido('Sólo puedes consultar recomendaciones de tus comercios.')
    if not comercio.zona_id:
        raise ErrorApi(409, 'sin_zona', 'El comercio no tiene zona asignada; captura su ubicación.')
    lista = analisis.recomendaciones(comercio)
    campos = ('producto_id', 'producto', 'canasta_basica', 'motivo', 'cobertura', 'con_disponibilidad',
              'comercios_analizados', 'ventas', 'proveedores', 'precio_mayoreo_min', 'precio_promedio',
              'margen_estimado', 'puntaje')
    return {'comercio_id': str(comercio.id), 'zona': comercio.zona.nombre,
            'umbral_cobertura': parametro('UMBRAL_COBERTURA_RECOMENDACION'),
            'recomendaciones': [{k: r[k] for k in campos} for r in lista]}


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
