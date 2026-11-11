"""Preferencias de notificación de cada usuario (informe beta del 2026-10-06).

Revision ID: a2c4e6f8b0d1
Revises: e1b5c9d3a7f2
Create Date: 2026-11-11

``notify_email`` apaga el envío automático del dossier por correo; ``notify_browser`` activa el
aviso del sistema operativo. Ambas activadas por omisión. Se reutiliza la tupla de
``schema_patches`` (DDL idempotente).
"""
from __future__ import annotations

from sqlalchemy import text

from alembic import op

revision = "a2c4e6f8b0d1"
down_revision = "e1b5c9d3a7f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from dossier.db.schema_patches import USER_NOTIFY_PATCHES

    for sql in USER_NOTIFY_PATCHES:
        op.execute(text(sql))


def downgrade() -> None:
    op.execute(text("ALTER TABLE users DROP COLUMN IF EXISTS notify_browser"))
    op.execute(text("ALTER TABLE users DROP COLUMN IF EXISTS notify_email"))
