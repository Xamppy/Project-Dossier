"""S6.2: `dossier_access_links`, enlaces de un solo uso para leer un dossier desde el correo.

Revision ID: b4e8f2a6c0d3
Revises: a9d3e5f7b1c4
Create Date: 2026-11-10

Cada correo lleva un enlace por dossier que abre solo ese dossier, en solo lectura y sin iniciar
sesión. Se gasta al canjearlo y vence en 24 horas. La tabla guarda solo el SHA-256 del token y
cae con el dossier (``ON DELETE CASCADE``).

Igual que las revisiones anteriores, se reutiliza la tupla de ``schema_patches``, que la app
también aplica al arrancar (DDL idempotente).
"""
from __future__ import annotations

from sqlalchemy import text

from alembic import op

revision = "b4e8f2a6c0d3"
down_revision = "a9d3e5f7b1c4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from dossier.db.schema_patches import ACCESS_LINK_PATCHES

    for sql in ACCESS_LINK_PATCHES:
        op.execute(text(sql))


def downgrade() -> None:
    op.execute(text("DROP TABLE IF EXISTS dossier_access_links"))
