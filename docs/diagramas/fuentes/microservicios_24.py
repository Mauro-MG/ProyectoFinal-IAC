"""
Genera docs/diagramas/fuentes/microservicios_24.svg a partir del registro de servicios (24 microservicios).
Para obtener el PNG se abre el SVG en un navegador sin ventana:

    python docs/diagramas/fuentes/microservicios_24.py
    msedge --headless=new --window-size=1600,1180 --screenshot=docs/diagramas/microservicios_24.png \
        file:///<ruta>/docs/diagramas/fuentes/microservicios_24.svg
"""
from html import escape
from pathlib import Path

from abasto_dominio.registro_servicios import SERVICIOS

GRUPOS = [
    ('Identidad y control', '#1d4ed8', '#eff6ff', ['seguridad', 'auditoria', 'configuracion', 'monitoreo']),
    ('Comercio', '#15803d', '#ecfdf5', ['comercios', 'catalogo', 'inventario', 'precios', 'ventas', 'disponibilidad']),
    ('Abasto', '#a16207', '#fefce8', ['proveedores', 'abastecimiento', 'pedidos', 'entregas']),
    ('Análisis', '#7c3aed', '#f5f3ff', ['analisis', 'demanda', 'recomendaciones', 'geolocalizacion', 'busqueda',
                                        'reportes']),
    ('Integración y archivos', '#be123c', '#fff1f2', ['sincronizacion', 'integraciones', 'documentos',
                                                       'notificaciones']),
]
assert sorted(s for g in GRUPOS for s in g[3]) == sorted(SERVICIOS), 'el diagrama debe tener los 24 servicios'

ANCHO, ALTO = 1600, 1180


def partir(texto, largo=34):
    lineas, actual = [], ''
    for palabra in texto.split():
        if len(actual) + len(palabra) + 1 > largo:
            lineas.append(actual)
            actual = palabra
        else:
            actual = f'{actual} {palabra}'.strip()
    return lineas + [actual]


def caja(x, y, w, h, titulo, sub, borde='#64748b', fondo='#fff'):
    partes = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{fondo}" stroke="{borde}" stroke-width="2"/>',
              f'<text x="{x + w / 2}" y="{y + 28}" text-anchor="middle" font-size="18" font-weight="700" fill="#0f172a">{escape(titulo)}</text>']
    for i, linea in enumerate(sub):
        partes.append(f'<text x="{x + w / 2}" y="{y + 50 + i * 18}" text-anchor="middle" font-size="13" fill="#475569">{escape(linea)}</text>')
    return '\n'.join(partes)


s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{ANCHO}" height="{ALTO}" viewBox="0 0 {ANCHO} {ALTO}" '
     'font-family="Segoe UI, Helvetica, Arial, sans-serif">',
     '<defs><marker id="f" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto">'
     '<path d="M0,0 L10,5 L0,10 z" fill="#475569"/></marker></defs>',
     f'<rect width="{ANCHO}" height="{ALTO}" fill="#fff"/>',
     f'<text x="{ANCHO / 2}" y="42" text-anchor="middle" font-size="28" font-weight="700" fill="#0f172a">'
     'AbastoRed: 24 microservicios con propiedad de datos</text>',
     f'<text x="{ANCHO / 2}" y="68" text-anchor="middle" font-size="15" fill="#475569">Cada servicio es dueño de sus '
     'tablas y colecciones, entra a PostgreSQL con su propio usuario y expone JSON y XML validado con XSD</text>']
# Clientes y gateway
for i, (t, sub) in enumerate([('Navegador', 'web (lectura + escritura por APIs)'), ('App Android', 'JSON · sin conexión + lotes'),
                              ('App de escritorio', 'XML validado con XSD'), ('Postman / Swagger', 'contratos y pruebas')]):
    s.append(caja(100 + i * 360, 95, 320, 66, t, [sub]))
s.append(caja(520, 200, 560, 66, 'Gateway nginx (HTTPS)', ['TLS · límite por IP · /ms/<servicio>/api/v1/...'], '#0f172a', '#f1f5f9'))
for i in range(4):
    s.append(f'<path d="M{260 + i * 360},161 L{700 + i * 67},200" stroke="#475569" stroke-width="2" fill="none" marker-end="url(#f)"/>')
s.append('<path d="M800,266 L800,300" stroke="#475569" stroke-width="2" fill="none" marker-end="url(#f)"/>')

# Grupos de servicios
x = 30
anchos = [290, 300, 290, 300, 300]
for (nombre, color, fondo, servicios), w in zip(GRUPOS, anchos):
    alto_grupo = 56 + len(servicios) * 100
    s.append(f'<rect x="{x}" y="305" width="{w}" height="{alto_grupo}" rx="12" fill="{fondo}" stroke="{color}" stroke-width="2"/>')
    s.append(f'<text x="{x + w / 2}" y="333" text-anchor="middle" font-size="17" font-weight="700" fill="{color}">{escape(nombre)}</text>')
    for j, servicio in enumerate(servicios):
        puerto, desc = SERVICIOS[servicio]
        lineas = partir(desc, 38)
        if len(lineas) > 2:
            lineas = [lineas[0], lineas[1].rstrip(',') + '…']
        s.append(caja(x + 12, 350 + j * 100, w - 24, 88, f'ms-{servicio} · {puerto}', lineas, color, '#fff'))
    x += w + 10

# Datos
y = 1040
for i, (t, sub, borde, fondo) in enumerate([
        ('PostgreSQL 16 + PostGIS', 'negocio · un rol por servicio', '#a16207', '#fef9c3'),
        ('MongoDB 7', 'auditoría, avisos, metadatos, salud', '#a16207', '#fef9c3'),
        ('Redis 7', 'sesiones JWT, caché, límites', '#a16207', '#fef9c3'),
        ('Cloud Storage', 'archivos privados · URL firmadas', '#1d4ed8', '#eff6ff')]):
    s.append(caja(70 + i * 375, y, 335, 76, t, [sub], borde, fondo))
s.append(f'<text x="{ANCHO / 2}" y="1020" text-anchor="middle" font-size="14" fill="#475569">Red «datos» interna: '
         'solo los servicios llegan a las bases; el web entra a PostgreSQL con un usuario de solo lectura</text>')
s.append(f'<text x="{ANCHO / 2}" y="1150" text-anchor="middle" font-size="13" fill="#64748b">Generado de '
         'abasto_dominio.registro_servicios · docs/diagramas/fuentes/microservicios_24.py</text>')
s.append('</svg>')

destino = Path(__file__).with_name('microservicios_24.svg')
destino.write_text('\n'.join(s), encoding='utf-8')
print(destino)
