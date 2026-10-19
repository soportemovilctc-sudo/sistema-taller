"""Cuadre del banco del sistema con el saldo real del banco.

1. pistas(): busca de dónde puede salir la diferencia (comisiones del POS,
   transferencias sin confirmar, posibles duplicados, un movimiento por el
   mismo monto de la diferencia, el saldo inicial del mes).
2. cuadrar(): registra el ajuste en Banco (salida si el sistema tiene de
   más, entrada si tiene de menos) con su asiento contable, para que el
   saldo del sistema quede igual al real en esa fecha.
3. deshacer(): anula un cuadre (no se borra: deja de contar)."""
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import MovimientoFinanciero, SaldoInicialMensual, CATEGORIA_DEPOSITO_BANCO
from app.utils.calculations import to_decimal
from app.utils.caja_calculos import CUENTA_BANCO
from app.utils.estado_cuenta_banco import clasificar
from app.utils.turnos_caja import inicio_dia_local_en_utc, a_hora_local, hoy_local

CERO = Decimal("0.00")
CENT = Decimal("0.01")
REFERENCIA_CUADRE = "Cuadre de banco"
MOTIVO_COMISIONES = "Comisiones POS / tarjeta"
MOTIVO_CARGOS = "Cargos y comisiones bancarias"
MOTIVO_SIN_IDENTIFICAR = "Ajuste de conciliación bancaria"
MOTIVO_INGRESO = "Ingreso al banco no registrado"
MOTIVOS_SALIDA = (MOTIVO_COMISIONES, MOTIVO_CARGOS, MOTIVO_SIN_IDENTIFICAR)
MOTIVOS_ENTRADA = (MOTIVO_INGRESO, MOTIVO_SIN_IDENTIFICAR)


def q(v) -> Decimal:
    return to_decimal(v or 0).quantize(CENT)


def fin_del_dia_utc(dia: date) -> datetime:
    return inicio_dia_local_en_utc(dia + timedelta(days=1))


def saldo_sistema(db: Session, dia: date) -> Decimal:
    from app.utils.estados_financieros import saldo_efectivo_a
    return q(saldo_efectivo_a(db, fin_del_dia_utc(dia))["banco"])


def _movs_banco(db, inicio, fin):
    return (db.query(MovimientoFinanciero)
            .filter(MovimientoFinanciero.cuenta == CUENTA_BANCO,
                    MovimientoFinanciero.excluir_de_contabilidad == False,  # noqa: E712
                    MovimientoFinanciero.fecha >= inicio, MovimientoFinanciero.fecha < fin)
            .order_by(MovimientoFinanciero.fecha).all())


def _fila(m):
    return {"id": m.id, "fecha": a_hora_local(m.fecha), "tipo": "Entrada" if m.tipo == "ingreso" else "Salida",
            "categoria": m.categoria or "", "metodo": m.metodo_pago or "", "monto": q(m.monto),
            "detalle": ((m.cliente_nombre or "").strip() or (m.descripcion or "").strip())[:90],
            "referencia": " · ".join(x for x in ((m.num_referencia or "").strip(), (m.referencia or "").strip()) if x),
            "usuario": m.usuario_nombre or ""}


def pistas(db: Session, dia: date, diferencia: Decimal) -> dict:
    """Todo lo del mes de `dia` hasta ese día. diferencia = sistema - real."""
    desde = dia.replace(day=1)
    inicio, fin = inicio_dia_local_en_utc(desde), fin_del_dia_utc(dia)
    movs = _movs_banco(db, inicio, fin)
    entradas = [m for m in movs if m.tipo == "ingreso"]

    tarjeta = [m for m in entradas if clasificar(m) == "tarjeta"]
    total_tarjeta = q(sum((to_decimal(m.monto) for m in tarjeta), CERO))
    pct_tarjeta = (diferencia / total_tarjeta * 100).quantize(Decimal("0.01")) if total_tarjeta and diferencia > 0 else None

    pendientes = [m for m in entradas if m.estado_conciliacion == "pendiente"]
    total_pendientes = q(sum((to_decimal(m.monto) for m in pendientes), CERO))

    # posibles duplicados: misma referencia de transferencia, o mismo monto el mismo día
    por_ref, por_dia_monto = defaultdict(list), defaultdict(list)
    for m in entradas:
        if m.categoria == CATEGORIA_DEPOSITO_BANCO:
            continue
        ref = (m.num_referencia or "").strip().lower()
        if ref:
            por_ref[ref].append(m)
        por_dia_monto[(a_hora_local(m.fecha).date(), q(m.monto))].append(m)
    duplicados, vistos = [], set()
    for grupo in list(por_ref.values()) + list(por_dia_monto.values()):
        ids = tuple(sorted(m.id for m in grupo))
        if len(grupo) > 1 and ids not in vistos:
            vistos.add(ids)
            duplicados.append({"motivo": "Misma referencia de transferencia" if (grupo[0].num_referencia or "").strip() and
                               len({(x.num_referencia or "").strip().lower() for x in grupo}) == 1 else "Mismo monto el mismo día",
                               "filas": [_fila(m) for m in grupo],
                               "de_mas": q(sum((to_decimal(m.monto) for m in grupo[1:]), CERO))})
    duplicados.sort(key=lambda g: -g["de_mas"])

    objetivo = abs(q(diferencia))
    exactos = [_fila(m) for m in movs if abs(q(m.monto) - objetivo) <= CENT] if objetivo else []
    # dos entradas que juntas suman la diferencia (solo si no son demasiadas)
    pares = []
    if objetivo and len(entradas) <= 1500:
        montos = {}
        for m in entradas:
            montos.setdefault(q(m.monto), []).append(m)
        vistos_p = set()
        for m in entradas:
            resto = q(objetivo - q(m.monto))
            for o in montos.get(resto, []):
                if o.id != m.id:
                    clave = tuple(sorted((m.id, o.id)))
                    if clave not in vistos_p:
                        vistos_p.add(clave)
                        pares.append([_fila(m), _fila(o)])
            if len(pares) >= 15:
                break

    fila_mes = db.query(SaldoInicialMensual).filter(SaldoInicialMensual.anio == desde.year, SaldoInicialMensual.mes == desde.month).first()
    return {
        "desde": desde, "hasta": dia, "n_movimientos": len(movs),
        "total_tarjeta": total_tarjeta, "n_tarjeta": len(tarjeta), "pct_tarjeta": pct_tarjeta,
        "pendientes": [_fila(m) for m in pendientes][:60], "n_pendientes": len(pendientes), "total_pendientes": total_pendientes,
        "duplicados": duplicados[:40], "exactos": exactos[:20], "pares": pares,
        "saldo_inicial_mes": q(fila_mes.saldo_inicial_banco) if fila_mes else None,
        "saldo_inicio_calculado": saldo_sistema(db, desde - timedelta(days=1)) if not fila_mes else None,
    }


def cuadres(db: Session) -> list:
    return (db.query(MovimientoFinanciero).filter(MovimientoFinanciero.referencia == REFERENCIA_CUADRE)
            .order_by(MovimientoFinanciero.fecha.desc()).limit(50).all())


def cuadrar(db: Session, dia: date, saldo_real: Decimal, motivo: str, nota: str, usuario_nombre: str):
    """Devuelve (movimiento, diferencia, error)."""
    from app.utils.libro_diario import registrar_asiento, CTA_BANCO, CTA_GASTOS_OPERATIVOS, CTA_OTROS_INGRESOS
    if dia > hoy_local():
        return None, CERO, "La fecha no puede ser futura."
    saldo_real = q(saldo_real)
    sistema = saldo_sistema(db, dia)
    diferencia = q(sistema - saldo_real)
    if diferencia == 0:
        return None, diferencia, "El banco del sistema ya cuadra con ese saldo."
    tipo = "gasto" if diferencia > 0 else "ingreso"
    validos = MOTIVOS_SALIDA if tipo == "gasto" else MOTIVOS_ENTRADA
    if motivo not in validos:
        motivo = MOTIVO_SIN_IDENTIFICAR
    monto = abs(diferencia)
    # al final de ese día (o ahora, si es hoy), para que cuente en el saldo de ese día
    fecha = min(datetime.utcnow(), fin_del_dia_utc(dia) - timedelta(seconds=1))
    descripcion = (f"Cuadre con el saldo real del banco al {dia.strftime('%d/%m/%Y')}: real L {saldo_real:,.2f}, "
                   f"sistema L {sistema:,.2f}" + (f". {nota.strip()}" if nota.strip() else ""))
    mov = MovimientoFinanciero(tipo=tipo, categoria=motivo, monto=monto, descripcion=descripcion, usuario_nombre=usuario_nombre,
                               referencia=REFERENCIA_CUADRE, cuenta=CUENTA_BANCO, metodo_pago=None, fecha=fecha)
    db.add(mov)
    db.flush()
    mov.turno_caja_id = None  # es del banco, no de la caja de la cajera
    db.flush()
    try:
        lineas = ([(CTA_GASTOS_OPERATIVOS, monto, 0), (CTA_BANCO, 0, monto)] if tipo == "gasto"
                  else [(CTA_BANCO, monto, 0), (CTA_OTROS_INGRESOS, 0, monto)])
        registrar_asiento(db, fecha, f"{motivo} - cuadre de banco", "cuadre_banco", lineas,
                          referencia=REFERENCIA_CUADRE, movimiento_financiero_id=mov.id, usuario_nombre=usuario_nombre)
    except Exception:  # noqa: BLE001 - el libro diario nunca bloquea
        pass
    return mov, diferencia, None


def deshacer(db: Session, mov: MovimientoFinanciero, usuario_nombre: str):
    from app.utils.libro_diario import eliminar_asiento_de_movimiento
    if not mov or mov.referencia != REFERENCIA_CUADRE or mov.excluir_de_contabilidad:
        return "Ese cuadre no existe o ya fue anulado."
    mov.excluir_de_contabilidad = True
    mov.descripcion = f"{mov.descripcion} (ANULADO por {usuario_nombre} el {a_hora_local(datetime.utcnow()).strftime('%d/%m/%Y %I:%M %p')})"
    eliminar_asiento_de_movimiento(db, mov.id)
    return None
