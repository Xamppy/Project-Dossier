"""
Modelos ORM alineados con el schema PostgreSQL (Migración v1.0).

Fuente de verdad del DDL: `docs/sql/schema_project_dossier.sql` (copia de
`src/dossier/db/Migracion.md`). Ejecuta ese SQL en tu base antes de usar auth.

Tablas cubiertas por los modelos ORM actuales: `organizations`, `users`, `org_memberships`,
`contacts`, `dossiers` (alineadas con `docs/sql/schema_project_dossier.sql`).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from dossier.db.base import Base
from dossier.db.schema_patches import ALERT_LEVELS


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    plan: Mapped[str] = mapped_column(String(20), default="free")
    credits_balance: Mapped[int] = mapped_column(Integer, default=10)
    credits_monthly_limit: Mapped[int] = mapped_column(Integer, default=10)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    is_white_label: Mapped[bool] = mapped_column(Boolean, default=False)
    custom_domain: Mapped[str | None] = mapped_column(String(255))
    settings: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    timezone: Mapped[str] = mapped_column(String(100), default="UTC")
    locale: Mapped[str] = mapped_column(String(10), default="es")
    dossier_output_language: Mapped[str] = mapped_column(String(10), default="match")
    dossier_retention_days: Mapped[int | None] = mapped_column(Integer, nullable=True, default=30)
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_platform_admin: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class OAuthAccount(Base):
    """Identidad externa con la que un usuario inicia sesión (hoy solo Google)."""

    __tablename__ = "oauth_accounts"
    __table_args__ = (UniqueConstraint("provider", "provider_user_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(50))
    provider_user_id: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class RefreshToken(Base):
    """Token de renovación de sesión (S3.9). Solo se guarda el hash SHA-256, nunca el token.

    La tabla viene de la línea base (Migracion.md); `revoked_at` la agrega S3.9.
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_revoked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AuditLog(Base):
    """Registro de auditoría de solo inserción (S4.10). Diseño: Migracion.md, sección 13.

    La tabla viene de la línea base; aquí solo se describe. Una regla en la base
    (``trg_audit_logs_inmutable``) impide modificar o borrar filas, salvo que la base
    deje en NULL el usuario o la organización al borrarlos (``ON DELETE SET NULL``).
    """

    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # WHO
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    user_role_at_time: Mapped[str | None] = mapped_column(String(20), nullable=True)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
    # WHAT
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # WHEN
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # WHERE
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    # RESULT
    http_status: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    success: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Datos adicionales
    request_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    log_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)


class OrgMembership(Base):
    __tablename__ = "org_memberships"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_org_membership_org_user"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    role: Mapped[str] = mapped_column(String(20), default="user")
    is_primary_org: Mapped[bool] = mapped_column(Boolean, default=False)
    invited_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class OrgInvite(Base):
    """Invitación pendiente a unirse a una organización (mismo dominio de correo)."""

    __tablename__ = "org_invites"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
    )
    email: Mapped[str] = mapped_column(String(255), index=True)
    role: Mapped[str] = mapped_column(String(20), default="user")
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    invited_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class CalendarIntegration(Base):
    """Integración OAuth de calendario por usuario (DDL: ``docs/calendar_integrations_oauth.sql``)."""

    __tablename__ = "calendar_integrations"
    __table_args__ = (
        UniqueConstraint("user_id", "provider", name="calendar_integrations_user_id_provider_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(20))
    calendar_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    advance_minutes: Mapped[int] = mapped_column(Integer, default=20)
    skip_internal_meetings: Mapped[bool] = mapped_column(Boolean, default=False)
    skip_recurring_after_first: Mapped[bool] = mapped_column(Boolean, default=True)
    min_attendees: Mapped[int] = mapped_column(Integer, default=1)
    domain_whitelist: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    domain_blacklist: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    default_depth: Mapped[str] = mapped_column(String(10), default="standard")
    auto_send_email: Mapped[bool] = mapped_column(Boolean, default=True)
    email_cc_assistant: Mapped[str | None] = mapped_column(String(255), nullable=True)
    refresh_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    access_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    access_token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    granted_scopes: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CalendarEvent(Base):
    """Evento de calendario detectado para automatización (DDL: ``Migracion.md`` sección 11)."""

    __tablename__ = "calendar_events"
    __table_args__ = (
        UniqueConstraint(
            "calendar_integration_id",
            "external_event_id",
            name="calendar_events_integration_external_key",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    calendar_integration_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("calendar_integrations.id", ondelete="CASCADE"),
        index=True,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    external_event_id: Mapped[str] = mapped_column(String(500))
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    meeting_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_attendees: Mapped[list | dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    event_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    dossier_scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    processing_status: Mapped[str] = mapped_column(String(20), default="detected")
    skip_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Contact(Base):
    """Address book por organización; referenciado por `dossiers.contact_id`."""

    __tablename__ = "contacts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
    )
    email: Mapped[str | None] = mapped_column(String(255))
    full_name: Mapped[str | None] = mapped_column(String(255))
    linkedin_url: Mapped[str | None] = mapped_column(String(500))
    company: Mapped[str | None] = mapped_column(String(255))
    job_title: Mapped[str | None] = mapped_column(String(255))
    domain: Mapped[str | None] = mapped_column(String(255))
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    is_vip: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text)
    last_dossier_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Dossier(Base):
    """Tabla `dossiers` del schema migrado (solo columnas necesarias para lectura vía API)."""

    __tablename__ = "dossiers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
    )
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True
    )
    # Sin ForeignKey en ORM: evita NoReferencedTableError si el orden de import no
    # registra `contacts` en metadata; la FK real sigue en PostgreSQL (Migración).
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    subject_email: Mapped[str | None] = mapped_column(String(255))
    subject_name: Mapped[str | None] = mapped_column(String(255))
    module_identity: Mapped[bool] = mapped_column(Boolean, default=True)
    module_corporate: Mapped[bool] = mapped_column(Boolean, default=False)
    module_media: Mapped[bool] = mapped_column(Boolean, default=False)
    depth_level: Mapped[str] = mapped_column(String(10), default="basic")
    credits_consumed: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    status_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    dossier_data: Mapped[dict | list | None] = mapped_column(JSONB, nullable=True)
    alerts: Mapped[list | dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    agents_activated: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    agents_failed: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    data_sources_used: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    generation_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    generation_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    generation_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cache_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cached_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    trigger_source: Mapped[str] = mapped_column(String(20), default="manual")
    calendar_event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    dossier_folder_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    email_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    email_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    email_recipients: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DossierShare(Base):
    """Compartición interna de un dossier con otro miembro de la misma organización."""

    __tablename__ = "dossier_shares"
    __table_args__ = (
        UniqueConstraint(
            "dossier_id",
            "shared_with_user_id",
            name="uq_dossier_shares_dossier_user",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    dossier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dossiers.id", ondelete="CASCADE"),
        index=True,
    )
    shared_with_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    shared_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DossierAccessLink(Base):
    """Enlace de un solo uso para leer un dossier desde el correo (S6.2). DDL en ``schema_patches``.

    Solo guarda el SHA-256 del token; el token viaja únicamente en el correo.
    """

    __tablename__ = "dossier_access_links"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    dossier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dossiers.id", ondelete="CASCADE")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class PlanSetting(Base):
    """Ajustes por plan que el admin de plataforma cambia en el panel (UX-ADMIN-01).

    DDL y valores iniciales en ``schema_patches.PLAN_SETTINGS_PATCHES``.
    """

    __tablename__ = "plan_settings"

    plan: Mapped[str] = mapped_column(String(20), primary_key=True)
    max_concurrent_dossiers: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class DossierEmailRetry(Base):
    """Envío automático de correo en espera de reintento (S6.4). DDL en ``schema_patches``.

    No guarda la dirección del destinatario: al reintentar se lee de ``users.email``.
    """

    __tablename__ = "dossier_email_retries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(String(20))
    dossier_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)))
    calendar_event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("calendar_events.id", ondelete="SET NULL"), nullable=True
    )
    meeting_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    # Índice idx_dossier_email_retries_next en schema_patches.
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DossierGenerationJob(Base):
    """Cola de generación asíncrona (manual desde calendario u otros triggers)."""

    __tablename__ = "dossier_generation_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
    )
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True
    )
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    job_type: Mapped[str] = mapped_column(String(40), default="calendar_manual")
    calendar_provider: Mapped[str | None] = mapped_column(String(20), nullable=True)
    external_event_id: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    reunion_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    depth_level: Mapped[str] = mapped_column(String(10), default="standard")
    meeting_label: Mapped[str | None] = mapped_column(String(512), nullable=True)
    credits_estimated: Mapped[int] = mapped_column(Integer, default=0)
    credits_consumed: Mapped[int] = mapped_column(Integer, default=0)
    result_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Latido del proceso que lo genera; sin latido reciente, el trabajo quedó colgado.
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# S4.5: las tres tablas siguen el DDL de Migracion.md (secciones 7, 14 y 15) más
# las columnas que agrega schema_patches.DOSSIER_ENTITIES_PATCHES.


class DossierAlert(Base):
    """Alerta de riesgo de un dossier (``RiskAlert`` del contrato de S4.1)."""

    __tablename__ = "dossier_alerts"
    __table_args__ = (
        CheckConstraint(
            "level IN (" + ", ".join(f"'{nivel}'" for nivel in ALERT_LEVELS) + ")",
            name="dossier_alerts_level_check",
        ),
        Index("idx_alerts_dossier", "dossier_id"),
        Index("idx_alerts_level", "dossier_id", "level"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    dossier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dossiers.id", ondelete="CASCADE"), nullable=False
    )
    # 'critical'/'warning' son los niveles heredados; el contrato usa 'low'/'medium'/'high'.
    level: Mapped[str] = mapped_column(String(10), nullable=False)
    category: Mapped[str | None] = mapped_column(String(50))
    title: Mapped[str | None] = mapped_column(String(255))
    message: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    sources: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    is_acknowledged: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )


class DossierMediaMention(Base):
    """Mención de prensa de un dossier (``PressMention`` del contrato de S4.1)."""

    __tablename__ = "dossier_media_mentions"
    __table_args__ = (
        CheckConstraint(
            "sentiment IN ('positive', 'neutral', 'negative', 'mixed')",
            name="dossier_media_mentions_sentiment_check",
        ),
        CheckConstraint(
            "relevance_score BETWEEN 0.00 AND 1.00",
            name="dossier_media_mentions_relevance_score_check",
        ),
        Index("idx_media_dossier", "dossier_id"),
        Index("idx_media_sentiment", "dossier_id", "sentiment"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    dossier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dossiers.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_name: Mapped[str | None] = mapped_column(String(255))
    source_type: Mapped[str | None] = mapped_column(String(50))
    sentiment: Mapped[str | None] = mapped_column(String(10))
    summary: Mapped[str | None] = mapped_column(Text)
    relevance_score: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    # Procedencia (S3.4): SourceCitation serializada y la consulta que la trajo.
    source_citation: Mapped[dict | None] = mapped_column(JSONB)
    query_context: Mapped[str | None] = mapped_column(String(255))


class DossierCareerEntry(Base):
    """Cargo de la trayectoria de un dossier (``CareerPosition`` del contrato de S4.1)."""

    __tablename__ = "dossier_career_entries"
    __table_args__ = (Index("idx_career_dossier", "dossier_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    dossier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dossiers.id", ondelete="CASCADE"), nullable=False
    )
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    job_title: Mapped[str | None] = mapped_column(String(255))
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    # El contrato trae fechas parciales ("2019", "2019-03") que no caben en DATE.
    start_date_text: Mapped[str | None] = mapped_column(String(50))
    end_date_text: Mapped[str | None] = mapped_column(String(50))
    tenure_months: Mapped[int | None] = mapped_column(Integer)
    is_current: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    gap_months_after: Mapped[int | None] = mapped_column(Integer)
    has_discrepancy: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    discrepancy_detail: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(String(50))
    source_citation: Mapped[dict | None] = mapped_column(JSONB)
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
