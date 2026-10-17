"""Estados Financieros: Estado de Resultados, Estado de Flujo de Efectivo,
Balance General y Estado de Cambios en el Patrimonio, para cualquier período.

De dónde sale cada número (no se crea ni se modifica ningún registro):
  * Ingresos y gastos: el libro de movimientos (MovimientoFinanciero), el
    mismo que usan Caja, Contabilidad y Reportes. Se excluyen las filas
    anuladas (excluir_de_contabilidad) y los Depósitos bancarios (son un
    traslado de Caja Chica a Banco, no un ingreso ni un gasto).
  * ISV: las ventas se muestran SIN ISV. El ISV de cada ingreso de Factura
    o del POS se calcula con la proporción isv/total de su factura; ese ISV
    es un pasivo (ISV por pagar), no un ingreso del negocio.
  * Costo de ventas (método periódico): inventario inicial + compras de
    mercadería (egresos "Compras" y "Proveedores") - inventario final. Los
    faltantes/sobrantes de los Ajustes de inventario se separan en su propia
    línea de gasto, para que se vean y no queden escondidos en el costo.
  * Inventario a una fecha: la existencia de cada producto en esa fecha (a
    partir de su historial de movimientos) valorada al costo ACTUAL del
    producto (el sistema no guarda el historial de costos).
  * Caja y Banco a una fecha: el saldo inicial del mes configurado en Caja
    más lo que entró y salió de cada cuenta desde el día 1 de ese mes.
  * Activos fijos, otros activos, deudas, préstamos, capital y retiros: lo
    que registre el administrador en "Datos del balance" (PartidaBalance).
    Los activos fijos se deprecian en línea recta según su vida útil.

Fechas: los períodos se toman en días de Honduras (UTC-6). La base de datos
guarda en UTC, así que cada día va de 06:00 UTC a 06:00 UTC del siguiente.
"""
from collections import OrderedDict
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import (
    MovimientoFinanciero, Factura, Venta, Producto, MovimientoInventario,
    SaldoInicialMensual, PartidaBalance,
    CATEGORIA_VENTA_FACTURADA, CATEGORIA_DEPOSITO_BANCO,
)
from app.utils.calculations import to_decimal
from app.utils.inventario_costos import reporte_ajustes
from app.utils.turnos_caja import inicio_dia_local_en_utc, a_hora_local


def a_hora_local_naive(dt: datetime) -> datetime:
    return a_hora_local(dt).replace(tzinfo=None)

CERO = Decimal("0.00")
CENT = Decimal("0.01")
CATEGORIA_VENTA_POS = "Venta POS"
CATEGORIAS_COMPRA_MERCADERIA = ("Compras", "Proveedores")
CUENTA_CAJA_CHICA = "caja_chica"
CUENTA_BANCO = "banco"
DIAS_POR_MES = Decimal("30.4375")
NOMBRES_MES = ["", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
               "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def q(valor) -> Decimal:
    return to_decimal(valor or 0).quantize(CENT)


# ---------------------------------------------------------------------------
# Período
# ---------------------------------------------------------------------------
class Periodo:
    """Rango de días de Honduras [desde, hasta] (ambos incluidos)."""

    def __init__(self, desde: date, hasta: date):
        if hasta < desde:
            desde, hasta = hasta, desde
        self.desde = desde
        self.hasta = hasta
        self.inicio_utc = inicio_dia_local_en_utc(desde)
        self.fin_utc = inicio_dia_local_en_utc(hasta + timedelta(days=1))

    @property
    def texto(self) -> str:
        if self.desde.day == 1 and (self.hasta + timedelta(days=1)).day == 1 and self.desde.month == self.hasta.month and self.desde.year == self.hasta.year:
            return f"{NOMBRES_MES[self.desde.month].capitalize()} {self.desde.year}"
        return f"del {self.desde.strftime('%d/%m/%Y')} al {self.hasta.strftime('%d/%m/%Y')}"


def periodo_mes(anio: int, mes: int) -> Periodo:
    inicio = date(anio, mes, 1)
    siguiente = date(anio + 1, 1, 1) if mes == 12 else date(anio, mes + 1, 1)
    return Periodo(inicio, siguiente - timedelta(days=1))


# ---------------------------------------------------------------------------
# Línea de un estado (misma estructura para pantalla, Excel y PDF)
# ---------------------------------------------------------------------------
def _l(etiqueta, monto=None, tipo="linea", nivel=1, nota=""):
    """tipo: titulo | linea | subtotal | total | nota"""
    return {"etiqueta": etiqueta, "monto": monto, "tipo": tipo, "nivel": nivel, "nota": nota}


# ---------------------------------------------------------------------------
# Inventario histórico (se carga una vez y se valora a cualquier fecha)
# ---------------------------------------------------------------------------
class InventarioHistorico:
    def __init__(self, db: Session):
        self.productos = db.query(Producto).all()
        self.movimientos = {}
        filas = (
            db.query(
                MovimientoInventario.producto_id, MovimientoInventario.fecha, MovimientoInventario.id,
                MovimientoInventario.tipo, MovimientoInventario.cantidad,
                MovimientoInventario.existencia_anterior, MovimientoInventario.existencia_resultante,
            )
            .order_by(MovimientoInventario.producto_id, MovimientoInventario.fecha, MovimientoInventario.id)
            .all()
        )
        for f in filas:
            self.movimientos.setdefault(f.producto_id, []).append(f)
        self._cache = {}

    @staticmethod
    def _existencia_antes_de(mov) -> int:
        if mov.existencia_anterior is not None:
            return mov.existencia_anterior
        if mov.tipo == "entrada":
            return mov.existencia_resultante - (mov.cantidad or 0)
        if mov.tipo == "salida":
            return mov.existencia_resultante + (mov.cantidad or 0)
        return mov.existencia_resultante  # ajuste viejo sin dato anterior: aproximado

    def existencia_a(self, producto, instante: datetime) -> int:
        if instante >= datetime.utcnow():
            return producto.existencia or 0
        movs = self.movimientos.get(producto.id, [])
        anterior = None
        for m in movs:
            if m.fecha is not None and m.fecha < instante:
                anterior = m
            else:
                break
        if anterior is not None:
            return anterior.existencia_resultante
        if movs:
            return self._existencia_antes_de(movs[0])
        if producto.creado_en is not None and producto.creado_en >= instante:
            return 0
        return producto.existencia or 0

    def valor_a(self, instante: datetime) -> dict:
        if instante in self._cache:
            return self._cache[instante]
        total, unidades = CERO, 0
        por_categoria = {}
        for p in self.productos:
            existencia = max(self.existencia_a(p, instante), 0)
            if not existencia:
                continue
            valor = q(to_decimal(p.costo or 0) * existencia)
            total += valor
            unidades += existencia
            cat = p.categoria or "Sin categoría"
            por_categoria[cat] = por_categoria.get(cat, CERO) + valor
        resultado = {"valor": q(total), "unidades": unidades,
                     "por_categoria": sorted(por_categoria.items(), key=lambda x: -x[1])}
        self._cache[instante] = resultado
        return resultado


# ---------------------------------------------------------------------------
# Movimientos de dinero del período e ISV
# ---------------------------------------------------------------------------
def _movimientos(db: Session, inicio: datetime, fin: datetime, incluir_depositos=False):
    consulta = db.query(MovimientoFinanciero).filter(
        MovimientoFinanciero.fecha >= inicio, MovimientoFinanciero.fecha < fin,
        MovimientoFinanciero.excluir_de_contabilidad == False,  # noqa: E712
    )
    if not incluir_depositos:
        consulta = consulta.filter(MovimientoFinanciero.categoria != CATEGORIA_DEPOSITO_BANCO)
    return consulta.all()


def _isv_de_movimientos(db: Session, ingresos) -> dict:
    """ISV incluido en cada ingreso de Factura de orden y del POS, por
    proporción isv/total de su factura. Devuelve {mov_id: isv}."""
    ids_factura = {m.factura_id for m in ingresos if m.factura_id}
    numeros_venta = {m.referencia for m in ingresos if m.categoria == CATEGORIA_VENTA_POS and m.referencia}
    facturas = {}
    if ids_factura:
        facturas.update({f.id: f for f in db.query(Factura).filter(Factura.id.in_(ids_factura)).all()})
    recibos_por_venta = {}
    if numeros_venta:
        ventas = db.query(Venta.id, Venta.numero_venta).filter(Venta.numero_venta.in_(numeros_venta)).all()
        ids_venta = {v.id: v.numero_venta for v in ventas}
        if ids_venta:
            for f in db.query(Factura).filter(Factura.venta_id.in_(list(ids_venta)), Factura.orden_id.is_(None)).all():
                recibos_por_venta[ids_venta[f.venta_id]] = f
    isv = {}
    for m in ingresos:
        factura = None
        if m.categoria == CATEGORIA_VENTA_FACTURADA and m.factura_id:
            factura = facturas.get(m.factura_id)
        elif m.categoria == CATEGORIA_VENTA_POS:
            factura = recibos_por_venta.get(m.referencia)
        if factura is None or not factura.total or factura.anulada:
            continue
        isv[m.id] = q(to_decimal(m.monto) * to_decimal(factura.isv_monto or 0) / to_decimal(factura.total))
    return isv


def _agrupar(movs) -> list[tuple[str, Decimal]]:
    grupos = OrderedDict()
    for m in sorted(movs, key=lambda x: x.categoria or ""):
        grupos[m.categoria or "Sin categoría"] = grupos.get(m.categoria or "Sin categoría", CERO) + to_decimal(m.monto)
    return sorted(((k, q(v)) for k, v in grupos.items()), key=lambda par: -par[1])


# ---------------------------------------------------------------------------
# Partidas registradas por el admin y depreciación
# ---------------------------------------------------------------------------
def _depreciacion_acumulada(partida: PartidaBalance, dia: date) -> Decimal:
    """Depreciación en línea recta acumulada hasta el inicio de `dia`."""
    if partida.tipo != "activo_fijo" or not partida.vida_util_meses:
        return CERO
    tope = dia if partida.fecha_baja is None else min(dia, partida.fecha_baja)
    dias = (tope - partida.fecha).days
    if dias <= 0:
        return CERO
    fraccion = min(Decimal(dias) / (Decimal(partida.vida_util_meses) * DIAS_POR_MES), Decimal(1))
    return q(to_decimal(partida.monto) * fraccion)


def depreciacion_del_periodo(partidas, periodo: Periodo) -> Decimal:
    fin = periodo.hasta + timedelta(days=1)
    return q(sum((_depreciacion_acumulada(p, fin) - _depreciacion_acumulada(p, periodo.desde) for p in partidas), CERO))


# ---------------------------------------------------------------------------
# Saldos de Caja Chica y Banco a un instante
# ---------------------------------------------------------------------------
def _sumar_movimientos(db: Session, caja: Decimal, banco: Decimal, desde: datetime, hasta: datetime):
    for m in _movimientos(db, desde, hasta, incluir_depositos=True):
        signo = 1 if m.tipo == "ingreso" else -1
        if m.cuenta == CUENTA_BANCO:
            banco += signo * to_decimal(m.monto)
        else:
            caja += signo * to_decimal(m.monto)
    return caja, banco


def _inicio_mes_utc(anio: int, mes: int) -> datetime:
    return inicio_dia_local_en_utc(date(anio, mes, 1))


def _saldo_al_iniciar_mes(db: Session, anio: int, mes: int, profundidad: int = 0) -> tuple[Decimal, Decimal, bool]:
    """(caja, banco, hay_saldo_configurado) al empezar el mes: el saldo
    inicial configurado en Caja; si ese mes no tiene, el saldo final del mes
    anterior (hasta 36 meses atrás; si no hay ninguno, se parte de 0)."""
    fila = db.query(SaldoInicialMensual).filter(
        SaldoInicialMensual.anio == anio, SaldoInicialMensual.mes == mes,
    ).first()
    if fila is not None:
        return to_decimal(fila.saldo_inicial_caja_chica), to_decimal(fila.saldo_inicial_banco), True
    if profundidad >= 36:
        return CERO, CERO, False
    anio_prev, mes_prev = (anio - 1, 12) if mes == 1 else (anio, mes - 1)
    caja, banco, configurado = _saldo_al_iniciar_mes(db, anio_prev, mes_prev, profundidad + 1)
    caja, banco = _sumar_movimientos(db, caja, banco, _inicio_mes_utc(anio_prev, mes_prev), _inicio_mes_utc(anio, mes))
    return caja, banco, configurado


def saldo_efectivo_a(db: Session, instante: datetime) -> dict:
    """Saldo de Caja Chica y Banco en un instante: el saldo con que empezó
    ese mes (ver _saldo_al_iniciar_mes) + lo que entró y salió de cada
    cuenta desde el día 1 (mismo criterio que calcular_liquidez)."""
    local = a_hora_local_naive(instante)
    caja, banco, configurado = _saldo_al_iniciar_mes(db, local.year, local.month)
    caja, banco = _sumar_movimientos(db, caja, banco, _inicio_mes_utc(local.year, local.month), instante)
    return {"caja_chica": q(caja), "banco": q(banco), "total": q(caja + banco),
            "saldo_mes_configurado": configurado}


# ---------------------------------------------------------------------------
# Estado de Resultados
# ---------------------------------------------------------------------------
def estado_resultados(db: Session, periodo: Periodo, inv: InventarioHistorico, partidas) -> dict:
    movs = _movimientos(db, periodo.inicio_utc, periodo.fin_utc)
    ingresos = [m for m in movs if m.tipo == "ingreso"]
    gastos = [m for m in movs if m.tipo == "gasto"]
    isv = _isv_de_movimientos(db, ingresos)

    def neto(lista):
        bruto = sum((to_decimal(m.monto) for m in lista), CERO)
        impuesto = sum((isv.get(m.id, CERO) for m in lista), CERO)
        return q(bruto), q(impuesto), q(bruto - impuesto)

    ventas_ordenes = [m for m in ingresos if m.categoria == CATEGORIA_VENTA_FACTURADA]
    ventas_pos = [m for m in ingresos if m.categoria == CATEGORIA_VENTA_POS]
    otros = [m for m in ingresos if m.categoria not in (CATEGORIA_VENTA_FACTURADA, CATEGORIA_VENTA_POS)]
    bruto_ord, isv_ord, neto_ord = neto(ventas_ordenes)
    bruto_pos, isv_pos, neto_pos = neto(ventas_pos)
    otros_ingresos = _agrupar(otros)
    total_otros = q(sum((v for _, v in otros_ingresos), CERO))
    total_ingresos = q(neto_ord + neto_pos + total_otros)

    inv_inicial = inv.valor_a(periodo.inicio_utc)["valor"]
    inv_final = inv.valor_a(periodo.fin_utc)["valor"]
    # Compras de mercadería = lo recibido con el módulo de Compras (al costo,
    # sin ISV, en la fecha en que llegó, aunque sea al crédito) + los egresos
    # «Compras»/«Proveedores» hechos a mano. Los pagos de una recepción no se
    # suman otra vez (ya están en lo recibido).
    from app.utils.compras import compras_recibidas
    compras = [m for m in gastos if m.categoria in CATEGORIAS_COMPRA_MERCADERIA and not m.recepcion_compra_id]
    recibidas = compras_recibidas(db, periodo.inicio_utc, periodo.fin_utc)
    total_compras = q(sum((to_decimal(m.monto) for m in compras), CERO) + recibidas["subtotal"])
    ajustes = reporte_ajustes(db, periodo.inicio_utc, periodo.fin_utc)["total"]
    ajustes_neto = q(ajustes["valor_neto"])  # + sobrante / - faltante, al costo
    costo_ventas = q(inv_inicial + total_compras - inv_final + ajustes_neto)
    utilidad_bruta = q(total_ingresos - costo_ventas)

    gastos_operacion = _agrupar([m for m in gastos if m.categoria not in CATEGORIAS_COMPRA_MERCADERIA and not m.recepcion_compra_id])
    total_gastos_caja = q(sum((v for _, v in gastos_operacion), CERO))
    depreciacion = depreciacion_del_periodo([p for p in partidas if p.tipo == "activo_fijo"], periodo)
    perdida_ajustes = q(-ajustes_neto)
    total_gastos = q(total_gastos_caja + depreciacion + perdida_ajustes)
    utilidad_neta = q(utilidad_bruta - total_gastos)

    lineas = [_l("Ingresos", tipo="titulo", nivel=0)]
    lineas.append(_l("Ventas de órdenes de servicio (sin ISV)", neto_ord))
    lineas.append(_l("Ventas del Punto de Venta (sin ISV)", neto_pos))
    for cat, monto in otros_ingresos:
        lineas.append(_l(f"{cat}", monto))
    lineas.append(_l("Total de ingresos", total_ingresos, "subtotal", 0))

    lineas.append(_l("Costo de ventas", tipo="titulo", nivel=0))
    lineas.append(_l("Inventario al inicio del período", inv_inicial))
    lineas.append(_l("(+) Compras de mercadería (recepciones de compra y egresos «Compras»/«Proveedores»)", total_compras))
    lineas.append(_l("(−) Inventario al final del período", -inv_final))
    if ajustes_neto:
        lineas.append(_l("(±) Faltantes/sobrantes de inventario (se muestran abajo, en gastos)", ajustes_neto))
    lineas.append(_l("Costo de ventas", costo_ventas, "subtotal", 0))
    lineas.append(_l("Utilidad bruta", utilidad_bruta, "total", 0))

    lineas.append(_l("Gastos de operación", tipo="titulo", nivel=0))
    for cat, monto in gastos_operacion:
        lineas.append(_l(cat, monto))
    if depreciacion:
        lineas.append(_l("Depreciación de activos fijos", depreciacion))
    if perdida_ajustes:
        lineas.append(_l("Pérdida por faltantes de inventario" if perdida_ajustes > 0 else "Sobrantes de inventario (ganancia)", perdida_ajustes))
    lineas.append(_l("Total de gastos de operación", total_gastos, "subtotal", 0))
    lineas.append(_l("Utilidad (o pérdida) neta del período", utilidad_neta, "total", 0,
                     "Antes del Impuesto Sobre la Renta."))

    notas = [
        f"El ISV cobrado en el período ({q(isv_ord + isv_pos):,.2f}) no es ingreso del negocio: se muestra como ISV por pagar en el Balance.",
        "El inventario se valora con el costo actual de cada producto.",
    ]
    if costo_ventas < 0:
        notas.append("El costo de ventas salió negativo: probablemente entró mercadería al inventario que no se registró como egreso «Compras» o «Proveedores».")

    return {
        "titulo": "Estado de Resultados", "periodo": periodo.texto, "lineas": lineas, "notas": notas,
        "total_ingresos": total_ingresos, "costo_ventas": costo_ventas, "utilidad_bruta": utilidad_bruta,
        "total_gastos": total_gastos, "utilidad_neta": utilidad_neta,
        "isv_cobrado": q(isv_ord + isv_pos), "ventas_brutas": q(bruto_ord + bruto_pos + total_otros),
        "inventario_inicial": inv_inicial, "inventario_final": inv_final, "compras": total_compras,
        "ajustes_inventario": ajustes_neto, "depreciacion": depreciacion,
        "margen_bruto": float((utilidad_bruta / total_ingresos * 100).quantize(Decimal("0.1"))) if total_ingresos else 0.0,
        "margen_neto": float((utilidad_neta / total_ingresos * 100).quantize(Decimal("0.1"))) if total_ingresos else 0.0,
    }


# ---------------------------------------------------------------------------
# Estado de Flujo de Efectivo (método directo)
# ---------------------------------------------------------------------------
def flujo_efectivo(db: Session, periodo: Periodo) -> dict:
    inicial = saldo_efectivo_a(db, periodo.inicio_utc)
    final = saldo_efectivo_a(db, periodo.fin_utc)
    movs = _movimientos(db, periodo.inicio_utc, periodo.fin_utc, incluir_depositos=True)
    depositos = [m for m in movs if m.categoria == CATEGORIA_DEPOSITO_BANCO]
    movs = [m for m in movs if m.categoria != CATEGORIA_DEPOSITO_BANCO]
    entradas = _agrupar([m for m in movs if m.tipo == "ingreso"])
    salidas_compras = q(sum((to_decimal(m.monto) for m in movs if m.tipo == "gasto" and m.categoria in CATEGORIAS_COMPRA_MERCADERIA), CERO))
    salidas = _agrupar([m for m in movs if m.tipo == "gasto" and m.categoria not in CATEGORIAS_COMPRA_MERCADERIA])
    total_entradas = q(sum((v for _, v in entradas), CERO))
    total_salidas = q(salidas_compras + sum((v for _, v in salidas), CERO))
    neto_operacion = q(total_entradas - total_salidas)
    esperado = q(inicial["total"] + neto_operacion)
    ajuste_saldos = q(final["total"] - esperado)
    traslados = q(sum((to_decimal(m.monto) for m in depositos if m.tipo == "gasto"), CERO))

    lineas = [_l("Efectivo al inicio del período (Caja Chica + Banco)", inicial["total"], "subtotal", 0)]
    lineas.append(_l("Actividades de operación", tipo="titulo", nivel=0))
    lineas.append(_l("Entradas de efectivo", tipo="titulo", nivel=1))
    for cat, monto in entradas:
        lineas.append(_l(cat, monto, nivel=2))
    lineas.append(_l("Total de entradas", total_entradas, "subtotal", 1))
    lineas.append(_l("Salidas de efectivo", tipo="titulo", nivel=1))
    if salidas_compras:
        lineas.append(_l("Compras de mercadería", -salidas_compras, nivel=2))
    for cat, monto in salidas:
        lineas.append(_l(cat, -monto, nivel=2))
    lineas.append(_l("Total de salidas", -total_salidas, "subtotal", 1))
    lineas.append(_l("Flujo neto de las actividades de operación", neto_operacion, "subtotal", 0))
    lineas.append(_l("Actividades de inversión", 0, "subtotal", 0, "Compras o ventas de equipo que se paguen desde Caja/Banco aparecen arriba en su categoría."))
    lineas.append(_l("Actividades de financiamiento", 0, "subtotal", 0, "Préstamos y aportes registrados en «Datos del balance» no mueven Caja ni Banco."))
    if ajuste_saldos:
        lineas.append(_l("Ajuste por saldos iniciales mensuales configurados en Caja", ajuste_saldos, "linea", 0,
                         "Diferencia entre el saldo con que se configuró algún mes y lo que venía del mes anterior."))
    lineas.append(_l("Efectivo al final del período (Caja Chica + Banco)", final["total"], "total", 0))
    lineas.append(_l("Caja Chica", final["caja_chica"], nivel=1))
    lineas.append(_l("Banco", final["banco"], nivel=1))

    notas = []
    if traslados:
        notas.append(f"Depósitos de Caja Chica a Banco en el período: {traslados:,.2f}. Son traslados entre cuentas: no cambian el total.")
    if not inicial["saldo_mes_configurado"] or not final["saldo_mes_configurado"]:
        notas.append("No hay ningún saldo inicial de mes configurado en Caja (Panel gerencial) antes de este período; el efectivo se calculó partiendo de 0.")
    return {
        "titulo": "Estado de Flujo de Efectivo", "periodo": periodo.texto, "lineas": lineas, "notas": notas,
        "efectivo_inicial": inicial["total"], "efectivo_final": final["total"],
        "neto_operacion": neto_operacion, "ajuste_saldos": ajuste_saldos,
    }


# ---------------------------------------------------------------------------
# Balance General
# ---------------------------------------------------------------------------
def _isv_por_pagar(db: Session, dia: date) -> Decimal:
    """ISV cobrado en el mes de la fecha de corte, hasta esa fecha. Se asume
    que el de los meses anteriores ya se declaró y pagó a la SAR."""
    inicio = inicio_dia_local_en_utc(dia.replace(day=1))
    fin = inicio_dia_local_en_utc(dia + timedelta(days=1))
    ingresos = [m for m in _movimientos(db, inicio, fin) if m.tipo == "ingreso"]
    # Menos el ISV pagado en las facturas de compra del mes (crédito fiscal).
    from app.utils.compras import compras_recibidas
    return q(sum(_isv_de_movimientos(db, ingresos).values(), CERO) - compras_recibidas(db, inicio, fin)["isv"])


def balance_general(db: Session, dia: date, inv: InventarioHistorico, partidas) -> dict:
    instante = inicio_dia_local_en_utc(dia + timedelta(days=1))
    efectivo = saldo_efectivo_a(db, instante)
    inventario = inv.valor_a(instante)["valor"]
    vigentes = [p for p in partidas if p.vigente_en(dia)]
    siguiente = dia + timedelta(days=1)

    def suma(tipo):
        return q(sum((to_decimal(p.monto) for p in vigentes if p.tipo == tipo), CERO))

    otros_activos = suma("otro_activo")
    fijos = [p for p in vigentes if p.tipo == "activo_fijo"]
    fijos_bruto = q(sum((to_decimal(p.monto) for p in fijos), CERO))
    dep_acumulada = q(sum((_depreciacion_acumulada(p, siguiente) for p in fijos), CERO))
    total_corriente = q(efectivo["caja_chica"] + efectivo["banco"] + inventario + otros_activos)
    total_activo = q(total_corriente + fijos_bruto - dep_acumulada)

    isv = _isv_por_pagar(db, dia)
    cxp, prestamos, otros_pasivos = suma("cuenta_por_pagar"), suma("prestamo"), suma("otro_pasivo")
    from app.utils.compras import por_pagar_a
    proveedores_compras = por_pagar_a(db, instante)
    total_pasivo = q(isv + cxp + proveedores_compras + otros_pasivos + prestamos)

    capital = q(sum((to_decimal(p.monto) for p in partidas if p.tipo == "capital" and p.fecha <= dia), CERO))
    retiros = q(sum((to_decimal(p.monto) for p in partidas if p.tipo == "retiro" and p.fecha <= dia), CERO))
    ejercicio = estado_resultados(db, Periodo(date(dia.year, 1, 1), dia), inv, partidas)
    utilidad_ejercicio = ejercicio["utilidad_neta"]
    total_patrimonio = q(total_activo - total_pasivo)
    acumulados = q(total_patrimonio - capital + retiros - utilidad_ejercicio)

    lineas = [_l("Activo", tipo="titulo", nivel=0), _l("Activo corriente", tipo="titulo", nivel=1)]
    lineas += [_l("Caja Chica", efectivo["caja_chica"], nivel=2), _l("Banco", efectivo["banco"], nivel=2),
               _l("Inventario de mercadería (al costo)", inventario, nivel=2)]
    if otros_activos:
        lineas.append(_l("Otros activos", otros_activos, nivel=2))
    lineas.append(_l("Total activo corriente", total_corriente, "subtotal", 1))
    lineas.append(_l("Activo no corriente", tipo="titulo", nivel=1))
    lineas.append(_l("Activos fijos (valor de compra)", fijos_bruto, nivel=2))
    lineas.append(_l("(−) Depreciación acumulada", -dep_acumulada, nivel=2))
    lineas.append(_l("Total activo no corriente", q(fijos_bruto - dep_acumulada), "subtotal", 1))
    lineas.append(_l("TOTAL ACTIVO", total_activo, "total", 0))

    lineas.append(_l("Pasivo", tipo="titulo", nivel=0))
    lineas.append(_l("ISV por pagar (del mes en curso, menos el ISV de las compras)", isv, nivel=1))
    if proveedores_compras:
        lineas.append(_l("Proveedores por pagar (compras recibidas al crédito)", proveedores_compras, nivel=1))
    if cxp:
        lineas.append(_l("Cuentas por pagar a proveedores", cxp, nivel=1))
    if otros_pasivos:
        lineas.append(_l("Otros pasivos", otros_pasivos, nivel=1))
    if prestamos:
        lineas.append(_l("Préstamos", prestamos, nivel=1))
    lineas.append(_l("TOTAL PASIVO", total_pasivo, "total", 0))

    lineas.append(_l("Patrimonio", tipo="titulo", nivel=0))
    lineas.append(_l("Capital aportado", capital, nivel=1))
    if retiros:
        lineas.append(_l("(−) Retiros del dueño", -retiros, nivel=1))
    lineas.append(_l(f"Utilidad (o pérdida) del ejercicio {dia.year}", utilidad_ejercicio, nivel=1))
    lineas.append(_l("Resultados acumulados y ajustes de apertura", acumulados, nivel=1, nota=
                     "Lo que no se explica con los datos registrados: utilidades de años anteriores y saldos con los que empezó el negocio."))
    lineas.append(_l("TOTAL PATRIMONIO", total_patrimonio, "total", 0))
    lineas.append(_l("TOTAL PASIVO + PATRIMONIO", q(total_pasivo + total_patrimonio), "total", 0))

    notas = ["El inventario se valora con el costo actual de cada producto.",
             "El ISV por pagar es solo el del mes de la fecha de corte; se asume que los meses anteriores ya se declararon."]
    if not partidas:
        notas.append("Todavía no hay datos registrados en «Datos del balance» (activos fijos, préstamos, capital...).")
    return {
        "titulo": "Balance General", "periodo": f"al {dia.strftime('%d/%m/%Y')}", "lineas": lineas, "notas": notas,
        "total_activo": total_activo, "total_pasivo": total_pasivo, "total_patrimonio": total_patrimonio,
        "capital": capital, "retiros": retiros, "utilidad_ejercicio": utilidad_ejercicio,
    }


# ---------------------------------------------------------------------------
# Estado de Cambios en el Patrimonio
# ---------------------------------------------------------------------------
def cambios_patrimonio(db: Session, periodo: Periodo, inv: InventarioHistorico, partidas, resultados: dict) -> dict:
    inicial = balance_general(db, periodo.desde - timedelta(days=1), inv, partidas)["total_patrimonio"]
    final = balance_general(db, periodo.hasta, inv, partidas)["total_patrimonio"]
    aportes = q(sum((to_decimal(p.monto) for p in partidas if p.tipo == "capital" and periodo.desde <= p.fecha <= periodo.hasta), CERO))
    retiros = q(sum((to_decimal(p.monto) for p in partidas if p.tipo == "retiro" and periodo.desde <= p.fecha <= periodo.hasta), CERO))
    utilidad = resultados["utilidad_neta"]
    otros = q(final - (inicial + aportes - retiros + utilidad))
    lineas = [
        _l("Patrimonio al inicio del período", inicial, "subtotal", 0),
        _l("(+) Aportes de capital", aportes),
        _l("(−) Retiros del dueño", -retiros),
        _l("(+/−) Utilidad o pérdida neta del período", utilidad),
        _l("(+/−) Otros cambios (activos, deudas y saldos registrados o corregidos)", otros, nota=
           "Por ejemplo un activo fijo o un préstamo registrado en el período, o un cambio en el saldo inicial de Caja."),
        _l("Patrimonio al final del período", final, "total", 0),
    ]
    return {"titulo": "Estado de Cambios en el Patrimonio", "periodo": periodo.texto, "lineas": lineas, "notas": [],
            "inicial": inicial, "final": final}


# ---------------------------------------------------------------------------
# Todo junto
# ---------------------------------------------------------------------------
def generar_estados(db: Session, periodo: Periodo) -> dict:
    inv = InventarioHistorico(db)
    partidas = db.query(PartidaBalance).order_by(PartidaBalance.fecha).all()
    resultados = estado_resultados(db, periodo, inv, partidas)
    return {
        "periodo": periodo,
        "resultados": resultados,
        "flujo": flujo_efectivo(db, periodo),
        "balance": balance_general(db, periodo.hasta, inv, partidas),
        "patrimonio": cambios_patrimonio(db, periodo, inv, partidas, resultados),
    }
