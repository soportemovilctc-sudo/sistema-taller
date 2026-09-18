"""Generación de PDF profesional para una orden de servicio (ReportLab)."""
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_RIGHT

from app.models import parse_condiciones_servicio


def _agregar_condiciones_servicio(story, titulo_style, texto_style, texto_condiciones=""):
    """Agrega, al final del documento, el bloque (editable desde Configuración)
    de condiciones de servicio y retiro de equipos (orden de servicio y
    factura, carta). Si no hay texto configurado, no agrega nada."""
    condiciones = parse_condiciones_servicio(texto_condiciones)
    if not condiciones:
        return
    story.append(Spacer(1, 14))
    story.append(Paragraph("Condiciones de Servicio y Retiro de Equipos", titulo_style))
    story.append(Spacer(1, 3))
    for titulo, texto in condiciones:
        if titulo:
            story.append(Paragraph(f"<b>{titulo}</b> {texto}", texto_style))
        else:
            story.append(Paragraph(texto, texto_style))


def _moneda(valor, simbolo="L"):
    try:
        return f"{simbolo} {float(valor):,.2f}"
    except (TypeError, ValueError):
        return f"{simbolo} 0.00"


def generar_pdf_orden(data: dict) -> bytes:
    """Genera el PDF de una orden de servicio a partir de un diccionario plano.
    Ver app/routers/ordenes.py -> construir_contexto_pdf() para el formato esperado.
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=letter,
        topMargin=1.2 * cm, bottomMargin=1.2 * cm,
        leftMargin=1.4 * cm, rightMargin=1.4 * cm,
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="Sub", fontSize=9, textColor=colors.HexColor("#475569")))
    styles.add(ParagraphStyle(name="Seccion", fontSize=11, fontName="Helvetica-Bold", textColor=colors.white,
                               backColor=colors.HexColor("#1d4ed8"), leftIndent=4, spaceBefore=6, spaceAfter=4,
                               borderPadding=(3, 3, 3, 3)))
    styles.add(ParagraphStyle(name="Celda", fontSize=9, leading=12))
    styles.add(ParagraphStyle(name="CeldaBold", fontSize=9, leading=12, fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle(name="CondTitulo", fontSize=9.5, leading=12, fontName="Helvetica-Bold", textColor=colors.HexColor("#1d4ed8")))
    styles.add(ParagraphStyle(name="CondTexto", fontSize=7.5, leading=10, textColor=colors.HexColor("#475569")))

    taller = data.get("taller", {}) or {}
    moneda = taller.get("moneda", "L")
    story = []

    logo_path = taller.get("logo_path")
    logo_data = taller.get("logo_data")
    logo_cell = ""
    if logo_data:
        try:
            logo_cell = Image(BytesIO(logo_data), width=2.2 * cm, height=2.2 * cm)
        except Exception:
            logo_cell = ""
    elif logo_path:
        try:
            logo_cell = Image(logo_path, width=2.2 * cm, height=2.2 * cm)
        except Exception:
            logo_cell = ""

    info_taller = Paragraph(
        f"<b>{taller.get('nombre', 'Taller de Reparación')}</b><br/>"
        f"{taller.get('direccion', '')}<br/>"
        f"Tel/WhatsApp: {taller.get('telefono', '')} · {taller.get('correo', '')}",
        styles["Sub"],
    )
    orden_info = Paragraph(
        f"<b>ORDEN DE SERVICIO</b><br/>"
        f"N.º <b>{data.get('numero_orden', '')}</b><br/>"
        f"Fecha: {data.get('fecha', '')}<br/>"
        f"Estado: <b>{data.get('estado', '')}</b> &nbsp;|&nbsp; Prioridad: <b>{data.get('prioridad', '')}</b>",
        styles["Sub"],
    )
    tabla_header = Table([[logo_cell, info_taller, orden_info]], colWidths=[2.6 * cm, 9.5 * cm, 5.5 * cm])
    tabla_header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (2, 0), (2, 0), "RIGHT"),
    ]))
    story.append(tabla_header)
    story.append(Spacer(1, 6))
    story.append(HRFlowable(width="100%", color=colors.HexColor("#1d4ed8"), thickness=1.5))
    story.append(Spacer(1, 8))

    cliente = data.get("cliente", {}) or {}
    equipo = data.get("equipo", {}) or {}
    accesorios = ", ".join(equipo.get("accesorios", []) or []) or "Ninguno"

    story.append(Paragraph("DATOS DEL CLIENTE", styles["Seccion"]))
    cliente_tbl = Table([
        [Paragraph("Nombre:", styles["CeldaBold"]), Paragraph(cliente.get("nombre", ""), styles["Celda"]),
         Paragraph("Teléfono:", styles["CeldaBold"]), Paragraph(cliente.get("telefono", ""), styles["Celda"])],
        [Paragraph("DNI:", styles["CeldaBold"]), Paragraph(cliente.get("dni", ""), styles["Celda"]),
         Paragraph("WhatsApp:", styles["CeldaBold"]), Paragraph(cliente.get("whatsapp", ""), styles["Celda"])],
        [Paragraph("Correo:", styles["CeldaBold"]), Paragraph(cliente.get("correo", ""), styles["Celda"]),
         Paragraph("Dirección:", styles["CeldaBold"]), Paragraph(cliente.get("direccion", ""), styles["Celda"])],
    ], colWidths=[2.3 * cm, 6.7 * cm, 2.3 * cm, 6.3 * cm])
    cliente_tbl.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(cliente_tbl)
    story.append(Spacer(1, 6))

    story.append(Paragraph("EQUIPO", styles["Seccion"]))
    equipo_tbl = Table([
        [Paragraph("Tipo:", styles["CeldaBold"]), Paragraph(equipo.get("tipo", ""), styles["Celda"]),
         Paragraph("Marca:", styles["CeldaBold"]), Paragraph(equipo.get("marca", ""), styles["Celda"])],
        [Paragraph("Modelo:", styles["CeldaBold"]), Paragraph(equipo.get("modelo", ""), styles["Celda"]),
         Paragraph("IMEI/Serie:", styles["CeldaBold"]), Paragraph(equipo.get("imei", "") or equipo.get("numero_serie", ""), styles["Celda"])],
        [Paragraph("Accesorios:", styles["CeldaBold"]), Paragraph(accesorios, styles["Celda"]), "", ""],
    ], colWidths=[2.3 * cm, 6.7 * cm, 2.3 * cm, 6.3 * cm])
    equipo_tbl.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("SPAN", (1, 2), (3, 2))]))
    story.append(equipo_tbl)
    story.append(Spacer(1, 6))

    story.append(Paragraph("CONDICIÓN, FALLA Y TRABAJO REALIZADO", styles["Seccion"]))
    filas_detalle = [
        [Paragraph("Estado físico:", styles["CeldaBold"]), Paragraph(data.get("condicion_fisica", "") or "-", styles["Celda"])],
        [Paragraph("Falla reportada:", styles["CeldaBold"]), Paragraph(data.get("falla_reportada", "") or "-", styles["Celda"])],
        [Paragraph("Diagnóstico:", styles["CeldaBold"]), Paragraph(data.get("diagnostico", "") or "-", styles["Celda"])],
        [Paragraph("Trabajo realizado:", styles["CeldaBold"]), Paragraph(data.get("trabajo_realizado", "") or "-", styles["Celda"])],
        [Paragraph("Observaciones:", styles["CeldaBold"]), Paragraph(data.get("observaciones", "") or "-", styles["Celda"])],
        [Paragraph("Técnico:", styles["CeldaBold"]), Paragraph(data.get("tecnico", "") or "-", styles["Celda"])],
    ]
    if data.get("mostrar_seguridad_en_pdf") and (data.get("pin") or data.get("patron")):
        seguridad_partes = []
        if data.get("pin"):
            seguridad_partes.append(f"PIN: {data['pin']}")
        if data.get("patron"):
            seguridad_partes.append(f"Patrón: {data['patron']}")
        filas_detalle.append([Paragraph("Acceso al equipo:", styles["CeldaBold"]), Paragraph(" / ".join(seguridad_partes), styles["Celda"])])
    detalle_tbl = Table(filas_detalle, colWidths=[3.2 * cm, 14.4 * cm])
    detalle_tbl.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(detalle_tbl)
    story.append(Spacer(1, 6))

    fin = data.get("financiero", {}) or {}
    story.append(Paragraph("RESUMEN FINANCIERO", styles["Seccion"]))
    filas_fin = [["Cotización", _moneda(fin.get("cotizacion", 0), moneda)],
                 [f"Recargo ({fin.get('recargo_pct', 0)}%)", _moneda(fin.get("recargo_monto", 0), moneda)]]
    if float(fin.get("repuestos_subtotal", 0) or 0) > 0:
        filas_fin.append(["Repuestos utilizados", _moneda(fin.get("repuestos_subtotal", 0), moneda)])
    fila_total_idx = len(filas_fin)
    filas_fin.append(["TOTAL DEL SERVICIO", _moneda(fin.get("total", 0), moneda)])
    filas_fin.append(["Total abonado", _moneda(fin.get("abonado", 0), moneda)])
    fila_saldo_idx = len(filas_fin)
    filas_fin.append(["SALDO PENDIENTE", _moneda(fin.get("saldo", 0), moneda)])
    filas_fin.append(["Forma de pago", fin.get("forma_pago", "-")])
    fin_tbl = Table(filas_fin, colWidths=[8 * cm, 9.6 * cm])
    fin_tbl.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("FONTNAME", (0, fila_total_idx), (-1, fila_total_idx), "Helvetica-Bold"),
        ("FONTNAME", (0, fila_saldo_idx), (-1, fila_saldo_idx), "Helvetica-Bold"),
        ("BACKGROUND", (0, fila_total_idx), (-1, fila_total_idx), colors.HexColor("#e0e7ff")),
        ("BACKGROUND", (0, fila_saldo_idx), (-1, fila_saldo_idx), colors.HexColor("#dcfce7")),
    ]))
    story.append(fin_tbl)

    repuestos = data.get("repuestos") or []
    if repuestos:
        story.append(Spacer(1, 6))
        story.append(Paragraph("REPUESTOS UTILIZADOS", styles["Seccion"]))
        filas = [["Repuesto", "Cant.", "P. unitario", "Subtotal"]]
        for r in repuestos:
            filas.append([r.get("producto", ""), str(r.get("cantidad", "")),
                          _moneda(r.get("precio_unitario", 0), moneda), _moneda(r.get("subtotal", 0), moneda)])
        rep_tbl = Table(filas, colWidths=[7.6 * cm, 2 * cm, 3.5 * cm, 4.5 * cm])
        rep_tbl.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1d4ed8")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ]))
        story.append(rep_tbl)

    pagos = data.get("pagos") or []
    if pagos:
        story.append(Spacer(1, 6))
        story.append(Paragraph("ABONOS REGISTRADOS", styles["Seccion"]))
        filas = [["Fecha", "Monto", "Forma de pago"]]
        for p in pagos:
            filas.append([str(p.get("fecha", "")), _moneda(p.get("monto", 0), moneda), p.get("forma_pago", "")])
        pagos_tbl = Table(filas, colWidths=[5 * cm, 5 * cm, 7.6 * cm])
        pagos_tbl.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1d4ed8")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ]))
        story.append(pagos_tbl)

    if taller.get("info_pdf_extra"):
        story.append(Spacer(1, 6))
        story.append(Paragraph(taller["info_pdf_extra"], styles["Sub"]))

    story.append(Spacer(1, 24))
    firmas = Table([
        ["_________________________", "_________________________"],
        ["Firma del cliente", "Firma del técnico / taller"],
    ], colWidths=[8.5 * cm, 8.5 * cm])
    firmas.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER")]))
    story.append(firmas)

    _agregar_condiciones_servicio(story, styles["CondTitulo"], styles["CondTexto"], data.get("taller", {}).get("condiciones_servicio", ""))

    doc.build(story)
    return buffer.getvalue()


def construir_contexto_pdf(orden, config) -> dict:
    """Arma el diccionario que espera generar_pdf_orden() a partir de los
    objetos SQLAlchemy OrdenServicio y Configuracion.
    """
    return {
        "taller": {
            "nombre": config.nombre_taller if config else "Taller de Reparación",
            "telefono": config.telefono if config else "",
            "direccion": config.direccion if config else "",
            "correo": config.correo if config else "",
            "moneda": config.moneda if config else "L",
            "logo_path": config.logo_path if config else None,
            "logo_data": config.logo_data if config else None,
            "info_pdf_extra": config.info_pdf_extra if config else "",
            "condiciones_servicio": (config.condiciones_servicio if config and config.condiciones_servicio else "") if config else "",
        },
        "numero_orden": orden.numero_orden,
        "fecha": orden.fecha.strftime("%d/%m/%Y") if orden.fecha else "",
        "estado": orden.estado,
        "prioridad": orden.prioridad,
        "pin": orden.pin,
        "patron": orden.patron,
        "mostrar_seguridad_en_pdf": bool(orden.mostrar_seguridad_en_pdf),
        "cliente": {
            "nombre": orden.cliente.nombre if orden.cliente else "",
            "telefono": orden.cliente.telefono if orden.cliente else "",
            "whatsapp": orden.cliente.whatsapp if orden.cliente else "",
            "dni": orden.cliente.dni if orden.cliente else "",
            "correo": orden.cliente.correo if orden.cliente else "",
            "direccion": orden.cliente.direccion if orden.cliente else "",
        },
        "equipo": {
            "tipo": orden.tipo_equipo,
            "marca": orden.marca,
            "modelo": orden.modelo,
            "imei": orden.imei,
            "numero_serie": orden.numero_serie,
            "accesorios": orden.lista_accesorios(),
        },
        "condicion_fisica": ", ".join(orden.lista_condicion()) + ((" - " + orden.observaciones_condicion) if orden.observaciones_condicion else ""),
        "falla_reportada": orden.falla_reportada,
        "diagnostico": orden.diagnostico,
        "trabajo_realizado": orden.trabajo_realizado,
        "observaciones": orden.observaciones,
        "tecnico": orden.tecnico.nombre if orden.tecnico else "",
        "financiero": {
            "cotizacion": orden.cotizacion,
            "recargo_pct": orden.recargo_pct,
            "recargo_monto": orden.recargo_monto,
            "repuestos_subtotal": orden.repuestos_subtotal,
            "total": orden.total,
            "abonado": orden.abonado,
            "saldo": orden.saldo,
            "forma_pago": orden.forma_pago,
        },
        "pagos": [
            {"fecha": p.fecha.strftime("%d/%m/%Y"), "monto": p.monto, "forma_pago": p.forma_pago}
            for p in orden.pagos
        ],
        "repuestos": [
            {
                "producto": r.producto.nombre if r.producto else "",
                "cantidad": r.cantidad,
                "precio_unitario": r.precio_unitario,
                "subtotal": r.subtotal,
            }
            for r in orden.repuestos
        ],
    }


def generar_pdf_factura(data: dict) -> bytes:
    """Genera el PDF en formato carta de una factura (interna o fiscal).
    Ver construir_contexto_pdf_factura() para el formato del diccionario."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=letter,
        topMargin=1.2 * cm, bottomMargin=1.2 * cm,
        leftMargin=1.4 * cm, rightMargin=1.4 * cm,
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="SubF", fontSize=9, textColor=colors.HexColor("#475569")))
    styles.add(ParagraphStyle(name="SeccionF", fontSize=11, fontName="Helvetica-Bold", textColor=colors.white,
                               backColor=colors.HexColor("#1d4ed8"), leftIndent=4, spaceBefore=6, spaceAfter=4,
                               borderPadding=(3, 3, 3, 3)))
    styles.add(ParagraphStyle(name="Legal", fontSize=7.5, textColor=colors.HexColor("#64748b")))
    styles.add(ParagraphStyle(name="TituloDoc", fontSize=14, fontName="Helvetica-Bold", alignment=TA_RIGHT))
    styles.add(ParagraphStyle(name="Celda", fontSize=9, leading=12))
    styles.add(ParagraphStyle(name="CeldaBold", fontSize=9, leading=12, fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle(name="CondTitulo", fontSize=9.5, leading=12, fontName="Helvetica-Bold", textColor=colors.HexColor("#1d4ed8")))
    styles.add(ParagraphStyle(name="CondTexto", fontSize=7.5, leading=10, textColor=colors.HexColor("#475569")))

    taller = data.get("taller", {}) or {}
    moneda = taller.get("moneda", "L")
    es_fiscal = data.get("tipo") == "fiscal"
    story = []

    logo_path = taller.get("logo_path")
    logo_data = taller.get("logo_data")
    logo_cell = ""
    if logo_data:
        try:
            logo_cell = Image(BytesIO(logo_data), width=2.2 * cm, height=2.2 * cm)
        except Exception:
            logo_cell = ""
    elif logo_path:
        try:
            logo_cell = Image(logo_path, width=2.2 * cm, height=2.2 * cm)
        except Exception:
            logo_cell = ""

    titulo = "FACTURA" if es_fiscal else "COMPROBANTE INTERNO"
    info_taller_html = f"<b>{taller.get('nombre', 'Taller de Reparación')}</b><br/>{taller.get('direccion', '')}<br/>"
    if es_fiscal:
        info_taller_html += f"RTN: <b>{data.get('rtn_emisor', '')}</b><br/>"
    info_taller_html += f"Tel/WhatsApp: {taller.get('telefono', '')} · {taller.get('correo', '')}"
    info_taller = Paragraph(info_taller_html, styles["SubF"])

    doc_info_html = f"<b>{titulo}</b><br/>N.º <b>{data.get('numero_documento', '')}</b><br/>Fecha: {data.get('fecha_emision', '')}"
    if es_fiscal:
        doc_info_html += (
            f"<br/><font size=7>CAI: {data.get('cai_usado', '')}</font>"
            f"<br/><font size=7>Rango autorizado: {data.get('rango_autorizado_inicio', '')} al {data.get('rango_autorizado_fin', '')}</font>"
        )
        if data.get("fecha_limite_emision"):
            doc_info_html += f"<br/><font size=7>Fecha límite de emisión: {data['fecha_limite_emision']}</font>"
    doc_info = Paragraph(doc_info_html, styles["SubF"])

    tabla_header = Table([[logo_cell, info_taller, doc_info]], colWidths=[2.6 * cm, 9.5 * cm, 5.5 * cm])
    tabla_header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (2, 0), (2, 0), "RIGHT"),
    ]))
    story.append(tabla_header)
    story.append(Spacer(1, 6))
    story.append(HRFlowable(width="100%", color=colors.HexColor("#1d4ed8"), thickness=1.5))
    story.append(Spacer(1, 8))

    if data.get("anulada"):
        story.append(Paragraph("<b>*** DOCUMENTO ANULADO ***</b>", ParagraphStyle(
            name="Anulado", fontSize=13, textColor=colors.red, alignment=1)))
        story.append(Spacer(1, 8))

    story.append(Paragraph("CLIENTE", styles["SeccionF"]))
    cliente_filas = [[Paragraph("Nombre:", styles["CeldaBold"]), Paragraph(data.get("cliente_nombre") or "Consumidor final", styles["Celda"])]]
    if es_fiscal:
        cliente_filas.append([Paragraph("RTN:", styles["CeldaBold"]), Paragraph(data.get("cliente_rtn") or "N/A", styles["Celda"])])
    if data.get("cliente_direccion"):
        cliente_filas.append([Paragraph("Dirección:", styles["CeldaBold"]), Paragraph(data.get("cliente_direccion", ""), styles["Celda"])])
    cliente_tbl = Table(cliente_filas, colWidths=[3.2 * cm, 14.4 * cm])
    cliente_tbl.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(cliente_tbl)
    story.append(Spacer(1, 6))

    if data.get("descripcion"):
        story.append(Paragraph("DETALLE", styles["SeccionF"]))
        story.append(Paragraph(data["descripcion"], styles["Celda"]))
        story.append(Spacer(1, 6))

    story.append(Paragraph("RESUMEN", styles["SeccionF"]))
    filas_resumen = [["Subtotal", _moneda(data.get("subtotal", 0), moneda)]]
    if float(data.get("descuento", 0) or 0) > 0:
        filas_resumen.append(["Descuento", "-" + _moneda(data.get("descuento", 0), moneda)])
    if float(data.get("importe_exento", 0) or 0) > 0:
        filas_resumen.append(["Importe exento", _moneda(data.get("importe_exento", 0), moneda)])
    if float(data.get("importe_gravado", 0) or 0) > 0:
        filas_resumen.append([f"Importe gravado ({data.get('isv_tasa', 0)}%)", _moneda(data.get("importe_gravado", 0), moneda)])
        filas_resumen.append([f"ISV ({data.get('isv_tasa', 0)}%)", _moneda(data.get("isv_monto", 0), moneda)])
    filas_resumen.append(["TOTAL A PAGAR", _moneda(data.get("total", 0), moneda)])
    resumen_tbl = Table(filas_resumen, colWidths=[8 * cm, 9.6 * cm])
    estilo_resumen = [
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#dcfce7")),
    ]
    resumen_tbl.setStyle(TableStyle(estilo_resumen))
    story.append(resumen_tbl)
    story.append(Spacer(1, 10))

    if data.get("texto_legal"):
        story.append(Paragraph(data["texto_legal"], styles["Legal"]))

    story.append(Spacer(1, 24))
    firmas = Table([
        ["_________________________", "_________________________"],
        ["Firma del cliente", "Firma autorizada del taller"],
    ], colWidths=[8.5 * cm, 8.5 * cm])
    firmas.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER")]))
    story.append(firmas)

    _agregar_condiciones_servicio(story, styles["CondTitulo"], styles["CondTexto"], data.get("taller", {}).get("condiciones_servicio", ""))

    doc.build(story)
    return buffer.getvalue()


def construir_contexto_pdf_factura(factura, config_facturacion, config_general) -> dict:
    """Arma el diccionario que esperan generar_pdf_factura() y
    generar_ticket_factura() a partir del objeto SQLAlchemy Factura."""
    es_fiscal = factura.tipo == "fiscal"
    orden = factura.orden
    descripcion = None
    if orden:
        partes = [f"Servicio: {orden.tipo_equipo or ''} {orden.marca or ''} {orden.modelo or ''}".strip()]
        if orden.falla_reportada:
            partes.append(f"Falla reportada: {orden.falla_reportada}")
        if orden.diagnostico:
            partes.append(f"Diagnóstico: {orden.diagnostico}")
        if orden.numero_orden:
            partes.append(f"Orden relacionada: {orden.numero_orden}")
        if getattr(orden, "repuestos", None):
            moneda_factura = config_general.moneda if config_general else "L"
            items_repuestos = ", ".join(
                f"{r.producto.nombre if r.producto else 'Repuesto'} x{r.cantidad} ({_moneda(r.subtotal, moneda_factura)})"
                for r in orden.repuestos
            )
            if items_repuestos:
                partes.append(f"Repuestos utilizados: {items_repuestos}")
        if getattr(orden, "mostrar_seguridad_en_pdf", False):
            if orden.pin:
                partes.append(f"PIN: {orden.pin}")
            if orden.patron:
                partes.append(f"Patrón: {orden.patron}")
        descripcion = " · ".join(p for p in partes if p)

    texto_legal = (config_facturacion.texto_legal_fiscal if es_fiscal else config_facturacion.texto_legal_interno) if config_facturacion else ""

    return {
        "taller": {
            "nombre": config_general.nombre_taller if config_general else "Taller de Reparación",
            "telefono": config_general.telefono if config_general else "",
            "direccion": config_general.direccion if config_general else "",
            "correo": config_general.correo if config_general else "",
            "moneda": config_general.moneda if config_general else "L",
            "logo_path": config_general.logo_path if config_general else None,
            "logo_data": config_general.logo_data if config_general else None,
            "info_pdf_extra": config_general.info_pdf_extra if config_general else "",
            "condiciones_servicio": (config_general.condiciones_servicio if config_general and config_general.condiciones_servicio else "") if config_general else "",
        },
        "tipo": factura.tipo,
        "numero_documento": factura.numero_documento,
        "fecha_emision": factura.fecha_emision.strftime("%d/%m/%Y %H:%M") if factura.fecha_emision else "",
        "rtn_emisor": factura.rtn_emisor or "",
        "cai_usado": factura.cai_usado or "",
        "rango_autorizado_inicio": factura.rango_autorizado_inicio or "",
        "rango_autorizado_fin": factura.rango_autorizado_fin or "",
        "fecha_limite_emision": factura.fecha_limite_emision.strftime("%d/%m/%Y") if factura.fecha_limite_emision else "",
        "cliente_nombre": factura.cliente_nombre or "",
        "cliente_rtn": factura.cliente_rtn or "",
        "cliente_direccion": factura.cliente_direccion or "",
        "descripcion": descripcion,
        "subtotal": factura.subtotal,
        "descuento": factura.descuento,
        "importe_exento": factura.importe_exento,
        "importe_gravado": factura.importe_gravado,
        "isv_tasa": factura.isv_tasa,
        "isv_monto": factura.isv_monto,
        "total": factura.total,
        "anulada": factura.anulada,
        "texto_legal": texto_legal,
    }
