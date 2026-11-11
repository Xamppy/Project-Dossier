"""UX-ADMIN-03: créditos al mes de cada plan en `plan_settings`.

Revision ID: f1c3e5a7b9d2
Revises: d4f6a8c2e0b3
Create Date: 2026-11-11

Antes eran fijos en `billing/plan_catalog.py` (Free 10, Pro 500, Enterprise 50.000). Se reutiliza
la tupla de ``schema_patches``, que la app también aplica al arrancar (DDL idempotente).
"""
from __future__ import annotations

from sqlalchemy import text

from alembic import op

revision = "f1c3e5a7b9d2"
down_revision = "d4f6a8c2e0b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from dossier.db.schema_patches import PLAN_CREDITS_PATCHES

    for sql in PLAN_CREDITS_PATCHES:
        op.execute(text(sql))


def downgrade() -> None:
    op.execute(text("ALTER TABLE plan_settings DROP CONSTRAINT IF EXISTS plan_settings_monthly_credits_rango"))
    op.execute(text("ALTER TABLE plan_settings DROP COLUMN IF EXISTS monthly_credits"))
