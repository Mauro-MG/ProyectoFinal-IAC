"""Genera los diagramas de la entrega final como SVG y los convierte a PNG con Edge headless."""
import html
import subprocess
import sys
from pathlib import Path

SALIDA = Path(sys.argv[1])
SALIDA.mkdir(parents=True, exist_ok=True)
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

VERDE = '#1E5B3E'
VERDE_CLARO = '#E7F0EA'
VERDE_MEDIO = '#3C7A5A'
TINTA = '#1F2933'
GRIS = '#5B6570'
LINEA = '#8A939C'
FONDO = '#F5F6F5'
ARENA = '#F4EBD8'
ARENA_BORDE = '#9A7322'
AZUL_CLARO = '#E8EEF6'
AZUL_BORDE = '#3D5A80'

FUENTE = "Segoe UI, Arial, sans-serif"


def esc(t):
    return html.escape(str(t))


class Svg:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.p = []

    def add(self, s):
        self.p.append(s)

    def rect(self, x, y, w, h, fill='#fff', stroke=LINEA, sw=1.5, r=8, dash=None):
        d = f' stroke-dasharray="{dash}"' if dash else ''
        self.add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d}/>')

    def text(self, x, y, t, size=16, weight=400, color=TINTA, anchor='start', italic=False):
        st = ' font-style="italic"' if italic else ''
        self.add(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{color}" text-anchor="{anchor}"{st}>{esc(t)}</text>')

    def line(self, x1, y1, x2, y2, color=LINEA, sw=1.6, arrow=True, dash=None):
        m = ' marker-end="url(#f)"' if arrow else ''
        d = f' stroke-dasharray="{dash}"' if dash else ''
        self.add(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{sw}"{m}{d}/>')

    def path(self, d, color=LINEA, sw=1.6, arrow=True, dash=None):
        m = ' marker-end="url(#f)"' if arrow else ''
        da = f' stroke-dasharray="{dash}"' if dash else ''
        self.add(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{sw}"{m}{da}/>')

    def caja(self, x, y, w, h, titulo, lineas=(), fill='#fff', stroke=LINEA, tsize=17, lsize=13.5, tcolor=TINTA):
        self.rect(x, y, w, h, fill, stroke)
        self.text(x + w / 2, y + 28, titulo, tsize, 600, tcolor, 'middle')
        for i, l in enumerate(lineas):
            self.text(x + w / 2, y + 50 + i * 19, l, lsize, 400, GRIS, 'middle')

    def svg(self):
        cab = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" viewBox="0 0 {self.w} {self.h}" '
               f'font-family="{FUENTE}"><defs><marker id="f" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
               f'markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="#5B6570"/></marker></defs>'
               f'<rect width="100%" height="100%" fill="#ffffff"/>')
        return cab + ''.join(self.p) + '</svg>'


def guardar(nombre, s):
    ruta_svg = SALIDA / f'{nombre}.svg'
    ruta_svg.write_text(s.svg(), encoding='utf-8')
    png = SALIDA / f'{nombre}.png'
    subprocess.run([EDGE, '--headless=new', '--disable-gpu', '--hide-scrollbars', '--force-device-scale-factor=2',
                    f'--screenshot={png}', f'--window-size={s.w},{s.h}', ruta_svg.resolve().as_uri()],
                   check=True, capture_output=True, timeout=60)
    print('ok', png)


# ---------------------------------------------------------------- 1. arquitectura general
def arquitectura():
    s = Svg(1600, 1010)
    s.text(800, 44, 'AbastoRed: arquitectura general', 28, 700, TINTA, 'middle')
    s.text(800, 72, 'Una sola entrada HTTPS · 24 servicios dueños de sus datos · dos bibliotecas compartidas', 16, 400, GRIS, 'middle')
    clientes = [('Navegador', 'web por rol + sitio público'), ('App Android', 'Kotlin · solo JSON · sin conexión'),
                ('App de escritorio', 'PySide6 · solo XML con XSD'), ('Postman / Swagger', 'contratos y pruebas')]
    for i, (t, d) in enumerate(clientes):
        x = 120 + i * 350
        s.caja(x, 100, 310, 70, t, [d])
        s.line(x + 155, 170, 800, 222)
    s.rect(470, 225, 660, 74, VERDE_CLARO, VERDE, 2)
    s.text(800, 256, 'Gateway nginx (HTTPS 443)', 19, 700, VERDE, 'middle')
    s.text(800, 280, 'TLS 1.2/1.3 · 30 peticiones/s por IP · /  → web · /ms/<servicio>/ → microservicio', 14, 400, GRIS, 'middle')
    # web
    s.line(640, 299, 230, 350)
    s.line(800, 299, 800, 350)
    s.caja(60, 352, 340, 128, 'abastored-web', ['Flask · plantillas + Highcharts', 'lee PostgreSQL con usuario', 'de solo lectura', 'escribe solo por las APIs'],
           fill='#fff', stroke=VERDE_MEDIO)
    s.line(400, 416, 455, 416)
    # microservicios
    s.rect(458, 340, 1082, 400, FONDO, LINEA, 1.5, 10, '6 4')
    s.text(475, 366, '24 microservicios (Flask + gunicorn, un contenedor cada uno, /api/v1, JSON o XML según Accept)', 15, 600, TINTA)
    grupos = [
        ('Identidad y control', ['seguridad', 'auditoria', 'configuracion', 'monitoreo']),
        ('Comercio', ['comercios', 'catalogo', 'inventario', 'precios', 'ventas', 'disponibilidad']),
        ('Abasto', ['proveedores', 'abastecimiento', 'pedidos', 'entregas']),
        ('Análisis', ['analisis', 'demanda', 'recomendaciones', 'geolocalizacion', 'busqueda', 'reportes']),
        ('Integración y archivos', ['sincronizacion', 'integraciones', 'documentos', 'notificaciones']),
    ]
    for i, (g, srv) in enumerate(grupos):
        x = 475 + i * 211
        s.rect(x, 382, 200, 340, '#fff', LINEA, 1.2, 8)
        s.text(x + 100, 408, g, 15, 700, VERDE, 'middle')
        for j, n in enumerate(srv):
            s.rect(x + 14, 424 + j * 48, 172, 38, VERDE_CLARO, VERDE_CLARO, 1, 6)
            s.text(x + 100, 449 + j * 48, f'ms-{n}', 14.5, 500, TINTA, 'middle')
    # librerias
    s.rect(60, 520, 340, 200, '#fff', LINEA, 1.5, 8)
    s.text(230, 548, 'Bibliotecas compartidas (libs/)', 16, 700, TINTA, 'middle')
    s.text(80, 580, 'abasto_api', 15, 700, VERDE)
    for k, l in enumerate(['rutas, JWT y permisos, Pydantic,', 'JSON/XML + XSD, errores uniformes,', 'límite por usuario, X-Correlation-ID,', '/health/*, OpenAPI y Swagger']):
        s.text(80, 601 + k * 18, l, 13, 400, GRIS)
    s.text(80, 684, 'abasto_dominio', 15, 700, VERDE)
    s.text(80, 704, 'modelos SQLAlchemy, reglas, auditoría', 13, 400, GRIS)
    s.line(400, 620, 455, 620, dash='5 4')
    # datos
    s.text(800, 790, 'red «datos» de Docker: interna, sin puertos publicados', 15, 600, ARENA_BORDE, 'middle')
    datos = [('PostgreSQL 16 + PostGIS', ['43 tablas de negocio', 'un usuario por servicio']),
             ('MongoDB 7', ['auditoría, avisos, bitácora', 'metadatos de archivos, historial']),
             ('Redis 7', ['sesiones JWT, revocación', 'caché, límites, bloqueos'])]
    for i, (t, l) in enumerate(datos):
        x = 60 + i * 370
        s.caja(x, 810, 340, 110, t, l, ARENA, ARENA_BORDE)
        s.line(800, 740, x + 170, 808)
    s.caja(1180, 810, 360, 110, 'Google Cloud Storage', ['bucket privado: fotos, CSV, PDF,', 'respaldos · URL firmadas V4'], AZUL_CLARO, AZUL_BORDE)
    s.line(1300, 740, 1360, 808)
    s.path('M60,440 H32 V865 H56', VERDE_MEDIO, 1.4, True, '5 4')
    s.text(36, 800, 'SELECT', 12, 600, VERDE_MEDIO)
    s.text(800, 975, 'En local, Cloud Storage se sustituye por un emulador; en Google Cloud se usa el bucket real.', 14, 400, GRIS, 'middle', True)
    guardar('arquitectura_general', s)


# ---------------------------------------------------------------- 2. modelo relacional en 3 vistas
def tabla(s, x, y, nombre, columnas, color=VERDE, w=300):
    h = 40 + 21 * len(columnas) + 10
    s.rect(x, y, w, h, '#fff', color, 1.8, 6)
    s.add(f'<path d="M{x},{y + 6} a6,6 0 0 1 6,-6 h{w - 12} a6,6 0 0 1 6,6 v28 h-{w} z" fill="{color}"/>')
    s.text(x + 14, y + 23, nombre, 15.5, 700, '#ffffff')
    for i, c in enumerate(columnas):
        peso, col = 400, TINTA
        if c.startswith('PK'):
            peso = 700
        elif c.startswith('FK'):
            col = GRIS
        s.text(x + 14, y + 56 + i * 21, c, 13.5, peso, col)
    return (x, y, w, h)


def er_comercio():
    s = Svg(1600, 980)
    s.text(800, 42, 'Modelo relacional · vista 1: identidad, comercio, catálogo e inventario', 24, 700, TINTA, 'middle')
    s.text(800, 68, 'Tablas principales de PostgreSQL. Cada línea es una llave foránea; se omiten created_at/updated_at y columnas descriptivas.', 14, 400, GRIS, 'middle')
    A = '#3D5A80'
    roles = tabla(s, 50, 100, 'roles', ['PK id', 'nombre (único)', 'permisos jsonb'], A, 270)
    usuarios = tabla(s, 50, 260, 'usuarios', ['PK id uuid', 'email (único)', 'password_hash (bcrypt)', 'FK rol_id', 'activo, ultimo_acceso'], A, 270)
    zonas = tabla(s, 50, 520, 'zonas_municipales', ['PK id', 'municipio, población', 'centro lat/lon, radio_km', 'área PostGIS (geom)'], A, 270)
    colonias = tabla(s, 50, 760, 'colonias', ['PK id', 'municipio, código postal', 'geom (PostGIS)'], A, 270)
    comercios = tabla(s, 420, 250, 'comercios', ['PK id uuid', 'FK usuario_id', 'FK zona_id', 'tipo_comercio (formal/informal)', 'estado_registro', 'latitud, longitud, geom', 'FK verificado_por', 'foto_url'], VERDE, 300)
    resp = tabla(s, 420, 580, 'responsables_comercio', ['PK id', 'FK comercio_id', 'FK usuario_id (opcional)', 'puesto, teléfono'], VERDE, 300)
    cat = tabla(s, 1250, 100, 'categorias', ['PK id', 'nombre (único)', 'orden, activa'], A, 300)
    prod = tabla(s, 1250, 250, 'productos_maestros', ['PK id', 'FK categoria_id', 'unidad_medida, codigo_barras', 'es_canasta_basica'], A, 300)
    var = tabla(s, 1250, 450, 'variantes_producto', ['PK id', 'FK producto_id', 'codigo_barras, factor'], A, 300)
    inv = tabla(s, 830, 100, 'inventario_comercio', ['PK id', 'FK comercio_id', 'FK producto_id', 'existencia ≥ 0', 'stock_minimo, stock_maximo', 'precio_venta', 'estado (columna generada)', 'UNIQUE(comercio, producto)'], VERDE, 320)
    mov = tabla(s, 830, 430, 'movimientos_inventario', ['PK id', 'FK inventario_id', 'tipo ENTRADA/SALIDA/AJUSTE', 'existencia anterior / nueva', 'FK pedido_id (nulo)', 'referencia idempotente'], VERDE, 320)
    res = tabla(s, 830, 720, 'reservas_inventario', ['PK id', 'FK inventario_id', 'cantidad, estado, expira_at'], VERDE, 320)
    precios = tabla(s, 1250, 610, 'precios_comercio (historial)', ['PK id', 'FK comercio_id', 'FK producto_id', 'precio, precio_anterior', 'estado_validacion (RN-001)'], '#7A5C1E', 300)
    promo = tabla(s, 1250, 830, 'promociones', ['PK id', 'FK inventario_id', 'precio_promocional, inicio, fin'], '#7A5C1E', 300)
    # relaciones
    s.line(185, 213, 185, 258, LINEA, 1.6, False)
    s.line(320, 330, 418, 330, LINEA, 1.6, False)
    s.path('M320,600 C370,600 370,370 418,370', arrow=False)
    s.line(570, 468, 570, 578, LINEA, 1.6, False)
    s.path('M720,300 C775,300 775,170 828,170', arrow=False)
    s.line(990, 318, 990, 428, LINEA, 1.6, False)
    s.path('M830,200 H800 V770 H828', arrow=False)
    s.line(1248, 320, 1152, 220, LINEA, 1.6, False)
    s.line(1400, 213, 1400, 248, LINEA, 1.6, False)
    s.line(1400, 384, 1400, 448, LINEA, 1.6, False)
    s.path('M1150,260 H1205 V880 H1248', arrow=False)
    s.text(800, 960, 'precios_comercio también referencia comercios y productos_maestros (líneas omitidas para no cruzar tablas). Fuente: db/postgres/01_schema.sql y 04_servicios.sql.', 13, 400, GRIS, 'middle', True)
    guardar('er_1_comercio_inventario', s)


def er_abasto():
    s = Svg(1600, 940)
    s.text(800, 42, 'Modelo relacional · vista 2: proveedores, pedidos de abasto y entregas', 24, 700, TINTA, 'middle')
    s.text(800, 68, 'comercios y productos_maestros aparecen como referencia (vista 1).', 14, 400, GRIS, 'middle')
    M = '#6B4E9B'
    O = '#8A5A12'
    A = '#3D5A80'
    prov = tabla(s, 50, 100, 'proveedores', ['PK id uuid', 'FK usuario_id (único)', 'pedido_minimo', 'tiempo_entrega_dias', 'plan (Básico/Destacado)'], M, 290)
    pz = tabla(s, 50, 360, 'proveedor_zonas', ['PK/FK proveedor_id', 'PK/FK zona_id'], M, 290)
    catp = tabla(s, 50, 520, 'catalogo_proveedor', ['PK id', 'FK proveedor_id', 'FK producto_id', 'precio_mayoreo, cantidad_minima', 'existencia_disponible'], M, 290)
    sal = tabla(s, 50, 760, 'salidas_catalogo', ['PK referencia (pedido:{id})', 'FK proveedor_id, partidas'], M, 290)
    ped = tabla(s, 460, 250, 'pedidos_abasto', ['PK id uuid, folio', 'FK comercio_id', 'FK proveedor_id', 'estado (8 estados)', 'subtotal, comision_plataforma', 'fechas envío / entrega'], O, 320)
    det = tabla(s, 460, 560, 'detalle_pedidos', ['PK id', 'FK pedido_id', 'FK producto_id', 'cantidad, precio_unitario'], O, 320)
    his = tabla(s, 460, 760, 'historial_pedido', ['PK id', 'FK pedido_id, FK usuario_id', 'estado anterior / nuevo'], O, 320)
    ent = tabla(s, 900, 250, 'entregas', ['PK id', 'pedido_id', 'FK proveedor_id, FK comercio_id', 'estado, responsable', 'codigo_confirmacion (QR)', 'evidencia_archivo_id'], O, 320)
    ev = tabla(s, 900, 560, 'eventos_entrega', ['PK id', 'FK entrega_id', 'estado, latitud, longitud'], O, 320)
    inc = tabla(s, 900, 730, 'incidencias_entrega', ['PK id', 'FK entrega_id', 'tipo, estado, resolucion'], O, 320)
    evp = tabla(s, 1300, 520, 'evaluaciones_proveedor', ['PK id', 'FK proveedor_id', 'FK pedido_id', 'calificacion, puntualidad'], M, 260)
    com = tabla(s, 1300, 100, 'comercios (vista 1)', ['PK id uuid', 'FK zona_id'], A, 260)
    pm = tabla(s, 1300, 280, 'productos_maestros', ['PK id'], A, 260)
    s.line(195, 237, 195, 358, LINEA, 1.6, False)
    s.path('M340,140 C380,140 380,560 340,560', arrow=False)
    s.path('M340,180 C400,180 400,320 458,320', arrow=False)
    s.line(620, 432, 620, 558, LINEA, 1.6, False)
    s.path('M780,320 C840,320 840,320 898,320', arrow=False)
    s.path('M460,700 C430,700 430,800 458,800', arrow=False)
    s.line(1060, 432, 1060, 558, LINEA, 1.6, False)
    s.path('M1220,600 C1250,600 1250,690 1220,760', arrow=False)
    s.path('M780,290 C1050,180 1150,140 1298,140', arrow=False, dash='4 3')
    s.path('M780,620 C1000,500 1200,330 1298,320', arrow=False, dash='4 3')
    s.path('M780,350 C1100,450 1200,560 1298,570', arrow=False, dash='4 3')
    s.text(800, 918, 'Estados del pedido: BORRADOR → ENVIADO → ACEPTADO → EN_PREPARACION → ENVIADO_A_COMERCIO → ENTREGADO (o CANCELADO / RECHAZADO).', 13.5, 400, GRIS, 'middle', True)
    guardar('er_2_abasto', s)


def er_ventas():
    s = Svg(1600, 760)
    s.text(800, 42, 'Modelo relacional · vista 3: ventas, devoluciones y abastecimiento consolidado', 24, 700, TINTA, 'middle')
    V = '#1E5B3E'
    C = '#3D5A80'
    tabla(s, 50, 100, 'ventas', ['PK id, folio', 'FK comercio_id, FK usuario_id', 'total, metodo_pago, origen', 'id_cliente (UUID de la app)', 'estado, fecha_venta'], V, 310)
    tabla(s, 50, 360, 'detalle_ventas', ['PK id', 'FK venta_id', 'FK inventario_id, FK producto_id', 'cantidad, precio, cantidad_devuelta'], V, 310)
    tabla(s, 420, 100, 'devoluciones', ['PK id', 'FK venta_id', 'motivo, total'], V, 290)
    tabla(s, 420, 300, 'detalle_devoluciones', ['PK id', 'FK devolucion_id', 'FK detalle_venta_id, cantidad'], V, 290)
    tabla(s, 820, 100, 'solicitudes_cotizacion', ['PK id, folio', 'FK zona_id, FK creada_por', 'consolidada, estado', 'fecha_limite'], C, 320)
    tabla(s, 820, 360, 'necesidades_solicitud', ['PK id', 'FK solicitud_id', 'FK comercio_id, FK producto_id', 'cantidad'], C, 320)
    tabla(s, 1230, 100, 'cotizaciones', ['PK id', 'FK solicitud_id, FK proveedor_id', 'tiempo_entrega, vigencia, estado'], C, 320)
    tabla(s, 1230, 300, 'partidas_cotizacion', ['PK id', 'FK cotizacion_id, FK producto_id', 'precio_unitario, cantidad'], C, 320)
    tabla(s, 1230, 480, 'ordenes_compra', ['PK id, folio', 'FK solicitud_id, FK cotizacion_id', 'FK comercio_id, FK proveedor_id', 'total, estado', 'pedido_id (al convertirse)'], C, 320)
    tabla(s, 820, 580, 'partidas_orden', ['PK id', 'FK orden_id, FK producto_id', 'cantidad, subtotal'], C, 320)
    s.line(205, 255, 205, 358, LINEA, 1.6, False)
    s.line(360, 140, 418, 140, LINEA, 1.6, False)
    s.line(565, 212, 565, 298, LINEA, 1.6, False)
    s.path('M360,420 C390,420 390,380 418,380', arrow=False)
    s.line(980, 233, 980, 358, LINEA, 1.6, False)
    s.line(1140, 140, 1228, 140, LINEA, 1.6, False)
    s.line(1390, 212, 1390, 298, LINEA, 1.6, False)
    s.path('M1140,180 C1190,180 1190,520 1228,520', arrow=False)
    s.path('M1228,640 C1180,640 1180,640 1140,640', arrow=False)
    s.text(800, 735, 'Una orden de compra se convierte en pedido de abasto por la API de ms-pedidos (estado CONVERTIDA + bloqueo en Redis).', 13.5, 400, GRIS, 'middle', True)
    guardar('er_3_ventas_abastecimiento', s)


# ---------------------------------------------------------------- 3. secuencias
def secuencia(nombre, titulo, subtitulo, actores, pasos, alto_paso=54, ancho=1600, notas=()):
    n = len(actores)
    margen = 90
    paso_x = (ancho - 2 * margen) / (n - 1)
    xs = [margen + i * paso_x for i in range(n)]
    alto = 170 + alto_paso * len(pasos) + 60 + 22 * len(notas)
    s = Svg(ancho, alto)
    s.text(ancho / 2, 40, titulo, 24, 700, TINTA, 'middle')
    s.text(ancho / 2, 66, subtitulo, 14, 400, GRIS, 'middle')
    for x, (a, sub, tipo) in zip(xs, actores):
        fill, borde = {'cliente': ('#fff', LINEA), 'ms': (VERDE_CLARO, VERDE), 'dato': (ARENA, ARENA_BORDE), 'gcs': (AZUL_CLARO, AZUL_BORDE)}[tipo]
        s.rect(x - 82, 86, 164, 56, fill, borde, 1.6, 8)
        s.text(x, 110, a, 14.5, 700, TINTA, 'middle')
        s.text(x, 129, sub, 12, 400, GRIS, 'middle')
        s.line(x, 142, x, alto - 50 - 22 * len(notas), '#C4CAD0', 1.4, False, '5 5')
    y = 180
    for p in pasos:
        if p[0] == 'nota':
            s.rect(margen - 60, y - 24, ancho - 2 * margen + 120, 34, '#FAFAF7', '#D9D4C3', 1, 6)
            s.text(ancho / 2, y - 2, p[1], 13.5, 600, ARENA_BORDE, 'middle')
            y += alto_paso
            continue
        a, b, etiqueta = p[0], p[1], p[2]
        num = p[3] if len(p) > 3 else ''
        x1, x2 = xs[a], xs[b]
        if a == b and x1 > ancho * 0.7:
            s.path(f'M{x1},{y - 6} h-40 v18 h36', arrow=True)
            s.text(x1 - 48, y + 8, etiqueta, 13, 400, TINTA, 'end')
        elif a == b:
            s.path(f'M{x1},{y - 6} h40 v18 h-36', arrow=True)
            s.text(x1 + 48, y + 8, etiqueta, 13, 400, TINTA)
        else:
            dash = '6 4' if etiqueta.startswith('←') else None
            s.line(x1, y, x2 + (-4 if x2 > x1 else 4), y, '#4B5563', 1.6, True, dash)
            lab = etiqueta.lstrip('← ')
            s.text((x1 + x2) / 2, y - 8, lab, 13, 400, TINTA, 'middle')
        if num:
            s.add(f'<circle cx="{min(x1, x2) - 22}" cy="{y - 4}" r="11" fill="{VERDE}"/>')
            s.text(min(x1, x2) - 22, y + 1, num, 12, 700, '#fff', 'middle')
        y += alto_paso
    for i, nt in enumerate(notas):
        s.text(margen - 60, alto - 40 - 22 * (len(notas) - 1 - i) + 10, nt, 13, 400, GRIS, 'start', True)
    guardar(nombre, s)


def secuencia_abasto():
    actores = [('Minorista', 'Android · JSON', 'cliente'), ('ms-recomendaciones', '8116', 'ms'), ('ms-proveedores', '8109', 'ms'),
               ('ms-pedidos', '8106', 'ms'), ('ms-notificaciones', '8108', 'ms'), ('Proveedor', 'web · JSON', 'cliente'),
               ('ms-entregas', '8119', 'ms'), ('ms-inventario', '8104', 'ms')]
    pasos = [
        (0, 1, 'GET /recomendaciones/{comercio}', '1'),
        (0, 2, 'GET /ofertas (proveedores que surten su zona)', '2'),
        (0, 3, 'POST /pedidos (borrador con partidas)', '3'),
        (0, 3, 'POST /pedidos/{id}/acciones/enviar', '4'),
        (3, 3, 'valida pedido mínimo (RN-004), zona (RN-011)'),
        (3, 4, 'aviso «Pedido PED-…: enviado» al equipo del proveedor'),
        (5, 3, 'POST /pedidos/{id}/acciones/aceptar', '5'),
        (5, 6, 'POST /entregas (programa la entrega)', '6'),
        (5, 6, 'POST /entregas/{id}/salida', '7'),
        (6, 3, 'preparar + despachar'),
        (3, 2, 'POST /proveedores/{id}/salidas  (ref. pedido:{id})'),
        (0, 6, 'POST /entregas/{id}/confirmacion (escanea QR)', '8'),
        (6, 3, 'recibir'),
        (3, 7, 'POST /comercios/{id}/movimientos/lote  (entradas, ref. pedido:{id})'),
        (7, 0, '← inventario actualizado: Arroz blanco 1 kg 78 → 102'),
        ('nota', 'Cada paso registra su evento de auditoría en la misma transacción y lleva el mismo X-Correlation-ID (GET /trazas/{id} en ms-auditoria).'),
    ]
    secuencia('secuencia_abasto', 'Proceso integral: abasto con entrega por QR',
              'Pasos reales de tests/integracion/test_procesos_completos.py, ejecutados contra GCP el 25/11/2026 (docs/evidencias/procesos/)',
              actores, pasos, 52,
              notas=['Si un paso intermedio falla, el pedido o la entrega no cambian de estado y el reintento usa la misma referencia; el dueño no repite el cambio.'])


def flujo_sesion():
    actores = [('Cliente', 'web, Android, escritorio', 'cliente'), ('ms-seguridad', '8101', 'ms'),
               ('Redis', 'sesiones', 'dato'), ('Otro servicio', 'p. ej. ms-pedidos', 'ms')]
    pasos = [
        (0, 1, 'POST /auth/login (correo, contraseña)', '1'),
        (1, 1, 'bcrypt; 5 fallos en 15 min → cuenta bloqueada'),
        (1, 2, 'SETEX sesion:{jti} 8 h · refresh:{token} 7 días'),
        (1, 0, '← access_token (JWT HS256, 8 h) + refresh_token', ''),
        (0, 3, 'GET /api/v1/pedidos  Authorization: Bearer …', '2'),
        (3, 2, 'firma y vigencia → ¿jwt:revocado:{jti}? → ¿existe sesion:{jti}?'),
        (3, 3, 'permiso del rol en el token (403 si falta)'),
        (3, 0, '← 200 (o 401 / 403 / 429 / 503 si Redis no responde)'),
        (0, 1, 'POST /auth/renovar (refresh de un solo uso)', '3'),
        (1, 2, 'GETDEL refresh:{token}; revoca el acceso anterior; emite par nuevo'),
        (0, 1, 'POST /auth/logout', '4'),
        (1, 2, 'borra sesion:{jti} y su refresh; SETEX jwt:revocado:{jti}'),
        ('nota', 'Cerrar sesión o desactivar al usuario invalida el token en los 24 servicios y en el web a la vez: todos consultan el mismo Redis.'),
    ]
    secuencia('flujo_sesion', 'Autenticación: JWT con sesión verificada en Redis',
              'libs/abasto_dominio/abasto_dominio/sesiones.py y libs/abasto_api/abasto_api/seguridad.py', actores, pasos, 50, 1400)


def flujo_sincronizacion():
    actores = [('App Android', 'Room (SQLite)', 'cliente'), ('ms-sincronizacion', '8113', 'ms'), ('Servicio dueño', 'ventas, inventario, precios', 'ms'),
               ('MongoDB', 'lotes y operaciones', 'dato')]
    pasos = [
        (0, 0, 'sin señal: guarda venta / entrada / precio con UUID y version_base'),
        (0, 0, 'más de 48 h sin enviar → se marca para revisión (RN-005)'),
        (0, 1, 'POST /lotes (operaciones en orden de captura)', '1'),
        (1, 3, 'registra lote; ¿operación ya aplicada (sync:{uuid})?'),
        (1, 2, 'aplica cada operación con el token del usuario', '2'),
        (2, 1, '← aplicada · duplicada (misma respuesta) · 409 conflicto · 503'),
        (1, 3, 'guarda el estado de cada operación'),
        (1, 0, '← resultado por operación: aplicada, conflicto, pendiente_reintento', '3'),
        (0, 0, 'el usuario revisa los conflictos en «Pendientes»'),
    ]
    secuencia('flujo_sincronizacion', 'Sincronización sin conexión (Android)',
              'apps/movil/.../Repositorio.kt y apps/microservicios/sincronizacion/app.py', actores, pasos, 50, 1400,
              notas=['Conflicto de precio: si el servidor cambió el precio después de version_base, la operación no se aplica y queda como conflicto.'])


def despliegue():
    fuente = Path(sys.argv[2]).read_text(encoding='utf-8')
    fuente = fuente.replace('• 182 pruebas de integración contra el despliegue (15 omitidas: requieren Docker local)',
                            '• 185 pruebas de integración aprobadas contra el despliegue (19 omitidas, 0 fallidas)')
    ruta = SALIDA / 'despliegue_gcp_final.svg'
    ruta.write_text(fuente, encoding='utf-8')
    subprocess.run([EDGE, '--headless=new', '--disable-gpu', '--hide-scrollbars', '--force-device-scale-factor=2',
                    f'--screenshot={SALIDA / "despliegue_gcp_final.png"}', '--window-size=1600,1110', ruta.resolve().as_uri()],
                   check=True, capture_output=True, timeout=60)
    print('ok despliegue')


arquitectura()
er_comercio()
er_abasto()
er_ventas()
secuencia_abasto()
flujo_sesion()
flujo_sincronizacion()
despliegue()
