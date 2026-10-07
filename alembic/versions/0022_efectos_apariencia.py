"""Agrega preferencias de "efectos de ventana" por usuario, parte de
Apariencia: estilo con que se cierran los modales (Genie/Escala/Succión,
aproximaciones con CSS/JS de los efectos de minimizar de macOS), si se
anima el rebote al abrirlos, la "magnificación" al pasar el mouse sobre la
mascota flotante (como el Dock de macOS) y un efecto "Liquid Glass"
independiente del modo de color (Oscuro/Claro/Vidrio).

Cada preferencia es individual (se puede prender/apagar por separado) y
es personal de cada usuario, igual que el resto de Apariencia. Los
valores por defecto reproducen lo que el sistema ya hace hoy (ventanas
con una animación de escala simple al abrir/cerrar, mascota con su
magnificación ya existente) excepto Liquid Glass, que empieza apagado
para no cambiarle la apariencia a nadie sin que la elija.

Revision ID: 0022_efectos_apariencia
Revises: 0021_fix_fk_factura_id
Create Date: 2026-10-06
"""
from alembic import op
import sqlalchemy as sa

revision = "0022_efectos_apariencia"
down_revision = "0021_fix_fk_factura_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("usuarios") as batch_op:
        batch_op.add_column(
            sa.Column("efecto_cierre_ventana", sa.String(20), nullable=False, server_default="escala")
        )
        batch_op.add_column(
            sa.Column("animar_apertura_ventana", sa.Boolean(), nullable=False, server_default=sa.true())
        )
        batch_op.add_column(
            sa.Column("dock_magnificacion", sa.Boolean(), nullable=False, server_default=sa.true())
        )
        batch_op.add_column(
            sa.Column("liquid_glass", sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    with op.batch_alter_table("usuarios") as batch_op:
        batch_op.drop_column("liquid_glass")
        batch_op.drop_column("dock_magnificacion")
        batch_op.drop_column("animar_apertura_ventana")
        batch_op.drop_column("efecto_cierre_ventana")
