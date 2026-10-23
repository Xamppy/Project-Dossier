-- Parche para bases que ya tienen el trigger antiguo de créditos.
-- Problema: INSERT en credit_ledger dentro de BEFORE INSERT sobre dossiers
-- referencia dossier_id antes de que la fila exista → FK credit_ledger_dossier_id_fkey.
-- Solución: débito en BEFORE; fila del ledger en AFTER.
--
-- Además: si dossier_data->>'billing' = 'none', no se debita (API sin cobro).
--
-- Ejecutar con psql (si está en el PATH):
--   psql "$DATABASE_URL" -f scripts/fix_dossier_credit_triggers.sql
-- O desde backend/, sin psql (usa .env + psycopg):
--   python scripts/apply_fix_dossier_credit_triggers.py

BEGIN;

DROP TRIGGER IF EXISTS trg_credit_ledger_after_dossier_insert ON dossiers;

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

DROP TRIGGER IF EXISTS trg_debit_credits ON dossiers;

CREATE TRIGGER trg_debit_credits
    BEFORE INSERT ON dossiers
    FOR EACH ROW EXECUTE FUNCTION fn_debit_credits_on_dossier();

CREATE TRIGGER trg_credit_ledger_after_dossier_insert
    AFTER INSERT ON dossiers
    FOR EACH ROW EXECUTE FUNCTION fn_credit_ledger_after_dossier_insert();

COMMIT;
