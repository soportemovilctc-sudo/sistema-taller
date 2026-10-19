"""PDF de una Solicitud de Compra (SC-000001), con el formato de la orden de
compra para el proveedor: encabezado del negocio, proveedor, productos con
cantidad y costo, total en letras y resumen de impuestos."""
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO
from xml.sax.saxutils import escape

from app.utils.calculations import to_decimal
from app.utils.turnos_caja import a_hora_local

CENT = Decimal("0.01")
_UNIDADES = ["", "UNO", "DOS", "TRES", "CUATRO", "CINCO", "SEIS", "SIETE", "OCHO", "NUEVE", "DIEZ", "ONCE", "DOCE",
             "TRECE", "CATORCE", "QUINCE", "DIECISÉIS", "DIECISIETE", "DIECIOCHO", "DIECINUEVE", "VEINTE", "VEINTIUNO",
             "VEINTIDÓS", "VEINTITRÉS", "VEINTICUATRO", "VEINTICINCO", "VEINTISÉIS", "VEINTISIETE", "VEINTIOCHO", "VEINTINUEVE"]
_DECENAS = ["", "", "", "TREINTA", "CUARENTA", "CINCUENTA", "SESENTA", "SETENTA", "OCHENTA", "NOVENTA"]
_CENTENAS = ["", "CIENTO", "DOSCIENTOS", "TRESCIENTOS", "CUATROCIENTOS", "QUINIENTOS", "SEISCIENTOS", "SETECIENTOS",
             "OCHOCIENTOS", "NOVECIENTOS"]


def _menor_mil(n: int) -> str:
    if n == 0:
        return ""
    if n == 100:
        return "CIEN"
    c, r = divmod(n, 100)
    partes = [_CENTENAS[c]] if c else []
    if r < 30:
        if r:
            partes.append(_UNIDADES[r])
    else:
        d, u = divmod(r, 10)
        partes.append(_DECENAS[d] + (f" Y {_UNIDADES[u]}" if u else ""))
    return " ".join(partes)


def numero_a_letras(n: int) -> str:
    if n == 0:
        return "CERO"
    millones, resto = divmod(n, 1_000_000)
    miles, unidades = divmod(resto, 1000)
    partes = []
    if millones:
        partes.append("UN MILLÓN" if millones == 1 else f"{numero_a_letras(millones)} MILLONES")
    if miles:
        partes.append("MIL" if miles == 1 else f"{_menor_mil(miles)} MIL")
    if unidades:
        partes.append(_menor_mil(unidades))
    texto = " ".join(partes)
    return texto.replace("VEINTIUNO MIL", "VEINTIÚN MIL").replace(" UNO MIL", " UN MIL")


def monto_en_letras(monto) -> str:
    v = to_decimal(monto or 0).quantize(CENT, rounding=ROUND_HALF_UP)
    entero = int(v)
    centavos = int((v - entero) * 100)
    palabras = numero_a_letras(entero)
    if palabras.endswith("UNO"):
        palabras = palabras[:-3] + "UN"
    if entero >= 1_000_000 and entero % 1_000_000 == 0:
        palabras += " DE"
    texto = f"{palabras} {'LEMPIRA' if entero == 1 else 'LEMPIRAS'}"
    return texto + (f" CON {centavos:02d}/100" if centavos else "") + "."


def totales(sol, con_isv: bool, tasa) -> dict:
    subtotal = sum((to_decimal(d.costo_unitario or 0) * d.cantidad for d in sol.detalles), Decimal("0")).quantize(CENT)
    tasa = to_decimal(tasa or 0)
    isv = (subtotal * tasa / 100).quantize(CENT, rounding=ROUND_HALF_UP) if con_isv else Decimal("0.00")
    return {"subtotal": subtotal, "gravadas": subtotal if con_isv else Decimal("0.00"),
            "exentas": Decimal("0.00") if con_isv else subtotal, "isv": isv, "tasa": tasa if con_isv else Decimal("0"),
            "total": subtotal + isv}


def pdf_solicitud(sol, cfg, cfg_fact, con_isv: bool = True) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import cm
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image

    base = getSampleStyleSheet()
    gris = colors.HexColor("#475569")
    linea = colors.HexColor("#cbd5e1")
    st = {
        "nombre": ParagraphStyle("n", parent=base["Normal"], fontSize=17, leading=20, alignment=1, textColor=colors.HexColor("#334155")),
        "info": ParagraphStyle("i", parent=base["Normal"], fontSize=8.5, leading=10.5, alignment=1, textColor=gris),
        "barra": ParagraphStyle("b", parent=base["Normal"], fontSize=9.5, fontName="Helvetica-Bold"),
        "txt": ParagraphStyle("t", parent=base["Normal"], fontSize=9, leading=11, textColor=gris),
        "celda": ParagraphStyle("c", parent=base["Normal"], fontSize=8.6, leading=10.5),
        "celda_r": ParagraphStyle("cr", parent=base["Normal"], fontSize=8.6, leading=10.5, alignment=2),
    }
    moneda = (cfg.moneda if cfg else None) or "L"
    nombre = (cfg_fact.razon_social if cfg_fact and cfg_fact.razon_social else None) or (cfg.nombre_taller if cfg else "Mi Taller")
    if cfg_fact and cfg_fact.nombre_comercial and cfg_fact.nombre_comercial.lower() not in nombre.lower():
        nombre = f'{nombre} "{cfg_fact.nombre_comercial}"'
    lineas_info = []
    tels = " / ".join(x for x in ((cfg.telefono if cfg else ""), (cfg.whatsapp if cfg else "")) if x)
    if tels or (cfg and cfg.correo):
        lineas_info.append("Tels: " + (tels or "") + (f" · Email: {cfg.correo}" if cfg and cfg.correo else ""))
    if cfg_fact and cfg_fact.rtn_taller:
        lineas_info.append(f"R.T.N. {cfg_fact.rtn_taller}")
    direccion = (cfg_fact.domicilio_fiscal if cfg_fact and cfg_fact.domicilio_fiscal else None) or (cfg.direccion if cfg else "")
    if direccion:
        lineas_info.append(f"Dirección: {direccion}")

    logo = ""
    if cfg and cfg.logo_data:
        try:
            logo = Image(BytesIO(cfg.logo_data), width=4.2 * cm, height=2.4 * cm, kind="proportional")
        except Exception:  # noqa: BLE001
            logo = ""
    ancho = 18.6 * cm
    encabezado = Table([[logo, [Paragraph(escape(nombre), st["nombre"]), Spacer(1, 4)]
                         + [Paragraph(escape(x), st["info"]) for x in lineas_info]]],
                       colWidths=[4.8 * cm, ancho - 4.8 * cm])
    encabezado.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("BOX", (0, 0), (-1, -1), 0.6, linea),
                                    ("TOPPADDING", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 10)]))

    fecha = a_hora_local(sol.fecha)
    barra = Table([[Paragraph(f"Solicitud de Compra: {escape(sol.numero)}", st["barra"]),
                    Paragraph(f"Fecha Emisión: {fecha.strftime('%d-%m-%Y %H:%M:%S')}", st["barra"])]], colWidths=[ancho / 2, ancho / 2])
    barra.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f1f5f9")), ("BOX", (0, 0), (-1, -1), 0.6, linea)]))
    prov = Table([[Paragraph(f"Proveedor: <b>{escape(sol.proveedor or '—')}</b>", st["txt"]),
                   Paragraph(f"Solicitado por: {escape(sol.usuario_nombre or '')}", st["txt"])]], colWidths=[ancho * 0.62, ancho * 0.38])
    prov.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.6, linea), ("TOPPADDING", (0, 0), (-1, -1), 6)]))

    filas = [["Cant.", "Descripción", "Costo", "Descuentos y\nRebajas Otorgados", "Total"]]
    for d in sol.detalles:
        p = d.producto
        codigo = escape(p.codigo) if p else ""
        desc = escape(p.nombre) if p else "(producto eliminado)"
        costo = to_decimal(d.costo_unitario or 0)
        filas.append([f"{d.cantidad:.4f}", Paragraph(f"{codigo} <b>{desc}</b>", st["celda"]), f"{costo:,.2f}", "0.00",
                      f"{(costo * d.cantidad).quantize(CENT):,.2f}"])
    tabla = Table(filas, colWidths=[1.6 * cm, 9.2 * cm, 2.4 * cm, 3.0 * cm, 2.4 * cm], repeatRows=1)
    tabla.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 8.6), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("TEXTCOLOR", (0, 0), (-1, 0), gris),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, linea), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"), ("ALIGN", (0, 0), (0, 0), "CENTER"),
    ]))

    t = totales(sol, con_isv, cfg_fact.isv_tasa if cfg_fact else 15)
    resumen = [
        ("SUB TOTAL " + moneda + ".", t["subtotal"]), ("COMPRAS EXONERADAS " + moneda + ".", Decimal("0")),
        ("COMPRAS EXENTAS " + moneda + ".", t["exentas"]), ("COMPRAS GRAVADAS " + moneda + ".", t["gravadas"]),
        ("DESCUENTOS Y REBAJAS OTORGADOS " + moneda + ".", Decimal("0")),
        (f"IMPUESTOS {t['tasa']:.0f}%", t["isv"]), ("TOTAL " + moneda + ".", t["total"]),
    ]
    der = Table([[Paragraph(escape(e), st["celda"]), Paragraph(f"{v:,.2f}", st["celda_r"])] for e, v in resumen], colWidths=[4.8 * cm, 3.0 * cm])
    der.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, linea), ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                             ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#f1f5f9"))]))
    obs = escape(sol.notas.strip()) if sol.notas and sol.notas.strip() else "Solicitud de Compra"
    izq = [Paragraph(escape(monto_en_letras(t["total"])), st["celda"]), Spacer(1, 40),
           Paragraph("<b>Observaciones</b>", st["celda"]), Paragraph(obs, st["celda"])]
    pie = Table([[izq, der]], colWidths=[ancho - 7.8 * cm, 7.8 * cm])
    pie.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOX", (0, 0), (-1, -1), 0.6, linea),
                             ("LEFTPADDING", (1, 0), (1, 0), 0), ("RIGHTPADDING", (1, 0), (1, 0), 0),
                             ("TOPPADDING", (1, 0), (1, 0), 0), ("BOTTOMPADDING", (1, 0), (1, 0), 0)]))

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=1.2 * cm, bottomMargin=1.2 * cm, leftMargin=1.5 * cm,
                            rightMargin=1.5 * cm, title=f"Solicitud de compra {sol.numero}")
    altura_productos = 13 * cm  # espacio para los productos, como el formato original
    filas_h = 0.5 * cm * len(filas)
    story = [encabezado, Spacer(1, 4), barra, prov, Spacer(1, 4), tabla,
             Spacer(1, max(0.4 * cm, altura_productos - filas_h)), pie]
    doc.build(story)
    return buffer.getvalue()
