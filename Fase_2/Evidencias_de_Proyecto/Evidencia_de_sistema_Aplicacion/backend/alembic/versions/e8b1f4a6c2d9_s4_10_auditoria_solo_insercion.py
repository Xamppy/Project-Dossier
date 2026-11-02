"""S4.10: `audit_logs` de solo inserción.

Revision ID: e8b1f4a6c2d9
Revises: d5a9e3c7f2b8
Create Date: 2026-11-02

La tabla `audit_logs` existe desde la línea base (Migracion.md, sección 13) y no se
recrea. Esta revisión agrega la regla que hace cumplir su comentario ("NUNCA
actualizar ni eliminar registros"): un trigger que rechaza UPDATE y DELETE, salvo que
la base deje en NULL el usuario o la organización al borrarlos (ON DELETE SET NULL).

Igual que las revisiones anteriores, se reutiliza la tupla de ``schema_patches``, que
la app también aplica al arrancar (DDL idempotente).
"""
from __future__ import annotations

from sqlalchemy import text

from alembic import op

revision = "e8b1f4a6c2d9"
down_revision = "d5a9e3c7f2b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from dossier.db.schema_patches import AUDIT_LOG_PATCHES

    for sql in AUDIT_LOG_PATCHES:
        op.execute(text(sql))


def downgrade() -> None:
    # La tabla y sus índices son de la línea base: solo se quita la regla.
    op.execute(text("DROP TRIGGER IF EXISTS trg_audit_logs_inmutable ON audit_logs"))
    op.execute(text("DROP FUNCTION IF EXISTS audit_logs_inmutable()"))
