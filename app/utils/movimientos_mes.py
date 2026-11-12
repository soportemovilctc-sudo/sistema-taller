"""Informe «Movimientos del mes»: todo lo que entró y salió de la Caja Chica y
del Banco en un mes, sumado por forma (efectivo, tarjeta, transferencia,
depósitos, retiros del banco), por categoría, y el detalle de cada
movimiento. Se ve en pantalla y se descarga en PDF o Excel."""
from collections import OrderedDict
from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO

from sqlalchemy.orm import Session

from app.models import (
    MovimientoFinanciero, CATEGORIA_DEPOSITO_BANCO, CATEGORIA_COMISION_TARJETA, CATEGORIAS_FUERA_DE_RESULTADOS,
)
from app.utils.calculations import to_decimal
from app.utils.turnos_caja import inicio_dia_local_en_utc, a_hora_local, hoy_local

CERO = Decimal("0.00")
MESES = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre",
         "Noviembre", "Diciembre"]
FORMAS = OrderedDict([
    ("efectivo", "Efectivo (Caja Chica)"),
    ("tarjeta", "Tarjeta / POS"),
    ("transferencia", "Transferencia / banco"),
    ("deposito", "Depósitos (caja → banco)"),
    ("retiro", "Retiros del banco"),
])


def q(v) -> Decimal:
    return to_decimal(v or 0).quantize(Decimal("0.01"))


def mes_desde_texto(texto: str) -> tuple[int, int]:
    try:
        anio, mes = (int(x) for x in (texto or "").split("-")[:2])
        if 1 <= mes <= 12 and 2000 <= anio <= 2100:
            return anio, mes
    except ValueError:
        pass
    h = hoy_local()
    return h.year, h.month


def rango_desde_texto(desde: str, hasta: str, mes: str = "") -> tuple[date, date]:
    """Desde/Hasta (AAAA-MM-DD) del filtro. Sin fechas: del 1 del mes hasta
    hoy (o el mes que venga en `mes`, para enlaces viejos). Si vienen al
    revés, se acomodan."""
    def leer(t):
        try:
            return date.fromisoformat((t or "").strip()[:10])
        except ValueError:
            return None
    d, h = leer(desde), leer(hasta)
    if not d and not h and (mes or "").strip():
        anio, m = mes_desde_texto(mes)
        d = date(anio, m, 1)
        h = (d + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    hoy = hoy_local()
    if not d and not h:
        d, h = hoy.replace(day=1), hoy
    d, h = d or h, h or d
    if d > h:
        d, h = h, d
    return d, h


def titulo_rango(d: date, h: date) -> str:
    fin_mes = (d + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    if d.day == 1 and h == fin_mes:
        return f"{MESES[d.month]} {d.year}"
    if d == h:
        return f"{d:%d/%m/%Y}"
    return f"del {d:%d/%m/%Y} al {h:%d/%m/%Y}"


def forma_de(m: MovimientoFinanciero) -> str:
    if m.categoria == CATEGORIA_DEPOSITO_BANCO:
        return "deposito"
    if m.cuenta != "banco":
        return "efectivo"
    metodo = (m.metodo_pago or "").lower()
    if "retiro" in (m.categoria or "").lower():
        return "retiro"
    if "tarjeta" in metodo or m.categoria == CATEGORIA_COMISION_TARJETA:
        return "tarjeta"
    return "transferencia"


def informe(db: Session, desde: date, hasta: date, banco_id: int | None = None) -> dict:
    """Movimientos de `desde` a `hasta` (los dos días incluidos, hora de Honduras)."""
    from app.utils.estados_financieros import saldo_efectivo_a
    from app.utils.bancos import filtro_banco, nombre_banco, bancos_activos, saldo_banco_a

    inicio_d, fin_d = desde, hasta + timedelta(days=1)
    inicio, fin = inicio_dia_local_en_utc(inicio_d), inicio_dia_local_en_utc(fin_d)
    consulta = db.query(MovimientoFinanciero).filter(
        MovimientoFinanciero.fecha >= inicio, MovimientoFinanciero.fecha < fin,
        MovimientoFinanciero.excluir_de_contabilidad == False,  # noqa: E712
    )
    if banco_id:
        cond = filtro_banco(db, banco_id)
        consulta = consulta.filter(MovimientoFinanciero.cuenta == "banco", cond)
    movs = consulta.order_by(MovimientoFinanciero.fecha.asc(), MovimientoFinanciero.id.asc()).all()

    por_forma = OrderedDict((k, {"nombre": v, "ingresos": CERO, "egresos": CERO, "n": 0}) for k, v in FORMAS.items())
    por_cat = {"ingreso": OrderedDict(), "gasto": OrderedDict()}
    nombres_banco, filas = {}, []
    for m in movs:
        forma = forma_de(m)
        monto = q(m.monto)
        # Un depósito son dos filas (sale de caja, entra al banco): se cuenta una vez, por la entrada al banco.
        if m.categoria == CATEGORIA_DEPOSITO_BANCO:
            if m.cuenta == "banco":
                por_forma["deposito"]["ingresos"] += monto
                por_forma["deposito"]["n"] += 1
        else:
            clave = "ingresos" if m.tipo == "ingreso" else "egresos"
            por_forma[forma][clave] += monto
            por_forma[forma]["n"] += 1
            grupo = por_cat["ingreso" if m.tipo == "ingreso" else "gasto"]
            grupo.setdefault(m.categoria or "Sin categoría", {"monto": CERO, "n": 0})
            grupo[m.categoria or "Sin categoría"]["monto"] += monto
            grupo[m.categoria or "Sin categoría"]["n"] += 1
        if m.cuenta == "banco" and m.banco_id not in nombres_banco:
            nombres_banco[m.banco_id] = nombre_banco(db, m.banco_id)
        filas.append({
            "fecha": a_hora_local(m.fecha), "tipo": "Ingreso" if m.tipo == "ingreso" else "Egreso",
            "forma": FORMAS[forma].split(" (")[0], "clave_forma": forma,
            "cuenta": "Caja Chica" if m.cuenta != "banco" else nombres_banco.get(m.banco_id, "Banco"),
            "categoria": m.categoria or "", "metodo": m.metodo_pago or "",
            "concepto": ((m.cliente_nombre or "").strip() + " · " if (m.cliente_nombre or "").strip() else "") + (m.descripcion or "").strip(),
            "referencia": " · ".join(x for x in ((m.num_referencia or "").strip(), (m.referencia or "").strip()) if x),
            "monto": monto, "ingreso": m.tipo == "ingreso", "fuera_resultados": m.categoria in CATEGORIAS_FUERA_DE_RESULTADOS,
            "usuario": m.usuario_nombre or "",
        })
    for v in por_forma.values():
        v["ingresos"], v["egresos"] = q(v["ingresos"]), q(v["egresos"])
        v["neto"] = q(v["ingresos"] - v["egresos"])

    sin_depositos = [v for k, v in por_forma.items() if k != "deposito"]
    total_ingresos = q(sum((v["ingresos"] for v in sin_depositos), CERO))
    total_egresos = q(sum((v["egresos"] for v in sin_depositos), CERO))
    categorias = {t: sorted(((k, q(v["monto"]), v["n"]) for k, v in g.items()), key=lambda x: -x[1]) for t, g in por_cat.items()}

    saldos = None
    if banco_id:
        saldos = {"banco_inicial": q(saldo_banco_a(db, banco_id, inicio)), "banco_final": q(saldo_banco_a(db, banco_id, min(fin, _ahora())))}
    else:
        ini, fi = saldo_efectivo_a(db, inicio), saldo_efectivo_a(db, min(fin, _ahora()))
        saldos = {"caja_inicial": q(ini["caja_chica"]), "caja_final": q(fi["caja_chica"]),
                  "banco_inicial": q(ini["banco"]), "banco_final": q(fi["banco"])}
    return {
        "desde": desde, "hasta": hasta, "titulo": titulo_rango(desde, hasta), "banco_id": banco_id,
        "banco_nombre": nombre_banco(db, banco_id) if banco_id else "", "varios_bancos": len(bancos_activos(db)) > 1,
        "por_forma": por_forma, "total_ingresos": total_ingresos, "total_egresos": total_egresos,
        "neto": q(total_ingresos - total_egresos), "categorias": categorias, "filas": filas, "n": len(filas),
        "saldos": saldos, "comision_tarjeta": q(sum((f["monto"] for f in filas if f["categoria"] == CATEGORIA_COMISION_TARJETA), CERO)),
    }


def _ahora():
    from datetime import datetime
    return datetime.utcnow() + timedelta(seconds=1)


def nombre_archivo(inf: dict, ext: str) -> str:
    return f"movimientos_{inf['desde']:%Y%m%d}_{inf['hasta']:%Y%m%d}{('_banco' + str(inf['banco_id'])) if inf['banco_id'] else ''}.{ext}"


def excel(inf: dict, nombre_taller: str, moneda: str) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    wb = Workbook()
    h = wb.active
    h.title = "Resumen"
    h["A1"] = nombre_taller
    h["A1"].font = Font(size=14, bold=True)
    h["A2"] = f"Movimientos del mes · {inf['titulo']}" + (f" · {inf['banco_nombre']}" if inf["banco_id"] else "")
    h["A2"].font = Font(size=12, bold=True)
    fila = 4
    cab = PatternFill("solid", fgColor="E2E8F0")
    for i, t in enumerate(["Forma", "Ingresos", "Egresos", "Neto", "Movimientos"], 1):
        c = h.cell(row=fila, column=i, value=t)
        c.font, c.fill = Font(bold=True), cab
    for v in inf["por_forma"].values():
        fila += 1
        h.cell(row=fila, column=1, value=v["nombre"])
        for col, k in ((2, "ingresos"), (3, "egresos"), (4, "neto")):
            h.cell(row=fila, column=col, value=float(v[k])).number_format = '#,##0.00'
        h.cell(row=fila, column=5, value=v["n"])
    fila += 1
    h.cell(row=fila, column=1, value="Total (sin depósitos)").font = Font(bold=True)
    for col, k in ((2, "total_ingresos"), (3, "total_egresos"), (4, "neto")):
        c = h.cell(row=fila, column=col, value=float(inf[k]))
        c.number_format, c.font = '#,##0.00', Font(bold=True)
    fila += 2
    for tipo, titulo in (("ingreso", "Ingresos por categoría"), ("gasto", "Egresos por categoría")):
        h.cell(row=fila, column=1, value=titulo).font = Font(bold=True)
        for cat, monto, n in inf["categorias"][tipo]:
            fila += 1
            h.cell(row=fila, column=1, value=cat)
            h.cell(row=fila, column=2, value=float(monto)).number_format = '#,##0.00'
            h.cell(row=fila, column=3, value=n)
        fila += 2
    h.column_dimensions["A"].width = 38
    for col in "BCDE":
        h.column_dimensions[col].width = 16

    d = wb.create_sheet("Detalle")
    cols = ["Fecha", "Tipo", "Forma", "Cuenta", "Categoría", "Concepto", "Referencia", "Ingreso", "Egreso", "Registró"]
    for i, t in enumerate(cols, 1):
        c = d.cell(row=1, column=i, value=t)
        c.font, c.fill = Font(bold=True), cab
    for r, f in enumerate(inf["filas"], 2):
        d.cell(row=r, column=1, value=f["fecha"].strftime("%d/%m/%Y %I:%M %p"))
        for col, k in ((2, "tipo"), (3, "forma"), (4, "cuenta"), (5, "categoria"), (6, "concepto"), (7, "referencia"), (10, "usuario")):
            d.cell(row=r, column=col, value=f[k])
        d.cell(row=r, column=8 if f["ingreso"] else 9, value=float(f["monto"])).number_format = '#,##0.00'
    for col, w in zip("ABCDEFGHIJ", (19, 9, 16, 18, 26, 50, 22, 13, 13, 18)):
        d.column_dimensions[col].width = w
    out = BytesIO()
    wb.save(out)
    return out.getvalue()


def pdf(inf: dict, nombre_taller: str, moneda: str) -> bytes:
    from xml.sax.saxutils import escape
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    def m(v):
        return f"{moneda} {to_decimal(v):,.2f}"

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(letter), topMargin=1.1 * cm, bottomMargin=1.1 * cm,
                            leftMargin=1.2 * cm, rightMargin=1.2 * cm, title="Movimientos del mes")
    est = getSampleStyleSheet()
    titulo = ParagraphStyle("t", parent=est["Title"], fontSize=15, alignment=0, spaceAfter=2)
    sub = ParagraphStyle("s", parent=est["Normal"], fontSize=9.5, textColor=colors.HexColor("#475569"))
    h2 = ParagraphStyle("h2", parent=est["Heading3"], fontSize=11, spaceBefore=10, spaceAfter=4)
    celda = ParagraphStyle("c", parent=est["Normal"], fontSize=7.6, leading=9.2)
    gris = colors.HexColor("#e2e8f0")
    story = [Paragraph(escape(nombre_taller), titulo),
             Paragraph(escape(f"Movimientos del mes · {inf['titulo']}" + (f" · {inf['banco_nombre']}" if inf["banco_id"] else "")), sub),
             Spacer(1, 8)]
    datos = [["Forma", "Ingresos", "Egresos", "Neto", "Mov."]]
    for v in inf["por_forma"].values():
        datos.append([v["nombre"], m(v["ingresos"]), m(v["egresos"]) if v["egresos"] else "—", m(v["neto"]), str(v["n"])])
    datos.append(["Total (sin depósitos)", m(inf["total_ingresos"]), m(inf["total_egresos"]), m(inf["neto"]), ""])
    t = Table(datos, colWidths=[6.2 * cm, 3.6 * cm, 3.6 * cm, 3.6 * cm, 1.6 * cm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), gris), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                           ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"), ("LINEABOVE", (0, -1), (-1, -1), 0.8, colors.black),
                           ("ALIGN", (1, 0), (-1, -1), "RIGHT"), ("FONTSIZE", (0, 0), (-1, -1), 9)]))
    story.append(t)
    s = inf["saldos"]
    if "caja_inicial" in s:
        story += [Spacer(1, 6), Paragraph(f"Caja Chica: inicio {m(s['caja_inicial'])} → fin {m(s['caja_final'])} · "
                                          f"Banco: inicio {m(s['banco_inicial'])} → fin {m(s['banco_final'])}", sub)]
    else:
        story += [Spacer(1, 6), Paragraph(f"Banco: inicio {m(s['banco_inicial'])} → fin {m(s['banco_final'])}", sub)]
    cats = []
    for tipo, nombre in (("ingreso", "Ingresos por categoría"), ("gasto", "Egresos por categoría")):
        filas = [[nombre, ""]] + [[escape(c), m(v)] for c, v, _ in inf["categorias"][tipo]] or [["—", ""]]
        tc = Table(filas, colWidths=[7.4 * cm, 3.4 * cm])
        tc.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("BACKGROUND", (0, 0), (-1, 0), gris),
                                ("ALIGN", (1, 0), (1, -1), "RIGHT"), ("FONTSIZE", (0, 0), (-1, -1), 8.5)]))
        cats.append(tc)
    story += [Spacer(1, 6), Table([cats], colWidths=[12.2 * cm, 12.2 * cm], style=[("VALIGN", (0, 0), (-1, -1), "TOP")])]
    story.append(Paragraph("Detalle", h2))
    det = [["Fecha", "Forma", "Cuenta", "Categoría", "Concepto", "Ingreso", "Egreso"]]
    for f in inf["filas"]:
        det.append([f["fecha"].strftime("%d/%m %I:%M %p"), f["forma"], Paragraph(escape(f["cuenta"]), celda),
                    Paragraph(escape(f["categoria"]), celda), Paragraph(escape(f["concepto"][:140]), celda),
                    m(f["monto"]) if f["ingreso"] else "", "" if f["ingreso"] else m(f["monto"])])
    td = Table(det, repeatRows=1, colWidths=[2.5 * cm, 2.7 * cm, 3 * cm, 4 * cm, 8.2 * cm, 2.6 * cm, 2.6 * cm])
    td.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), gris), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                            ("FONTSIZE", (0, 0), (-1, -1), 7.6), ("ALIGN", (5, 0), (6, -1), "RIGHT"), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")])]))
    story.append(td)
    doc.build(story)
    return buf.getvalue()
