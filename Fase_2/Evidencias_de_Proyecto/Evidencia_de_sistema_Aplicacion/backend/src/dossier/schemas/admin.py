"""Esquemas Pydantic para el panel de administración de plataforma (`/admin/*`)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


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
