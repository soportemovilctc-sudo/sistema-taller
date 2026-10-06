"""La contabilidad (Ingresos/Caja/Utilidad Neta/Contabilidad) deja de sumar
las ordenes en si (se contaban dos veces: al agregar el repuesto/servicio,
y otra vez al cobrarlo) y pasa a sumar solo las Facturas que se emitan.

- Agrega "excluir_de_contabilidad" a movimientos_financieros: las filas ya
  existentes de las categorias viejas (Venta de repuesto/servicio (orden),
  Abono de orden, Cancelacion de orden (automatico), Reversion por orden
  cancelada, Correccion de repuesto/servicio (orden)) se marcan con este
  campo en vez de borrarse, para que dejen de sumar pero el historial real
  nunca se pierda.
- Agrega "factura_id" a movimientos_financieros, para enlazar el ingreso
  nuevo con la Factura que lo genero (ver CATEGORIA_VENTA_FACTURADA).
- Por cada Factura YA EMITIDA (no anulada) de una orden, que todavia no
  tiene su ingreso contable (porque antes una Factura era solo un
  documento, nunca generaba un movimiento), se crea ahora ese ingreso con
  la fecha de la factura, para que el historial de meses anteriores no
  quede en cero.

IMPORTANTE: agregar las columnas nuevas (lo que el codigo de la aplicacion
realmente necesita para poder arrancar) NUNCA debe fallar por datos viejos
raros en produccion. Por eso la parte 1 (marcar categorias excluidas) y la
parte 2 (el ingreso retroactivo por factura, fila por fila) corren cada una
en su propio SAVEPOINT: si una fila puntual tiene datos incompletos o
inesperados, esa fila se omite (y se deja un aviso en el log de Railway)
en vez de tumbar toda la migracion -- y con ella, toda la aplicacion.

Revision ID: 0020_facturas_contabilidad
Revises: 0019_nomina_renombrar_deposito
Create Date: 2026-10-06
"""
from datetime import datetime

from alembic import op
import sqlalchemy as sa

revision = "0020_facturas_contabilidad"
down_revision = "0019_nomina_renombrar_deposito"
branch_labels = None
depends_on = None


def _como_datetime(valor):
    """SQLite devuelve la fecha como texto crudo en una consulta SQL
    directa (en vez de un datetime de Python, como sí hace PostgreSQL vía
    psycopg2); esto la normaliza en ambos casos."""
    if valor is None or isinstance(valor, datetime):
        return valor
    texto = str(valor)
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(texto, fmt)
        except ValueError:
            continue
    return valor


CATEGORIAS_ORDEN_EXCLUIDAS_CONTABILIDAD = [
    "Venta de repuesto (orden)", "Venta de servicio (orden)",
    "Abono de orden", "Cancelación de orden (automático)",
    "Reversión por orden cancelada",
    "Corrección de repuesto (orden)", "Corrección de servicio (orden)",
]
CATEGORIA_VENTA_FACTURADA = "Venta facturada (orden)"


def upgrade() -> None:
    with op.batch_alter_table("movimientos_financieros") as batch_op:
        batch_op.add_column(sa.Column(
            "excluir_de_contabilidad", sa.Boolean(), nullable=False, server_default=sa.false()
        ))
        batch_op.add_column(sa.Column("factura_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_movimientos_financieros_factura_id",
            "movimientos_financieros", ["factura_id"], ["id"]
        )

    conn = op.get_bind()

    # 1) Las filas viejas de ordenes: se quedan en la base de datos tal
    #    cual, solo se marcan para que dejen de sumar en la contabilidad.
    #    Va en su propio SAVEPOINT para que, si llegara a fallar, no afecte
    #    las columnas que ya se agregaron arriba.
    try:
        with conn.begin_nested():
            conn.execute(sa.text(
                "UPDATE movimientos_financieros SET excluir_de_contabilidad = true "
                "WHERE categoria IN :categorias"
            ).bindparams(sa.bindparam("categorias", expanding=True)), {
                "categorias": CATEGORIAS_ORDEN_EXCLUIDAS_CONTABILIDAD,
            })
    except Exception as exc:
        print(
            "[0020_facturas_contabilidad] AVISO: no se pudieron excluir las "
            f"categorias viejas de ordenes ({exc!r}). Revisar manualmente."
        )

    # 2) Por cada factura ya emitida (no anulada) de una orden, se crea el
    #    ingreso contable que nunca existio (antes la Factura era solo un
    #    documento). Las facturas de POS (venta_id, sin orden_id) no se
    #    tocan: esas ya generan su ingreso al momento de la venta.
    #    Se procesa factura por factura, cada una en su propio SAVEPOINT:
    #    una factura vieja con datos incompletos (total/fecha nulos, etc.)
    #    se omite con un aviso, en vez de bloquear a las demas.
    try:
        with conn.begin_nested():
            facturas = conn.execute(sa.text(
                "SELECT f.id AS factura_id, f.numero_documento, f.total, f.fecha_emision, "
                "       f.usuario_nombre, o.numero_orden "
                "FROM facturas f "
                "JOIN ordenes_servicio o ON o.id = f.orden_id "
                "WHERE f.orden_id IS NOT NULL AND f.anulada = false"
            )).mappings().all()
    except Exception as exc:
        print(
            "[0020_facturas_contabilidad] AVISO: no se pudo leer la lista de "
            f"facturas a respaldar ({exc!r}). No se crea ningun ingreso retroactivo."
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
                "[0020_facturas_contabilidad] AVISO: se omitio el ingreso retroactivo "
                f"de la factura id={f.get('factura_id')} numero={f.get('numero_documento')} "
                f"({exc!r})."
            )

    print(
        f"[0020_facturas_contabilidad] ingresos retroactivos creados: {insertadas}, "
        f"omitidos por datos incompletos: {omitidas}."
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text(
        "DELETE FROM movimientos_financieros WHERE categoria = :categoria AND factura_id IS NOT NULL"
    ), {"categoria": CATEGORIA_VENTA_FACTURADA})
    conn.execute(sa.text(
        "UPDATE movimientos_financieros SET excluir_de_contabilidad = false "
        "WHERE categoria IN :categorias"
    ).bindparams(sa.bindparam("categorias", expanding=True)), {
        "categorias": CATEGORIAS_ORDEN_EXCLUIDAS_CONTABILIDAD,
    })
    with op.batch_alter_table("movimientos_financieros") as batch_op:
        batch_op.drop_constraint("fk_movimientos_financieros_factura_id", type_="foreignkey")
        batch_op.drop_column("factura_id")
        batch_op.drop_column("excluir_de_contabilidad")
