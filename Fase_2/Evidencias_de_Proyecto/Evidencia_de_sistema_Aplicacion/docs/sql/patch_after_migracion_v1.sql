-- Parches incrementales tras ejecutar src/dossier/db/Migracion.md (o schema_project_dossier.sql).
-- Idempotente: ejecutar una vez en Neon SQL Editor si el dashboard muestra error de esquema.
-- Ver docs/render-deploy.md → Parte 1, paso 4.

-- Carpetas de dossiers (GET /dossiers falla sin esta columna).
ALTER TABLE dossiers
    ADD COLUMN IF NOT EXISTS dossier_folder_id UUID;

CREATE INDEX IF NOT EXISTS idx_dossiers_folder
    ON dossiers (dossier_folder_id)
    WHERE dossier_folder_id IS NOT NULL;

-- Preferencia de idioma de salida de dossiers (GET /auth/me).
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS dossier_output_language VARCHAR(10) NOT NULL DEFAULT 'match';

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS dossier_retention_days INTEGER DEFAULT 30;

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS is_platform_admin BOOLEAN NOT NULL DEFAULT FALSE;

-- OAuth calendario (si creaste calendar_integrations solo desde Migracion.md).
ALTER TABLE calendar_integrations
    ADD COLUMN IF NOT EXISTS refresh_token_encrypted TEXT,
    ADD COLUMN IF NOT EXISTS access_token_encrypted TEXT,
    ADD COLUMN IF NOT EXISTS access_token_expires_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS granted_scopes TEXT,
    ADD COLUMN IF NOT EXISTS provider_subject VARCHAR(255),
    ADD COLUMN IF NOT EXISTS provider_email VARCHAR(255),
    ADD COLUMN IF NOT EXISTS revoked_at TIMESTAMPTZ;

-- event_snapshot en calendar_events (automatización).
ALTER TABLE calendar_events
    ADD COLUMN IF NOT EXISTS event_snapshot JSONB;

-- Anticipación 20 min en integraciones de calendario.
ALTER TABLE calendar_integrations
    DROP CONSTRAINT IF EXISTS calendar_integrations_advance_minutes_check;
ALTER TABLE calendar_integrations
    ADD CONSTRAINT calendar_integrations_advance_minutes_check
    CHECK (advance_minutes IN (15, 20, 30, 60, 1440));
