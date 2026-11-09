"""S3.9: `refresh_tokens.revoked_at` para la rotación de tokens de renovación.

Revision ID: d5a9e3c7f2b8
Revises: c4d8a2f6b1e9
Create Date: 2026-11-02

La tabla `refresh_tokens` existe desde la línea base, pero nadie la usaba. La rotación
necesita saber cuándo se revocó cada token: dentro de una ventana corta, que otra pestaña
use el token recién rotado es una carrera normal; fuera de ella, es reutilización de un
token robado y se cierran todas las sesiones del usuario.

Igual que las revisiones anteriores, se reutiliza la tupla de ``schema_patches``, que la
app también aplica al arrancar (DDL idempotente).
"""
from __future__ import annotations

from sqlalchemy import text

from alembic import op

revision = "d5a9e3c7f2b8"
down_revision = "c4d8a2f6b1e9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from dossier.db.schema_patches import REFRESH_TOKEN_PATCHES

    for sql in REFRESH_TOKEN_PATCHES:
        op.execute(text(sql))


def downgrade() -> None:
    # La tabla es de la línea base: solo se quita lo que aporta esta revisión.
    op.execute(text("ALTER TABLE refresh_tokens DROP COLUMN IF EXISTS revoked_at"))
