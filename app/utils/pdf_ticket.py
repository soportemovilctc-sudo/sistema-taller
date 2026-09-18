"""Generación de tirilla (recibo térmico) de 80mm, tanto para la orden de
servicio como para la factura. Usa un lienzo (canvas) de ReportLab cuyo
alto se calcula según el contenido, para que el PDF quede del tamaño justo
(como en una impresora de rollo continuo), no del tamaño de una hoja carta.
"""
import textwrap
from io import BytesIO
from reportlab.lib.units import mm
from reportlab.lib.pagesizes import letter  # noqa: F401 (compatibilidad)
from reportlab.pdfgen import canvas

from app.models import parse_condiciones_servicio

ANCHO_TICKET = 80 * mm
MARGEN = 3 * mm
ANCHO_UTIL_CHARS = 42  # caracteres aprox. que caben por línea a 8pt


def _moneda(valor, simbolo="L"):
    try:
        return f"{simbolo} {float(valor):,.2f}"
    except (TypeError, ValueError):
        return f"{simbolo} 0.00"


def _wrap(texto, ancho=ANCHO_UTIL_CHARS):
    texto = str(texto or "").strip()
    if not texto:
        return [""]
    lineas = []
    for parrafo in texto.split("\n"):
        lineas.extend(textwrap.wrap(parrafo, ancho) or [""])
    return lineas


class _ConstructorTicket:
    """Arma la lista de instrucciones de dibujo y calcula el alto necesario
    antes de crear el canvas real, así el PDF sale del tamaño exacto."""

    def __init__(self):
        self.instrucciones = []  # lista de (tipo, contenido, alto_pts)

    def texto(self, s, tam=8, negrita=False, centrado=False, alto=10):
        self.instrucciones.append(("texto", s, tam, negrita, centrado, alto))

    def parrafo(self, s, tam=8, negrita=False, alto=10):
        for linea in _wrap(s):
            self.texto(linea, tam=tam, negrita=negrita, alto=alto)

    def linea_doble(self, izq, der, tam=8, negrita=False, alto=10):
        self.instrucciones.append(("dos_col", izq, der, tam, negrita, alto))

    def separador(self, alto=6):
        self.instrucciones.append(("separador", None, None, None, None, alto))

    def espacio(self, alto=6):
        self.instrucciones.append(("espacio", None, None, None, None, alto))

    def alto_total(self):
        return sum(item[-1] for item in self.instrucciones)

    def renderizar(self) -> bytes:
        alto_contenido = self.alto_total()
        alto_pagina = alto_contenido + 2 * MARGEN
        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=(ANCHO_TICKET, alto_pagina))
        y = alto_pagina - MARGEN
        x_izq = MARGEN
        x_der = ANCHO_TICKET - MARGEN
        x_centro = ANCHO_TICKET / 2

        for item in self.instrucciones:
            tipo = item[0]
            if tipo == "texto":
                _, s, tam, negrita, centrado, alto = item
                y -= alto
                fuente = "Helvetica-Bold" if negrita else "Helvetica"
                c.setFont(fuente, tam)
                if centrado:
                    c.drawCentredString(x_centro, y, s)
                else:
                    c.drawString(x_izq, y, s)
            elif tipo == "dos_col":
                _, izq, der, tam, negrita, alto = item
                y -= alto
                fuente = "Helvetica-Bold" if negrita else "Helvetica"
                c.setFont(fuente, tam)
                c.drawString(x_izq, y, str(izq))
                c.drawRightString(x_der, y, str(der))
            elif tipo == "separador":
                alto = item[-1]
                y -= alto / 2
                c.setDash(1, 1)
                c.line(x_izq, y, x_der, y)
                c.setDash()
                y -= alto / 2
            elif tipo == "espacio":
                alto = item[-1]
                y -= alto

        c.showPage()
        c.save()
        return buffer.getvalue()


def _condiciones_servicio(t, texto_condiciones=""):
    """Agrega, al final de la tirilla, el bloque (editable desde
    Configuración) de condiciones de servicio y retiro de equipos (orden de
    servicio y factura). Si no hay texto configurado, no agrega nada."""
    condiciones = parse_condiciones_servicio(texto_condiciones)
    if not condiciones:
        return
    t.separador()
    t.texto("Condiciones de Servicio y Retiro de Equipos", tam=7, negrita=True, centrado=True, alto=9)
    t.espacio(1)
    for titulo, texto in condiciones:
        contenido = f"{titulo} {texto}" if titulo else texto
        t.parrafo(contenido, tam=6, alto=8)


def _encabezado_taller(t, taller: dict):
    t.texto(taller.get("nombre", "Taller de Reparación"), tam=11, negrita=True, centrado=True, alto=14)
    if taller.get("direccion"):
        t.parrafo(taller["direccion"], tam=7, alto=9)
    contacto = " · ".join([x for x in [taller.get("telefono"), taller.get("correo")] if x])
    if contacto:
        t.texto(contacto, tam=7, centrado=True, alto=9)
    t.separador()


def generar_ticket_orden(data: dict) -> bytes:
    """Tirilla de 80mm para una ORDEN DE SERVICIO (ver construir_contexto_pdf)."""
    t = _ConstructorTicket()
    taller = data.get("taller", {}) or {}
    moneda = taller.get("moneda", "L")
    _encabezado_taller(t, taller)

    t.texto("ORDEN DE SERVICIO", tam=9, negrita=True, centrado=True, alto=12)
    t.texto(f"N.o {data.get('numero_orden', '')}", tam=9, negrita=True, centrado=True, alto=12)
    t.texto(f"Fecha: {data.get('fecha', '')}", tam=7, centrado=True, alto=9)
    t.texto(f"Estado: {data.get('estado', '')}", tam=7, centrado=True, alto=9)
    t.separador()

    cliente = data.get("cliente", {}) or {}
    t.texto("CLIENTE", tam=8, negrita=True, alto=10)
    t.parrafo(cliente.get("nombre", "-"), alto=9)
    if cliente.get("telefono"):
        t.parrafo(f"Tel: {cliente['telefono']}", alto=9)
    t.espacio(2)

    equipo = data.get("equipo", {}) or {}
    t.texto("EQUIPO", tam=8, negrita=True, alto=10)
    t.parrafo(f"{equipo.get('tipo', '')} {equipo.get('marca', '')} {equipo.get('modelo', '')}".strip(), alto=9)
    if equipo.get("imei"):
        t.parrafo(f"IMEI: {equipo['imei']}", alto=9)
    t.espacio(2)

    if data.get("falla_reportada"):
        t.texto("FALLA REPORTADA", tam=8, negrita=True, alto=10)
        t.parrafo(data["falla_reportada"], alto=9)
        t.espacio(2)

    if data.get("diagnostico"):
        t.texto("DIAGNOSTICO", tam=8, negrita=True, alto=10)
        t.parrafo(data["diagnostico"], alto=9)
        t.espacio(2)

    t.separador()
    fin = data.get("financiero", {}) or {}
    t.linea_doble("Cotizacion", _moneda(fin.get("cotizacion", 0), moneda), alto=10)
    t.linea_doble(f"Recargo ({fin.get('recargo_pct', 0)}%)", _moneda(fin.get("recargo_monto", 0), moneda), alto=10)
    t.linea_doble("TOTAL", _moneda(fin.get("total", 0), moneda), tam=9, negrita=True, alto=12)
    t.linea_doble("Abonado", _moneda(fin.get("abonado", 0), moneda), alto=10)
    t.linea_doble("SALDO PENDIENTE", _moneda(fin.get("saldo", 0), moneda), tam=9, negrita=True, alto=12)
    t.separador()

    if taller.get("info_pdf_extra"):
        t.parrafo(taller["info_pdf_extra"], tam=6, alto=8)
        t.espacio(2)

    t.espacio(6)
    t.texto("_____________________________", centrado=True, tam=7, alto=9)
    t.texto("Firma del cliente", centrado=True, tam=7, alto=10)
    t.espacio(4)

    _condiciones_servicio(t, data.get("taller", {}).get("condiciones_servicio", ""))

    return t.renderizar()


def generar_ticket_factura(data: dict) -> bytes:
    """Tirilla de 80mm para una FACTURA (interna o fiscal). Ver
    construir_contexto_pdf_factura()."""
    t = _ConstructorTicket()
    taller = data.get("taller", {}) or {}
    moneda = taller.get("moneda", "L")
    _encabezado_taller(t, taller)

    if data.get("tipo") == "fiscal":
        t.texto(f"RTN: {data.get('rtn_emisor', '')}", tam=7, centrado=True, alto=9)
        t.texto("FACTURA", tam=9, negrita=True, centrado=True, alto=12)
    else:
        t.texto("COMPROBANTE INTERNO", tam=9, negrita=True, centrado=True, alto=12)
        t.texto("(No valido como factura fiscal)", tam=6, centrado=True, alto=8)

    t.texto(f"No. {data.get('numero_documento', '')}", tam=9, negrita=True, centrado=True, alto=12)
    t.texto(f"Fecha: {data.get('fecha_emision', '')}", tam=7, centrado=True, alto=9)

    if data.get("tipo") == "fiscal":
        t.espacio(2)
        t.texto(f"CAI: {data.get('cai_usado', '')}", tam=6, centrado=True, alto=8)
        t.texto(f"Rango: {data.get('rango_autorizado_inicio', '')} al {data.get('rango_autorizado_fin', '')}", tam=6, centrado=True, alto=8)
        if data.get("fecha_limite_emision"):
            t.texto(f"Fecha limite de emision: {data['fecha_limite_emision']}", tam=6, centrado=True, alto=8)

    t.separador()
    t.texto("CLIENTE", tam=8, negrita=True, alto=10)
    t.parrafo(data.get("cliente_nombre") or "Consumidor final", alto=9)
    if data.get("cliente_rtn"):
        t.parrafo(f"RTN: {data['cliente_rtn']}", alto=9)
    t.separador()

    if data.get("descripcion"):
        t.parrafo(data["descripcion"], alto=9)
        t.espacio(3)

    t.linea_doble("Subtotal", _moneda(data.get("subtotal", 0), moneda), alto=10)
    if float(data.get("descuento", 0) or 0) > 0:
        t.linea_doble("Descuento", "-" + _moneda(data.get("descuento", 0), moneda), alto=10)
    if float(data.get("importe_exento", 0) or 0) > 0:
        t.linea_doble("Importe exento", _moneda(data.get("importe_exento", 0), moneda), alto=10)
    if float(data.get("importe_gravado", 0) or 0) > 0:
        t.linea_doble("Importe gravado", _moneda(data.get("importe_gravado", 0), moneda), alto=10)
        t.linea_doble(f"ISV ({data.get('isv_tasa', 0)}%)", _moneda(data.get("isv_monto", 0), moneda), alto=10)
    t.linea_doble("TOTAL", _moneda(data.get("total", 0), moneda), tam=10, negrita=True, alto=13)
    t.separador()

    texto_legal = data.get("texto_legal", "")
    if texto_legal:
        t.parrafo(texto_legal, tam=6, alto=8)

    if data.get("anulada"):
        t.espacio(4)
        t.texto("*** DOCUMENTO ANULADO ***", tam=9, negrita=True, centrado=True, alto=12)

    t.espacio(6)
    _condiciones_servicio(t, data.get("taller", {}).get("condiciones_servicio", ""))

    return t.renderizar()
