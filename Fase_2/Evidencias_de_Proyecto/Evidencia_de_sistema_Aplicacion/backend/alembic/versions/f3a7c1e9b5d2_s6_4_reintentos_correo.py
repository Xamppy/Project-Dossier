"""S6.4: `dossier_email_retries`, los envíos automáticos de correo en espera de reintento.

Revision ID: f3a7c1e9b5d2
Revises: e8b1f4a6c2d9
Create Date: 2026-11-10

Si los tres intentos seguidos de un envío automático fallan por algo pasajero, el envío queda
aquí y un proceso de fondo lo reintenta cada 10 minutos, hasta 1 hora. La tabla no guarda la
dirección del destinatario ni el contenido del correo.

Igual que las revisiones anteriores, se reutiliza la tupla de ``schema_patches``, que la app
también aplica al arrancar (DDL idempotente).
"""
from __future__ import annotations

from sqlalchemy import text

from alembic import op

revision = "f3a7c1e9b5d2"
down_revision = "e8b1f4a6c2d9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from dossier.db.schema_patches import EMAIL_RETRY_PATCHES

    for sql in EMAIL_RETRY_PATCHES:
        op.execute(text(sql))


def downgrade() -> None:
    op.execute(text("DROP TABLE IF EXISTS dossier_email_retries"))
