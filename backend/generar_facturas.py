"""
Genera 3 facturas PDF realistas chilenas para la demo del hotel.
- factura_verde.pdf   → aprobación automática
- factura_amarilla.pdf → alerta, requiere revisión
- factura_roja.pdf    → bloqueada, escala a gerencia
"""

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
import os

os.makedirs("facturas", exist_ok=True)

# ─── Colores ────────────────────────────────────────────────────────────────
AZUL      = colors.HexColor("#1a3a5c")
GRIS_OSC  = colors.HexColor("#4a4a4a")
GRIS_CLR  = colors.HexColor("#f5f5f5")
VERDE     = colors.HexColor("#2d7a3a")
AMARILLO  = colors.HexColor("#b8860b")
ROJO      = colors.HexColor("#a02020")
LINEA     = colors.HexColor("#cccccc")
BLANCO    = colors.white

# ─── Estilos ─────────────────────────────────────────────────────────────────
def estilos():
    return {
        "hotel":      ParagraphStyle("hotel",      fontName="Helvetica-Bold",  fontSize=20, textColor=AZUL,     spaceAfter=2),
        "rut_hotel":  ParagraphStyle("rut_hotel",  fontName="Helvetica",       fontSize=9,  textColor=GRIS_OSC, spaceAfter=1),
        "titulo":     ParagraphStyle("titulo",     fontName="Helvetica-Bold",  fontSize=14, textColor=BLANCO,   alignment=TA_CENTER),
        "folio":      ParagraphStyle("folio",      fontName="Helvetica-Bold",  fontSize=11, textColor=BLANCO,   alignment=TA_CENTER),
        "label":      ParagraphStyle("label",      fontName="Helvetica-Bold",  fontSize=8,  textColor=GRIS_OSC),
        "value":      ParagraphStyle("value",      fontName="Helvetica",       fontSize=9,  textColor=AZUL),
        "th":         ParagraphStyle("th",         fontName="Helvetica-Bold",  fontSize=8,  textColor=BLANCO,   alignment=TA_CENTER),
        "td":         ParagraphStyle("td",         fontName="Helvetica",       fontSize=8,  textColor=GRIS_OSC),
        "td_r":       ParagraphStyle("td_r",       fontName="Helvetica",       fontSize=8,  textColor=GRIS_OSC, alignment=TA_RIGHT),
        "total_lbl":  ParagraphStyle("total_lbl",  fontName="Helvetica-Bold",  fontSize=9,  textColor=GRIS_OSC, alignment=TA_RIGHT),
        "total_val":  ParagraphStyle("total_val",  fontName="Helvetica-Bold",  fontSize=9,  textColor=AZUL,     alignment=TA_RIGHT),
        "nota":       ParagraphStyle("nota",       fontName="Helvetica",       fontSize=7,  textColor=GRIS_OSC),
        "pie":        ParagraphStyle("pie",        fontName="Helvetica",       fontSize=7,  textColor=GRIS_OSC, alignment=TA_CENTER),
    }

def formatear_clp(n):
    return f"$ {n:,.0f}".replace(",", ".")

def construir_factura(nombre_archivo, color_banda, tipo_doc,
                      folio, fecha_emision, fecha_vencimiento,
                      proveedor, rut_prov, giro_prov, direccion_prov,
                      items, nota_zona=""):
    """Genera una factura chilena completa en PDF."""
    doc = SimpleDocTemplate(
        nombre_archivo, pagesize=A4,
        rightMargin=1.8*cm, leftMargin=1.8*cm,
        topMargin=1.5*cm, bottomMargin=1.5*cm
    )
    e = estilos()
    historia = []

    # ── ENCABEZADO: hotel izquierda | caja folio derecha ────────────────────
    caja_folio = Table([
        [Paragraph(tipo_doc, e["titulo"])],
        [Paragraph(f"N° {folio}", e["folio"])],
        [Paragraph("R.U.T.: 76.543.210-8", ParagraphStyle("rh2", fontName="Helvetica", fontSize=7, textColor=BLANCO, alignment=TA_CENTER))],
    ], colWidths=[5.2*cm])
    caja_folio.setStyle(TableStyle([
        ("BACKGROUND",  (0,0), (-1,-1), color_banda),
        ("TOPPADDING",  (0,0), (-1,-1), 6),
        ("BOTTOMPADDING",(0,0),(-1,-1), 6),
        ("ROWBACKGROUNDS",(0,0),(-1,-1),[color_banda]),
        ("BOX", (0,0),(-1,-1), 0.5, BLANCO),
    ]))

    encabezado = Table([
        [
            Table([
                [Paragraph("Hotel Pacifico Sur", e["hotel"])],
                [Paragraph("Av. del Mar 1840, Viña del Mar", e["rut_hotel"])],
                [Paragraph("R.U.T.: 76.543.210-8 | Giro: Servicios Hoteleros", e["rut_hotel"])],
                [Paragraph("Tel: +56 32 298 4000 | contacto@hotelpacificosur.cl", e["rut_hotel"])],
            ], colWidths=[10*cm]),
            caja_folio
        ]
    ], colWidths=[10.5*cm, 5.2*cm])
    encabezado.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("RIGHTPADDING", (0,0), (0,0), 10),
    ]))
    historia.append(encabezado)
    historia.append(Spacer(1, 0.4*cm))
    historia.append(HRFlowable(width="100%", thickness=0.5, color=LINEA))
    historia.append(Spacer(1, 0.3*cm))

    # ── DATOS PROVEEDOR + FECHAS ─────────────────────────────────────────────
    datos = Table([
        [
            Table([
                [Paragraph("PROVEEDOR", e["label"])],
                [Paragraph(proveedor, e["value"])],
                [Paragraph(f"R.U.T.: {rut_prov}", e["label"])],
                [Paragraph(f"Giro: {giro_prov}", e["label"])],
                [Paragraph(f"Dir.: {direccion_prov}", e["label"])],
            ], colWidths=[9*cm]),
            Table([
                [Paragraph("Fecha emisión", e["label"]),  Paragraph(fecha_emision,    e["value"])],
                [Paragraph("Fecha vencimiento", e["label"]), Paragraph(fecha_vencimiento, e["value"])],
                [Paragraph("Condición pago", e["label"]), Paragraph("30 días",         e["value"])],
                [Paragraph("Moneda", e["label"]),         Paragraph("CLP",             e["value"])],
            ], colWidths=[3.5*cm, 3*cm]),
        ]
    ], colWidths=[9.5*cm, 6.5*cm])
    datos.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("BOX", (0,0), (0,0), 0.5, LINEA),
        ("BOX", (1,0), (1,0), 0.5, LINEA),
        ("BACKGROUND", (0,0), (-1,-1), GRIS_CLR),
        ("TOPPADDING", (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("LEFTPADDING", (0,0), (-1,-1), 8),
        ("RIGHTPADDING", (0,0), (-1,-1), 8),
        ("INNERGRID", (1,0),(1,0), 0.3, LINEA),
        ("ROUNDEDCORNERS", [4]),
    ]))
    historia.append(datos)
    historia.append(Spacer(1, 0.4*cm))

    # ── TABLA DE ÍTEMS ───────────────────────────────────────────────────────
    filas = [[
        Paragraph("Cant.", e["th"]),
        Paragraph("Descripción", e["th"]),
        Paragraph("Unidad", e["th"]),
        Paragraph("P. Unitario", e["th"]),
        Paragraph("Total", e["th"]),
    ]]
    subtotal = 0
    for item in items:
        cant, desc, unidad, precio_u = item
        total_item = cant * precio_u
        subtotal += total_item
        filas.append([
            Paragraph(str(cant), e["td_r"]),
            Paragraph(desc, e["td"]),
            Paragraph(unidad, e["td"]),
            Paragraph(formatear_clp(precio_u), e["td_r"]),
            Paragraph(formatear_clp(total_item), e["td_r"]),
        ])

    tabla_items = Table(filas, colWidths=[1.5*cm, 7.5*cm, 2*cm, 2.5*cm, 2.5*cm])
    estilos_tabla = [
        ("BACKGROUND",    (0,0), (-1,0), color_banda),
        ("TEXTCOLOR",     (0,0), (-1,0), BLANCO),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [BLANCO, GRIS_CLR]),
        ("FONTNAME",      (0,0), (-1,-1), "Helvetica"),
        ("FONTSIZE",      (0,0), (-1,-1), 8),
        ("GRID",          (0,0), (-1,-1), 0.3, LINEA),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 6),
        ("RIGHTPADDING",  (0,0), (-1,-1), 6),
        ("ALIGN",         (0,1), (0,-1), "RIGHT"),
        ("ALIGN",         (3,1), (-1,-1), "RIGHT"),
    ]
    tabla_items.setStyle(TableStyle(estilos_tabla))
    historia.append(tabla_items)
    historia.append(Spacer(1, 0.4*cm))

    # ── TOTALES ──────────────────────────────────────────────────────────────
    iva     = round(subtotal * 0.19)
    total   = subtotal + iva

    totales = Table([
        ["", Paragraph("Neto:",        e["total_lbl"]), Paragraph(formatear_clp(subtotal), e["total_val"])],
        ["", Paragraph("IVA (19%):",   e["total_lbl"]), Paragraph(formatear_clp(iva),      e["total_val"])],
        ["", Paragraph("TOTAL:",
            ParagraphStyle("TT", fontName="Helvetica-Bold", fontSize=11, textColor=color_banda, alignment=TA_RIGHT)),
            Paragraph(formatear_clp(total),
            ParagraphStyle("TV", fontName="Helvetica-Bold", fontSize=11, textColor=color_banda, alignment=TA_RIGHT))],
    ], colWidths=[9.5*cm, 4*cm, 2.5*cm])
    totales.setStyle(TableStyle([
        ("LINEABOVE",  (1,2), (-1,2), 1, color_banda),
        ("TOPPADDING", (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
    ]))
    historia.append(totales)
    historia.append(Spacer(1, 0.4*cm))
    historia.append(HRFlowable(width="100%", thickness=0.5, color=LINEA))
    historia.append(Spacer(1, 0.2*cm))

    # ── NOTA DE ZONA (solo para demo) ────────────────────────────────────────
    if nota_zona:
        nota_box = Table([[Paragraph(nota_zona,
            ParagraphStyle("nb", fontName="Helvetica-Oblique", fontSize=7.5,
                           textColor=color_banda))]],
            colWidths=[15.7*cm])
        nota_box.setStyle(TableStyle([
            ("BOX", (0,0),(-1,-1), 0.5, color_banda),
            ("BACKGROUND",(0,0),(-1,-1), colors.HexColor("#f9f9f9")),
            ("TOPPADDING",(0,0),(-1,-1),5),
            ("BOTTOMPADDING",(0,0),(-1,-1),5),
            ("LEFTPADDING",(0,0),(-1,-1),8),
        ]))
        historia.append(nota_box)
        historia.append(Spacer(1, 0.3*cm))

    # ── PIE DE PÁGINA ────────────────────────────────────────────────────────
    historia.append(Paragraph(
        "Documento tributario electrónico — Timbre electrónico SII — Resolución Ex. SII N°80 del 22/08/2014",
        e["pie"]))
    historia.append(Paragraph(
        "Hotel Pacifico Sur SpA | Av. del Mar 1840, Viña del Mar, Valparaíso | www.hotelpacificosur.cl",
        e["pie"]))

    doc.build(historia)
    print(f"  ✓ Generado: {nombre_archivo}")
    return total

# ═══════════════════════════════════════════════════════════════════════════
# FACTURA 1 — ZONA VERDE (aprobación automática)
# ═══════════════════════════════════════════════════════════════════════════
total_verde = construir_factura(
    nombre_archivo="facturas/factura_verde.pdf",
    color_banda=VERDE,
    tipo_doc="FACTURA ELECTRÓNICA",
    folio="000891",
    fecha_emision="15/01/2025",
    fecha_vencimiento="14/02/2025",
    proveedor="Distribuidora López e Hijos Ltda.",
    rut_prov="12.456.789-5",
    giro_prov="Distribución de alimentos y bebidas",
    direccion_prov="Los Carrera 480, Valparaíso",
    items=[
        (24, "Aceite vegetal 5L — bidón",                   "Unid.",  4_850),
        (50, "Harina de trigo especial 25kg — saco",        "Saco",   8_200),
        (36, "Azúcar granulada 1kg — bolsa",                "Bolsa",  1_050),
        (20, "Sal de cocina entrefina 1kg",                 "Bolsa",    480),
        (12, "Salsa de tomate natural 3kg — garrafa",       "Garrafa", 3_600),
    ],
    nota_zona="ZONA VERDE — Proveedor verificado · Importe dentro del histórico · Aprobación y pago automáticos"
)

# ═══════════════════════════════════════════════════════════════════════════
# FACTURA 2 — ZONA AMARILLA (anomalía, requiere 1 clic del responsable)
# ═══════════════════════════════════════════════════════════════════════════
total_amarilla = construir_factura(
    nombre_archivo="facturas/factura_amarilla.pdf",
    color_banda=AMARILLO,
    tipo_doc="FACTURA ELECTRÓNICA",
    folio="001124",
    fecha_emision="15/01/2025",
    fecha_vencimiento="14/02/2025",
    proveedor="Sistemas Técnicos SA",
    rut_prov="76.321.654-K",
    giro_prov="Mantención y reparación de equipos",
    direccion_prov="Av. Argentina 1020, Valparaíso",
    items=[
        (1,  "Revisión completa sistema HVAC — 3 pisos",        "Serv.", 580_000),
        (1,  "Cambio filtros aire acondicionado x12 unidades",  "Serv.", 210_000),
        (1,  "Recarga gas refrigerante R-410A",                 "Serv.", 185_000),
        (1,  "Mantención preventiva calderas — 2 unidades",     "Serv.", 320_000),
        (1,  "Mano de obra especializada — 16 horas",           "Serv.", 155_000),
    ],
    nota_zona="ZONA AMARILLA — Importe 18% sobre histórico del proveedor (media: $1.060.000) · Requiere aprobación del responsable"
)

# ═══════════════════════════════════════════════════════════════════════════
# FACTURA 3 — ZONA ROJA (bloqueada, escala a gerencia)
# ═══════════════════════════════════════════════════════════════════════════
total_roja = construir_factura(
    nombre_archivo="facturas/factura_roja.pdf",
    color_banda=ROJO,
    tipo_doc="FACTURA ELECTRÓNICA",
    folio="000412",
    fecha_emision="15/01/2025",
    fecha_vencimiento="31/01/2025",
    proveedor="Constructora Pacifico Norte SPA",
    rut_prov="77.890.123-4",
    giro_prov="Construcción y remodelación de inmuebles",
    direccion_prov="Av. España 2100, Viña del Mar",
    items=[
        (1, "Remodelación lobby principal — materiales y mano de obra", "Global", 9_800_000),
        (1, "Instalación revestimiento mármol — 180 m2",                "Global", 6_400_000),
        (1, "Sistema iluminación LED empotrada — 240 puntos",           "Global", 3_200_000),
        (1, "Pintura y estucos interiores — 600 m2",                    "Global", 2_800_000),
        (1, "Gastos generales y administración de obra",                "Global", 1_600_000),
    ],
    nota_zona="ZONA ROJA — BLOQUEADO: Proveedor no registrado en lista blanca · Importe sobre umbral $10.000.000 · Sin OC vinculada · Expediente enviado a gerencia"
)

print(f"\n{'='*55}")
print(f"  Facturas generadas en carpeta /facturas/")
print(f"  Verde:    {formatear_clp(total_verde)} CLP")
print(f"  Amarilla: {formatear_clp(total_amarilla)} CLP")
print(f"  Roja:     {formatear_clp(total_roja)} CLP")
print(f"{'='*55}")
