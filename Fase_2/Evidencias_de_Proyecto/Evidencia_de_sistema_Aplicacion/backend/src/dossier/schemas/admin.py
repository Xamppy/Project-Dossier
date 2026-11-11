"""Esquemas Pydantic para el panel de administración de plataforma (`/admin/*`)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator, model_validator


class AdminOverviewResponse(BaseModel):
    users_total: int
    organizations_total: int
    dossiers_total: int


class AdminUserListItem(BaseModel):
    id: UUID
    email: str
    full_name: str | None
    is_active: bool
    is_platform_admin: bool
    created_at: datetime | None
    organization_id: UUID | None = None
    organization_name: str | None = None
    workspace_kind: Literal["personal", "work"] | None = None
    plan: str | None = None
    credits_balance: int | None = None
    credits_monthly_limit: int | None = None
    dossiers_count: int = 0


class AdminUserListResponse(BaseModel):
    total: int
    items: list[AdminUserListItem]


class AdminUserRolesPatch(BaseModel):
    """PATCH /admin/users/{id}: solo el flag de administrador de plataforma."""

    is_platform_admin: bool = Field(description="Rol de administrador de plataforma")


class AdminOrganizationListItem(BaseModel):
    id: UUID
    name: str
    slug: str
    plan: str
    credits_balance: int
    credits_monthly_limit: int
    is_active: bool
    members_count: int = 0
    dossiers_count: int = 0
    created_at: datetime | None = None
    workspace_kind: Literal["personal", "work"] = "work"


class AdminOrganizationListResponse(BaseModel):
    total: int
    items: list[AdminOrganizationListItem]


class AdminDossierListItem(BaseModel):
    id: UUID
    organization_id: UUID
    organization_name: str
    workspace_kind: Literal["personal", "work"] = "work"
    requested_by_user_id: UUID
    requested_by_email: str
    subject_name: str | None
    subject_email: str | None
    status: str
    credits_consumed: int
    created_at: datetime | None = None


class AdminDossierListResponse(BaseModel):
    total: int
    items: list[AdminDossierListItem]


class AdminPlanSettingItem(BaseModel):
    """Ajustes de un plan (UX-ADMIN-01)."""

    plan: Literal["free", "pro", "enterprise"]
    max_concurrent_dossiers: int
    updated_at: datetime | None = None
    updated_by_email: str | None = None


class AdminPlanSettingsResponse(BaseModel):
    plans: list[AdminPlanSettingItem]


class AdminPlanSettingPatch(BaseModel):
    """Entero estricto entre 1 y 100: ``2.5`` o ``"3"`` no se aceptan."""

    model_config = ConfigDict(extra="forbid")

    max_concurrent_dossiers: StrictInt = Field(ge=1, le=100)


# --- UX-ADMIN-02: fuentes de noticias -------------------------------------------------------

NewsDepth = Literal["basic", "standard", "deep"]
NewsPlan = Literal["free", "pro", "enterprise"]
_ORDEN_PLANES: tuple[str, ...] = ("free", "pro", "enterprise")


class AdminNewsSourceItem(BaseModel):
    """Una fuente instalada con sus ajustes. Nunca incluye el valor de la clave de la API."""

    key: str
    name: str
    description: str
    configured: bool
    key_env_var: str | None
    default_enabled: bool
    enabled: bool
    use_for_corporate: bool
    use_for_person: bool
    min_depth: NewsDepth
    plans: list[NewsPlan]
    extra_credits: int
    max_results: int
    daily_limit: int | None
    used_today: int
    updated_at: datetime | None = None
    updated_by_email: str | None = None


class AdminNewsSourcesResponse(BaseModel):
    sources: list[AdminNewsSourceItem]


class AdminNewsSourcePatch(BaseModel):
    """Cambios de una fuente. Solo lo enviado cambia; ``daily_limit: null`` quita el límite.

    Tipos estrictos: ``"true"`` o ``2.5`` no se aceptan. La clave de la API no va aquí: vive
    solo en el entorno del servidor (un campo desconocido es 422).
    """

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool | None = None
    use_for_corporate: StrictBool | None = None
    use_for_person: StrictBool | None = None
    min_depth: NewsDepth | None = None
    plans: list[NewsPlan] | None = Field(default=None, min_length=1, max_length=3)
    extra_credits: StrictInt | None = Field(default=None, ge=0, le=20)
    max_results: StrictInt | None = Field(default=None, ge=1, le=50)
    daily_limit: StrictInt | None = Field(default=None, ge=1, le=100_000)

    @field_validator("plans")
    @classmethod
    def _planes_ordenados(cls, valor: list[str] | None) -> list[str] | None:
        if valor is None:
            return None
        return [p for p in _ORDEN_PLANES if p in set(valor)]

    @model_validator(mode="after")
    def _con_cambios(self) -> AdminNewsSourcePatch:
        if not self.model_fields_set:
            raise ValueError("No hay cambios que guardar.")
        for campo in self.model_fields_set - {"daily_limit"}:
            if getattr(self, campo) is None:
                raise ValueError(f"{campo} no puede ser null.")
        return self


class NewsSourceApplicableItem(BaseModel):
    key: str
    name: str
    extra_credits: int


class NewsSourcesApplicableResponse(BaseModel):
    """Fuentes de prensa que usaría un dossier y su extra máximo (si responden todas)."""

    sources: list[NewsSourceApplicableItem]
    extra_credits: int

