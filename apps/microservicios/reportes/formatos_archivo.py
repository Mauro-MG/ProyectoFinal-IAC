"""PDF (reportlab), Excel (openpyxl), CSV y JSON a partir de (título, columnas, filas, resumen)."""
import csv
import io
import json
from datetime import date, datetime
from decimal import Decimal

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

TIPOS_MIME = {'pdf': 'application/pdf', 'csv': 'text/csv',
              'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'json': 'application/json'}


def _valor(v):
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, datetime):
        return v.strftime('%Y-%m-%d %H:%M')
    if isinstance(v, date):
        return v.isoformat()
    return v


def a_csv(titulo, columnas, filas, resumen):
    salida = io.StringIO()
    escritor = csv.writer(salida)
    escritor.writerow([c[1] for c in columnas])
    for f in filas:
        escritor.writerow(['' if f.get(c[0]) is None else _valor(f.get(c[0])) for c in columnas])
    return ('﻿' + salida.getvalue()).encode('utf-8')   # BOM: Excel abre bien los acentos


def a_json(titulo, columnas, filas, resumen):
    return json.dumps({'titulo': titulo, 'resumen': resumen, 'columnas': [c[0] for c in columnas],
                       'filas': [{c[0]: _valor(f.get(c[0])) for c in columnas} for f in filas]},
                      ensure_ascii=False, indent=2).encode('utf-8')


def a_xlsx(titulo, columnas, filas, resumen):
    libro = Workbook()
    hoja = libro.active
    hoja.title = 'Reporte'
    hoja['A1'] = titulo
    hoja['A1'].font = Font(size=14, bold=True)
    hoja['A2'] = f'Generado el {datetime.now():%d/%m/%Y %H:%M} · AbastoRed'
    renglon = 4
    for i, (_, encabezado) in enumerate(columnas, start=1):
        celda = hoja.cell(row=renglon, column=i, value=encabezado)
        celda.font = Font(bold=True, color='FFFFFF')
        celda.fill = PatternFill('solid', fgColor='237A4B')
        celda.alignment = Alignment(horizontal='center')
    for f in filas:
        renglon += 1
        for i, (clave, _) in enumerate(columnas, start=1):
            hoja.cell(row=renglon, column=i, value=_valor(f.get(clave)))
    for i, (clave, encabezado) in enumerate(columnas, start=1):
        largo = max([len(str(encabezado))] + [len(str(_valor(f.get(clave)) or '')) for f in filas[:200]])
        hoja.column_dimensions[get_column_letter(i)].width = min(max(largo + 2, 10), 45)
    hoja.freeze_panes = 'A5'
    resumen_hoja = libro.create_sheet('Resumen')
    for i, (clave, valor) in enumerate(resumen.items(), start=1):
        resumen_hoja.cell(row=i, column=1, value=clave).font = Font(bold=True)
        resumen_hoja.cell(row=i, column=2, value=_valor(valor))
    resumen_hoja.column_dimensions['A'].width = 28
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


def a_pdf(titulo, columnas, filas, resumen):
    salida = io.BytesIO()
    horizontal = len(columnas) > 6
    documento = SimpleDocTemplate(salida, pagesize=landscape(letter) if horizontal else letter, title=titulo,
                                  author='AbastoRed', leftMargin=1.2 * cm, rightMargin=1.2 * cm, topMargin=1.2 * cm,
                                  bottomMargin=1.2 * cm)
    estilos = getSampleStyleSheet()
    celda = estilos['BodyText'].clone('celda', fontSize=7.5, leading=9)
    elementos = [Paragraph(titulo, estilos['Title']),
                 Paragraph(f'Generado el {datetime.now():%d/%m/%Y %H:%M} · AbastoRed', estilos['Normal']),
                 Spacer(1, 8),
                 Paragraph(' · '.join(f'<b>{k}:</b> {_valor(v)}' for k, v in resumen.items()), estilos['Normal']),
                 Spacer(1, 10)]
    datos = [[Paragraph(f'<b>{c[1]}</b>', celda) for c in columnas]]
    for f in filas[:3000]:
        datos.append([Paragraph('' if f.get(c[0]) is None else str(_valor(f.get(c[0]))), celda) for c in columnas])
    tabla = Table(datos, repeatRows=1)
    tabla.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#237A4B')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F2F5F3')]),
        ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#C9D1CC')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    elementos.append(tabla)
    if len(filas) > 3000:
        elementos.append(Paragraph(f'Se muestran 3000 de {len(filas)} renglones; usa CSV o Excel para verlos todos.',
                                   estilos['Italic']))
    documento.build(elementos)
    return salida.getvalue()


GENERADORES = {'pdf': a_pdf, 'csv': a_csv, 'xlsx': a_xlsx, 'json': a_json}
