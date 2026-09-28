"""agrega preferencias de apariencia por usuario (tema_modo, tema_acento,
tema_color_personalizado, mascota): para que cada quien personalice su
propio tema de colores y elija su mascota (panda/león/ratón), guardado en
su cuenta para que lo mantenga en cualquier dispositivo

Revision ID: 0013_apariencia_usuario
Revises: 0012_notificado_listo
Create Date: 2026-09-28
"""
from alembic import op
import sqlalchemy as sa

revision = "0013_apariencia_usuario"
down_revision = "0012_notificado_listo"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Los valores por defecto (tema_modo="oscuro", tema_acento="azul") son
    # exactamente los colores que el sistema ya usa hoy, para que a nadie
    # se le cambie la apariencia sin que la elija en "Apariencia".
    with op.batch_alter_table("usuarios") as batch_op:
        batch_op.add_column(
            sa.Column("tema_modo", sa.String(20), nullable=False, server_default="oscuro")
        )
        batch_op.add_column(
            sa.Column("tema_acento", sa.String(30), nullable=False, server_default="azul")
        )
        batch_op.add_column(
            sa.Column("tema_color_personalizado", sa.String(20), nullable=True)
        )
        batch_op.add_column(
            sa.Column("mascota", sa.String(20), nullable=False, server_default="panda")
        )


def downgrade() -> None:
    with op.batch_alter_table("usuarios") as batch_op:
        batch_op.drop_column("mascota")
        batch_op.drop_column("tema_color_personalizado")
        batch_op.drop_column("tema_acento")
        batch_op.drop_column("tema_modo")
