"""Latido de los trabajos de generación para detectar los que quedaron colgados.

Revision ID: e1b5c9d3a7f2
Revises: c7e2a9d4f1b6
Create Date: 2026-11-11

Si el servidor se cae a mitad de una generación, el trabajo quedaba ``running`` para siempre.
El proceso que genera actualiza ``heartbeat_at``; un barrido marca como fallidos los que no
tienen latido reciente. Se reutiliza la tupla de ``schema_patches`` (DDL idempotente).
"""
from __future__ import annotations

from sqlalchemy import text

from alembic import op

revision = "e1b5c9d3a7f2"
down_revision = "c7e2a9d4f1b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from dossier.db.schema_patches import JOB_HEARTBEAT_PATCHES

    for sql in JOB_HEARTBEAT_PATCHES:
        op.execute(text(sql))


def downgrade() -> None:
    op.execute(text("ALTER TABLE dossier_generation_jobs DROP COLUMN IF EXISTS heartbeat_at"))
