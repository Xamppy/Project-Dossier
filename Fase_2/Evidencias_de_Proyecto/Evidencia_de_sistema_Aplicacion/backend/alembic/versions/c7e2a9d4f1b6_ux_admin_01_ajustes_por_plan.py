"""UX-ADMIN-01: `plan_settings`, ajustes por plan que cambia el admin de plataforma.

Revision ID: c7e2a9d4f1b6
Revises: b4e8f2a6c0d3
Create Date: 2026-11-11

Primer ajuste: máximo de dossiers generándose a la vez por usuario (Free 1, Pro 3,
Enterprise 10). Igual que las revisiones anteriores, se reutiliza la tupla de
``schema_patches``, que la app también aplica al arrancar (DDL idempotente).
"""
from __future__ import annotations

from sqlalchemy import text

from alembic import op

revision = "c7e2a9d4f1b6"
down_revision = "b4e8f2a6c0d3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from dossier.db.schema_patches import PLAN_SETTINGS_PATCHES

    for sql in PLAN_SETTINGS_PATCHES:
        op.execute(text(sql))


def downgrade() -> None:
    op.execute(text("DROP TABLE IF EXISTS plan_settings"))
