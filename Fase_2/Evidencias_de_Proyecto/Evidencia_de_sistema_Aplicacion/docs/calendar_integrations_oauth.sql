-- =============================================================================
-- Project Dossier — calendar_integrations + OAuth (solo lectura de calendario)
-- Ejecutar en PostgreSQL (Railway, etc.) cuando aún no exista la tabla, O
-- usar solo el bloque ALTER al final si ya creaste la tabla desde Migracion.md
-- sin columnas de tokens.
-- =============================================================================
-- Regla de producto recomendada: el usuario elige Google O Microsoft; la API
-- puede impedir tener ambos activos a la vez, o permitir solo uno según UX.
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS calendar_integrations (
    id                  UUID            PRIMARY KEY DEFAULT uuid_generate_v4(),

    user_id             UUID            NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    organization_id     UUID            NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,

    provider            VARCHAR(20)     NOT NULL
                        CHECK (provider IN ('google', 'microsoft')),

    -- Calendario concreto en la API externa (NULL = “principal” hasta resolver sync).
    calendar_id         VARCHAR(500),

    is_enabled          BOOLEAN         NOT NULL DEFAULT TRUE,

    advance_minutes     INTEGER         NOT NULL DEFAULT 20
                        CHECK (advance_minutes IN (15, 20, 30, 60, 1440)),

    skip_internal_meetings  BOOLEAN     NOT NULL DEFAULT TRUE,
    skip_recurring_after_first BOOLEAN  NOT NULL DEFAULT TRUE,

    min_attendees       INTEGER         NOT NULL DEFAULT 1
                        CHECK (min_attendees >= 1),

    domain_whitelist    TEXT[]          NOT NULL DEFAULT '{}',
    domain_blacklist    TEXT[]          NOT NULL DEFAULT '{}',

    default_depth       VARCHAR(10)     NOT NULL DEFAULT 'standard'
                        CHECK (default_depth IN ('basic', 'standard', 'deep')),

    auto_send_email     BOOLEAN         NOT NULL DEFAULT TRUE,
    email_cc_assistant  VARCHAR(255),

    -- --- OAuth / tokens (servidor; no exponer al navegador) ---
    -- refresh: idealmente cifrado en aplicación antes de guardar (ver docs).
    refresh_token_encrypted   TEXT,
    access_token_encrypted    TEXT,
    access_token_expires_at   TIMESTAMPTZ,
    granted_scopes            TEXT,
    -- Identidad en el proveedor (estable para reconciliar cuentas).
    provider_subject          VARCHAR(255),
    provider_email            VARCHAR(255),

    revoked_at          TIMESTAMPTZ,

    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    -- Una fila por usuario y proveedor (suficiente si el usuario elige Google XOR Outlook).
    UNIQUE (user_id, provider)
);

CREATE INDEX IF NOT EXISTS idx_calendar_integrations_user
    ON calendar_integrations(user_id);
CREATE INDEX IF NOT EXISTS idx_calendar_integrations_org
    ON calendar_integrations(organization_id);

-- Trigger updated_at (crear función update_updated_at si no existe en tu BD).
-- Si ya la tienes desde Migracion.md, descomenta:
-- CREATE TRIGGER trg_calendar_integrations_updated_at
--     BEFORE UPDATE ON calendar_integrations
--     FOR EACH ROW EXECUTE FUNCTION update_updated_at();


-- -----------------------------------------------------------------------------
-- Si YA tienes calendar_integrations desde Migracion.md (sin columnas OAuth),
-- ejecuta en su lugar (ajusta nombres si difieren):
-- -----------------------------------------------------------------------------
-- ALTER TABLE calendar_integrations
--     ADD COLUMN IF NOT EXISTS refresh_token_encrypted TEXT,
--     ADD COLUMN IF NOT EXISTS access_token_encrypted TEXT,
--     ADD COLUMN IF NOT EXISTS access_token_expires_at TIMESTAMPTZ,
--     ADD COLUMN IF NOT EXISTS granted_scopes TEXT,
--     ADD COLUMN IF NOT EXISTS provider_subject VARCHAR(255),
--     ADD COLUMN IF NOT EXISTS provider_email VARCHAR(255),
--     ADD COLUMN IF NOT EXISTS revoked_at TIMESTAMPTZ;
--
-- -- Migracion.md tenía UNIQUE (user_id, provider, calendar_id). Para “un proveedor
-- -- por usuario”, conviene reemplazar por UNIQUE (user_id, provider):
-- -- ALTER TABLE calendar_integrations DROP CONSTRAINT IF EXISTS calendar_integrations_user_id_provider_calendar_id_key;
-- -- ALTER TABLE calendar_integrations ADD CONSTRAINT calendar_integrations_user_provider_key UNIQUE (user_id, provider);
