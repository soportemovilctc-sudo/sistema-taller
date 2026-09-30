"""agrega credenciales de Twilio (twilio_account_sid, twilio_auth_token,
twilio_whatsapp_from) y notificar_whatsapp_automatico a configuracion:
para poder mandar automáticamente el mensaje de "tu equipo está listo"
por WhatsApp cuando una orden pasa a LISTO PARA ENTREGAR

Revision ID: 0014_notificaciones_whatsapp
Revises: 0013_apariencia_usuario
Create Date: 2026-09-30
"""
from alembic import op
import sqlalchemy as sa

revision = "0014_notificaciones_whatsapp"
down_revision = "0013_apariencia_usuario"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Todos vacíos/activado por defecto: mientras no se llenen las
    # credenciales en Configuración > Notificaciones, el envío automático
    # simplemente no hace nada (no rompe el flujo existente).
    with op.batch_alter_table("configuracion") as batch_op:
        batch_op.add_column(sa.Column("twilio_account_sid", sa.String(80), nullable=True, server_default=""))
        batch_op.add_column(sa.Column("twilio_auth_token", sa.String(120), nullable=True, server_default=""))
        batch_op.add_column(sa.Column("twilio_whatsapp_from", sa.String(40), nullable=True, server_default=""))
        batch_op.add_column(
            sa.Column("notificar_whatsapp_automatico", sa.Boolean(), nullable=False, server_default=sa.true())
        )


def downgrade() -> None:
    with op.batch_alter_table("configuracion") as batch_op:
        batch_op.drop_column("notificar_whatsapp_automatico")
        batch_op.drop_column("twilio_whatsapp_from")
        batch_op.drop_column("twilio_auth_token")
        batch_op.drop_column("twilio_account_sid")
