"""Parches DDL idempotentes para bases ya creadas (``create_all`` no altera tablas existentes)."""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

_PATCHES = (
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS dossier_output_language VARCHAR(10) NOT NULL DEFAULT 'match';",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS dossier_retention_days INTEGER DEFAULT 30;",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_platform_admin BOOLEAN NOT NULL DEFAULT FALSE;",
    "ALTER TABLE dossiers ADD COLUMN IF NOT EXISTS dossier_folder_id UUID;",
    "CREATE INDEX IF NOT EXISTS idx_dossiers_folder ON dossiers (dossier_folder_id) WHERE dossier_folder_id IS NOT NULL;",
    "ALTER TABLE calendar_integrations ADD COLUMN IF NOT EXISTS refresh_token_encrypted TEXT;",
    "ALTER TABLE calendar_integrations ADD COLUMN IF NOT EXISTS access_token_encrypted TEXT;",
    "ALTER TABLE calendar_integrations ADD COLUMN IF NOT EXISTS access_token_expires_at TIMESTAMPTZ;",
    "ALTER TABLE calendar_integrations ADD COLUMN IF NOT EXISTS granted_scopes TEXT;",
    "ALTER TABLE calendar_integrations ADD COLUMN IF NOT EXISTS provider_subject VARCHAR(255);",
    "ALTER TABLE calendar_integrations ADD COLUMN IF NOT EXISTS provider_email VARCHAR(255);",
    "ALTER TABLE calendar_integrations ADD COLUMN IF NOT EXISTS revoked_at TIMESTAMPTZ;",
    "ALTER TABLE calendar_events ADD COLUMN IF NOT EXISTS event_snapshot JSONB;",
    "ALTER TABLE calendar_integrations DROP CONSTRAINT IF EXISTS calendar_integrations_advance_minutes_check;",
    """
    DO $$
    BEGIN
      ALTER TABLE calendar_integrations
        ADD CONSTRAINT calendar_integrations_advance_minutes_check
        CHECK (advance_minutes IN (15, 20, 30, 60, 1440));
    EXCEPTION
      WHEN duplicate_object THEN NULL;
    END $$;
    """,
    """
    CREATE TABLE IF NOT EXISTS dossier_shares (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        dossier_id UUID NOT NULL REFERENCES dossiers(id) ON DELETE CASCADE,
        shared_with_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        shared_by_user_id UUID NOT NULL REFERENCES users(id),
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (dossier_id, shared_with_user_id)
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_dossier_shares_dossier ON dossier_shares(dossier_id);",
    "CREATE INDEX IF NOT EXISTS idx_dossier_shares_user ON dossier_shares(shared_with_user_id);",
    """
    CREATE TABLE IF NOT EXISTS org_invites (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        email VARCHAR(255) NOT NULL,
        role VARCHAR(20) NOT NULL DEFAULT 'user',
        token VARCHAR(64) NOT NULL UNIQUE,
        status VARCHAR(20) NOT NULL DEFAULT 'pending',
        invited_by_user_id UUID NOT NULL REFERENCES users(id),
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        expires_at TIMESTAMPTZ NOT NULL,
        accepted_at TIMESTAMPTZ
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_org_invites_org ON org_invites(organization_id);",
    "CREATE INDEX IF NOT EXISTS idx_org_invites_email ON org_invites(email);",
    "CREATE INDEX IF NOT EXISTS idx_org_invites_status ON org_invites(status);",
)

# S4.5: extiende las tablas de la línea base al contrato de S4.1
# (schemas/dossier_executive_payload.py). Separado de _PATCHES porque la
# migración de línea base itera _PATCHES en vivo; lo aplica la migración 0002.
ALERT_LEVELS = ("critical", "warning", "low", "medium", "high")

DOSSIER_ENTITIES_PATCHES = (
    "ALTER TABLE dossier_alerts ADD COLUMN IF NOT EXISTS title VARCHAR(255);",
    "ALTER TABLE dossier_alerts ADD COLUMN IF NOT EXISTS sources JSONB NOT NULL DEFAULT '[]'::jsonb;",
    "ALTER TABLE dossier_alerts DROP CONSTRAINT IF EXISTS dossier_alerts_level_check;",
    "ALTER TABLE dossier_alerts ADD CONSTRAINT dossier_alerts_level_check CHECK (level IN ("
    + ", ".join(f"'{nivel}'" for nivel in ALERT_LEVELS)
    + "));",
    "ALTER TABLE dossier_media_mentions ADD COLUMN IF NOT EXISTS source_citation JSONB;",
    "ALTER TABLE dossier_media_mentions ADD COLUMN IF NOT EXISTS query_context VARCHAR(255);",
    "ALTER TABLE dossier_career_entries ADD COLUMN IF NOT EXISTS start_date_text VARCHAR(50);",
    "ALTER TABLE dossier_career_entries ADD COLUMN IF NOT EXISTS end_date_text VARCHAR(50);",
    "ALTER TABLE dossier_career_entries ADD COLUMN IF NOT EXISTS source_citation JSONB;",
)


# BUG-2026-10-05-01: la cola de trabajos solo la creaba create_all del ORM, así que una base
# hecha con Alembic y DATABASE_AUTO_CREATE_TABLES=0 no la tenía. Mismo DDL que genera el ORM
# (db/models.py:DossierGenerationJob); lo reutiliza la migración c4d8a2f6b1e9.
JOB_QUEUE_PATCHES = (
    """
    CREATE TABLE IF NOT EXISTS dossier_generation_jobs (
        id UUID NOT NULL,
        organization_id UUID NOT NULL,
        requested_by_user_id UUID NOT NULL,
        status VARCHAR(20) NOT NULL,
        job_type VARCHAR(40) NOT NULL,
        calendar_provider VARCHAR(20),
        external_event_id VARCHAR(512),
        reunion_snapshot JSONB,
        depth_level VARCHAR(10) NOT NULL,
        meeting_label VARCHAR(512),
        credits_estimated INTEGER NOT NULL,
        credits_consumed INTEGER NOT NULL,
        result_payload JSONB,
        error_message TEXT,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        started_at TIMESTAMP WITH TIME ZONE,
        completed_at TIMESTAMP WITH TIME ZONE,
        PRIMARY KEY (id),
        FOREIGN KEY (organization_id) REFERENCES organizations (id) ON DELETE CASCADE,
        FOREIGN KEY (requested_by_user_id) REFERENCES users (id)
    );
    """,
    "CREATE INDEX IF NOT EXISTS ix_dossier_generation_jobs_organization_id "
    "ON dossier_generation_jobs (organization_id);",
    "CREATE INDEX IF NOT EXISTS ix_dossier_generation_jobs_requested_by_user_id "
    "ON dossier_generation_jobs (requested_by_user_id);",
    "CREATE INDEX IF NOT EXISTS ix_dossier_generation_jobs_status "
    "ON dossier_generation_jobs (status);",
    "CREATE INDEX IF NOT EXISTS ix_dossier_generation_jobs_external_event_id "
    "ON dossier_generation_jobs (external_event_id);",
)


# S3.9: la tabla `refresh_tokens` viene de la línea base (Migracion.md) y no se usaba. La
# rotación necesita saber cuándo se revocó cada token (ventana de gracia entre pestañas y
# detección de reutilización), por eso se agrega `revoked_at`. El CREATE TABLE cubre bases
# que no aplicaron la línea base; lo reutiliza la migración d5a9e3c7f2b8.
REFRESH_TOKEN_PATCHES = (
    """
    CREATE TABLE IF NOT EXISTS refresh_tokens (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        token_hash VARCHAR(255) NOT NULL UNIQUE,
        expires_at TIMESTAMPTZ NOT NULL,
        is_revoked BOOLEAN NOT NULL DEFAULT FALSE,
        ip_address INET,
        user_agent TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """,
    "ALTER TABLE refresh_tokens ADD COLUMN IF NOT EXISTS revoked_at TIMESTAMPTZ;",
    "CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user ON refresh_tokens (user_id);",
)


# S4.10: `audit_logs` viene de la línea base (Migracion.md, sección 13) y nadie la usaba.
# Su comentario exige "NUNCA actualizar ni eliminar"; Migracion.md lo dejaba a permisos de
# roles de la base, que el despliegue no configura. Esta regla lo hace cumplir en la base.
# Única excepción: que la base deje en NULL el usuario o la organización al borrarlos
# (ON DELETE SET NULL), para no impedir el borrado de cuentas. El CREATE TABLE cubre bases
# sin la línea base; lo reutiliza la migración e8b1f4a6c2d9.
AUDIT_LOG_PATCHES = (
    """
    CREATE TABLE IF NOT EXISTS audit_logs (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID REFERENCES users(id) ON DELETE SET NULL,
        user_role_at_time VARCHAR(20),
        organization_id UUID REFERENCES organizations(id) ON DELETE SET NULL,
        action VARCHAR(100) NOT NULL,
        resource_type VARCHAR(50),
        resource_id UUID,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        ip_address INET,
        user_agent TEXT,
        http_status SMALLINT,
        success BOOLEAN NOT NULL DEFAULT TRUE,
        error_message TEXT,
        request_data JSONB,
        duration_ms INTEGER,
        log_hash VARCHAR(64)
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_logs (user_id, created_at DESC);",
    "CREATE INDEX IF NOT EXISTS idx_audit_org ON audit_logs (organization_id, created_at DESC);",
    "CREATE INDEX IF NOT EXISTS idx_audit_resource ON audit_logs (resource_type, resource_id);",
    """
    CREATE OR REPLACE FUNCTION audit_logs_inmutable() RETURNS trigger AS $$
    BEGIN
        IF TG_OP = 'UPDATE'
           AND (NEW.user_id IS NOT DISTINCT FROM OLD.user_id OR NEW.user_id IS NULL)
           AND (NEW.organization_id IS NOT DISTINCT FROM OLD.organization_id OR NEW.organization_id IS NULL)
           AND (to_jsonb(NEW) - 'user_id' - 'organization_id')
               = (to_jsonb(OLD) - 'user_id' - 'organization_id') THEN
            RETURN NEW;
        END IF;
        RAISE EXCEPTION 'audit_logs es de solo inserción (S4.10): % no permitido', TG_OP;
    END;
    $$ LANGUAGE plpgsql;
    """,
    "DROP TRIGGER IF EXISTS trg_audit_logs_inmutable ON audit_logs;",
    """
    CREATE TRIGGER trg_audit_logs_inmutable
        BEFORE UPDATE OR DELETE ON audit_logs
        FOR EACH ROW EXECUTE FUNCTION audit_logs_inmutable();
    """,
)


def apply_schema_patches(engine: Engine) -> None:
    with engine.begin() as conn:
        for sql in (
            _PATCHES
            + DOSSIER_ENTITIES_PATCHES
            + JOB_QUEUE_PATCHES
            + REFRESH_TOKEN_PATCHES
            + AUDIT_LOG_PATCHES
        ):
            conn.execute(text(sql))
