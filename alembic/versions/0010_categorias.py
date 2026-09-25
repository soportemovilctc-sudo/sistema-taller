"""crea catalogo de categorias de inventario y corrige 'PANTALLAS' a 'PANTALLA'

Revision ID: 0010_categorias
Revises: 0009_caja_producto
Create Date: 2026-09-25
"""
from alembic import op
import sqlalchemy as sa

revision = "0010_categorias"
down_revision = "0009_caja_producto"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "categorias",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("nombre", sa.String(length=80), nullable=False, unique=True),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("creado_en", sa.DateTime(), nullable=True),
    )

    # Unifica la categoria duplicada "PANTALLAS" -> "PANTALLA" en los
    # productos que ya existen, antes de sembrar el catalogo.
    op.execute("UPDATE productos SET categoria = 'PANTALLA' WHERE categoria = 'PANTALLAS'")

    # Siembra el catalogo de categorias con las que ya se venian usando en
    # el inventario, para no perder ninguna al pasar a lista controlada.
    # (creado_en se deja NULL aqui; es solo informativo).
    op.execute(
        """
        INSERT INTO categorias (nombre, activo)
        SELECT DISTINCT categoria, TRUE
        FROM productos
        WHERE categoria IS NOT NULL AND categoria <> ''
        """
    )


def downgrade() -> None:
    op.drop_table("categorias")
