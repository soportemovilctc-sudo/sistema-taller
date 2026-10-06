"""Corrige un error en la migracion anterior (0020): la llave foranea de
movimientos_financieros.factura_id quedo apuntando por error a la misma
tabla movimientos_financieros(id) en vez de a facturas(id).

Efecto de ese error en produccion:
  - Generar una factura NUEVA fallaba casi siempre (pantalla en blanco):
    el id de la factura casi nunca coincide con un id ya existente en
    movimientos_financieros, asi que la base de datos rechazaba la
    insercion del ingreso -- y como todo pasa en una sola transaccion,
    tambien se perdia la factura misma, como si "no se hubiera creado".
  - Parte del respaldo historico de la migracion 0020 (el ingreso
    retroactivo por cada factura ya emitida) se omitio por el mismo
    motivo para las facturas cuyo id no coincidia con ningun id de
    movimientos_financieros -- de ahi que varias facturas viejas no
    quedaran contadas como ingreso.

Esta migracion:
  1) Corrige la llave foranea para que apunte a facturas(id).
  2) Vuelve a intentar el respaldo historico SOLO para las facturas que
     todavia no tienen su ingreso (es segura de correr otra vez: no
     duplica nada, cada factura se procesa en su propio SAVEPOINT igual
     que en 0020, asi que un dato viejo raro en una factura puntual se
     omite con un aviso en vez de afectar a las demas).

No se borra ni se modifica ningun dato existente de ordenes ni facturas.

Revision ID: 0021_fix_fk_factura_id
Revises: 0020_facturas_contabilidad
Create Date: 2026-10-06
"""
from datetime import datetime

from alembic import op
import sqlalchemy as sa

revision = "0021_fix_fk_factura_id"
down_revision = "0020_facturas_contabilidad"
branch_labels = None
depends_on = None

CATEGORIA_VENTA_FACTURADA = "Venta facturada (orden)"


def _como_datetime(valor):
    if valor is None or isinstance(valor, datetime):
        return valor
    texto = str(valor)
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(texto, fmt)
        except ValueError:
            continue
    return valor


def upgrade() -> None:
    # 1) Corrige la llave foranea: debe apuntar a facturas(id), no a
    #    movimientos_financieros(id).
    with op.batch_alter_table("movimientos_financieros") as batch_op:
        batch_op.drop_constraint("fk_movimientos_financieros_factura_id", type_="foreignkey")
        batch_op.create_foreign_key(
            "fk_movimientos_financieros_factura_id",
            "facturas", ["factura_id"], ["id"],
        )

    conn = op.get_bind()

    # 2) Reintenta el ingreso retroactivo solo para las facturas que todavia
    #    no tienen uno (la FK rota de 0020 pudo haber bloqueado varias).
    #    Factura por factura, cada una en su propio SAVEPOINT: si alguna
    #    sigue teniendo datos incompletos o raros, se omite con un aviso
    #    en vez de afectar a las demas.
    try:
        with conn.begin_nested():
            facturas = conn.execute(sa.text(
                "SELECT f.id AS factura_id, f.numero_documento, f.total, f.fecha_emision, "
                "       f.usuario_nombre, o.numero_orden "
                "FROM facturas f "
                "JOIN ordenes_servicio o ON o.id = f.orden_id "
                "WHERE f.orden_id IS NOT NULL AND f.anulada = false "
                "  AND NOT EXISTS ("
                "    SELECT 1 FROM movimientos_financieros m "
                "    WHERE m.factura_id = f.id"
                "  )"
            )).mappings().all()
    except Exception as exc:
        print(
            "[0021_fix_fk_factura_id] AVISO: no se pudo leer la lista de "
            f"facturas pendientes de respaldo ({exc!r})."
        )
        facturas = []

    insertadas = 0
    omitidas = 0
    for f in facturas:
        try:
            with conn.begin_nested():
                conn.execute(sa.text(
                    "INSERT INTO movimientos_financieros "
                    "(tipo, categoria, monto, fecha, descripcion, usuario_nombre, "
                    " referencia, cuenta, excluir_de_contabilidad, factura_id) "
                    "VALUES ('ingreso', :categoria, :monto, :fecha, :descripcion, "
                    " :usuario_nombre, :referencia, 'caja_chica', false, :factura_id)"
                ), {
                    "categoria": CATEGORIA_VENTA_FACTURADA,
                    "monto": f["total"] if f["total"] is not None else 0,
                    "fecha": _como_datetime(f["fecha_emision"]) or datetime.utcnow(),
                    "descripcion": f"Factura {f['numero_documento']} - Orden {f['numero_orden'] or ''}".strip(),
                    "usuario_nombre": f["usuario_nombre"],
                    "referencia": f["numero_orden"] or "",
                    "factura_id": f["factura_id"],
                })
            insertadas += 1
        except Exception as exc:
            omitidas += 1
            print(
                "[0021_fix_fk_factura_id] AVISO: se omitio el ingreso retroactivo "
                f"de la factura id={f.get('factura_id')} numero={f.get('numero_documento')} "
                f"({exc!r})."
            )

    print(
        f"[0021_fix_fk_factura_id] ingresos retroactivos creados ahora: {insertadas}, "
        f"omitidos por datos incompletos: {omitidas}."
    )


def downgrade() -> None:
    with op.batch_alter_table("movimientos_financieros") as batch_op:
        batch_op.drop_constraint("fk_movimientos_financieros_factura_id", type_="foreignkey")
        batch_op.create_foreign_key(
            "fk_movimientos_financieros_factura_id",
            "movimientos_financieros", ["factura_id"], ["id"],
        )
