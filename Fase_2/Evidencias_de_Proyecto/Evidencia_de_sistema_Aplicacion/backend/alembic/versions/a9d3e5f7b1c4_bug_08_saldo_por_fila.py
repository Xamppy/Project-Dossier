"""BUG-2026-10-19-08: cada dossier anota en `credit_ledger` su propio saldo.

Revision ID: a9d3e5f7b1c4
Revises: f3a7c1e9b5d2
Create Date: 2026-11-10

Antes, el descuento iba en el trigger BEFORE INSERT y la anotación en el AFTER INSERT. Postgres
corre los AFTER de fila al terminar la sentencia, así que con dos dossiers en un mismo INSERT
ambas filas de `credit_ledger` leían el saldo final (10 → 7 → 4 quedaba anotado como 4 y 4).

Ahora el descuento y la anotación van juntos en el AFTER: cada fila descuenta y lee su saldo con
``UPDATE … RETURNING``. El BEFORE solo calcula el costo y rechaza temprano una fila que ya no
alcanza; el AFTER vuelve a comprobar el saldo, porque con varias filas en una sentencia el BEFORE
ve el saldo de antes de todas.
"""
from __future__ import annotations

from sqlalchemy import text

from alembic import op

revision = "a9d3e5f7b1c4"
down_revision = "f3a7c1e9b5d2"
branch_labels = None
depends_on = None

_BEFORE_NUEVO = """
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

_AFTER_NUEVO = """
CREATE OR REPLACE FUNCTION fn_credit_ledger_after_dossier_insert()
RETURNS TRIGGER AS $$
DECLARE
    v_saldo INTEGER;
BEGIN
    IF NEW.credits_consumed IS NULL OR NEW.credits_consumed <= 0 THEN
        RETURN NEW;
    END IF;

    UPDATE organizations
    SET credits_balance = credits_balance - NEW.credits_consumed
    WHERE id = NEW.organization_id
      AND credits_balance >= NEW.credits_consumed
    RETURNING credits_balance INTO v_saldo;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Insufficient credits for organization %', NEW.organization_id;
    END IF;

    INSERT INTO credit_ledger (organization_id, user_id, dossier_id, change_amount, balance_after, reason)
    VALUES (NEW.organization_id, NEW.requested_by_user_id, NEW.id, -NEW.credits_consumed, v_saldo,
            'dossier_generation');

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

# Las versiones de la línea base (a3f1c9e2b7d4), para el downgrade.
_BEFORE_ANTERIOR = """
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

    UPDATE organizations
    SET credits_balance = credits_balance - v_credits
    WHERE id = NEW.organization_id;

    NEW.credits_consumed := v_credits;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

_AFTER_ANTERIOR = """
CREATE OR REPLACE FUNCTION fn_credit_ledger_after_dossier_insert()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.credits_consumed IS NULL OR NEW.credits_consumed <= 0 THEN
        RETURN NEW;
    END IF;

    INSERT INTO credit_ledger (organization_id, user_id, dossier_id, change_amount, balance_after, reason)
    SELECT
        NEW.organization_id,
        NEW.requested_by_user_id,
        NEW.id,
        -NEW.credits_consumed,
        (SELECT credits_balance FROM organizations WHERE id = NEW.organization_id),
        'dossier_generation';

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    op.execute(text(_BEFORE_NUEVO))
    op.execute(text(_AFTER_NUEVO))


def downgrade() -> None:
    op.execute(text(_BEFORE_ANTERIOR))
    op.execute(text(_AFTER_ANTERIOR))
