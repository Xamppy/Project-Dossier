"""UX-ADMIN-02: fuentes de noticias administrables y cobro extra por fuente.

Revision ID: d4f6a8c2e0b3
Revises: a2c4e6f8b0d1
Create Date: 2026-11-11

Crea ``news_source_settings`` (ajustes del admin por fuente) y ``news_source_usage``
(consultas por día para el límite diario), y cambia ``fn_debit_credits_on_dossier`` para
sumar ``dossier_data.news_extra_credits`` al costo por profundidad. Igual que las
revisiones anteriores, se reutiliza la tupla de ``schema_patches``.
"""
from __future__ import annotations

from sqlalchemy import text

from alembic import op

revision = "d4f6a8c2e0b3"
down_revision = "a2c4e6f8b0d1"
branch_labels = None
depends_on = None

# La función de cobro de a9d3e5f7b1c4, para el downgrade.
_BEFORE_SIN_EXTRA = """
CREATE OR REPLACE FUNCTION fn_debit_credits_on_dossier()
RETURNS TRIGGER AS $$
DECLARE
    v_credits INTEGER;
BEGIN
    IF jsonb_extract_path_text(COALESCE(NEW.dossier_data, '{}'::jsonb), 'billing') = 'none' THEN
        NEW.credits_consumed := 0;
        RETURN NEW;
    END IF;

    v_credits := CASE NEW.depth_level
        WHEN 'basic'    THEN 1
        WHEN 'standard' THEN 3
        WHEN 'deep'     THEN 5
        ELSE 1
    END;

    IF (SELECT credits_balance FROM organizations WHERE id = NEW.organization_id) < v_credits THEN
        RAISE EXCEPTION 'Insufficient credits for organization %', NEW.organization_id;
    END IF;

    -- BUG-2026-10-19-08: el descuento se hace en el AFTER, junto con su anotación.
    NEW.credits_consumed := v_credits;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    from dossier.db.schema_patches import NEWS_SOURCE_PATCHES

    for sql in NEWS_SOURCE_PATCHES:
        op.execute(text(sql))


def downgrade() -> None:
    op.execute(text(_BEFORE_SIN_EXTRA))
    op.execute(text("DROP TABLE IF EXISTS news_source_usage"))
    op.execute(text("DROP TABLE IF EXISTS news_source_settings"))
