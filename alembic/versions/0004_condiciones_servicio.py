"""agrega condiciones_servicio editable a configuracion

Revision ID: 0004_condiciones_servicio
Revises: 0003_servicios_rapidos
Create Date: 2026-09-18

"""
from alembic import op
import sqlalchemy as sa

revision = "0004_condiciones_servicio"
down_revision = "0003_servicios_rapidos"
branch_labels = None
depends_on = None

DEFAULT_TEXTO = (
    "Equipos Mojados: No cuentan con garantía debido a que el daño puede ser progresivo.\n"
    "Equipos Apagados: Se reciben bajo responsabilidad del cliente, ya que no se pueden "
    "verificar otras fallas hasta que enciendan; cualquier daño extra se cobrará por separado.\n"
    "Privacidad: Se garantiza la total confidencialidad de su información personal.\n"
    "Tiempo Límite: Tiene un plazo máximo de 30 días para retirar su equipo después de ser "
    "notificado, de lo contrario este pasará a ser propiedad de la empresa para cubrir costos "
    "de repuestos, mano de obra y almacenamiento."
)


def upgrade() -> None:
    op.add_column(
        "configuracion",
        sa.Column("condiciones_servicio", sa.Text, server_default=DEFAULT_TEXTO),
    )


def downgrade() -> None:
    op.drop_column("configuracion", "condiciones_servicio")
