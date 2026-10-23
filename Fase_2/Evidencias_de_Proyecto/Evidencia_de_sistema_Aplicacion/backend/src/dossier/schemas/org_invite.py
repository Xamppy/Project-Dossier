"""Esquemas para invitaciones a organizaciones."""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class OrgInviteCreate(BaseModel):
    email: EmailStr
    role: Literal["admin", "user", "viewer"] = "user"


class OrgInviteItem(BaseModel):
    id: UUID
    email: str
    role: str
    status: str
    invite_url: str | None = None
    created_at: str | None = None
    expires_at: str | None = None
    joined_immediately: bool = False


class OrgInvitesResponse(BaseModel):
    organization_domain: str
    items: list[OrgInviteItem]


class OrgInvitePreview(BaseModel):
    organization_id: UUID
    organization_name: str
    email: str
    role: str
    email_domain: str
    expires_at: str | None = None
    valid: bool = True
    token: str | None = None


class OrgPendingInvitesResponse(BaseModel):
    items: list[OrgInvitePreview]


class OrgInviteAcceptRequest(BaseModel):
    token: str = Field(min_length=8, max_length=128)


class UserOrganizationItem(BaseModel):
    """Membresía del usuario para el selector de organización."""

    organization_id: UUID
    organization_name: str
    role: str
    workspace_kind: Literal["personal", "work"]
    is_primary: bool = False
    is_active: bool = False


class UserOrganizationsResponse(BaseModel):
    items: list[UserOrganizationItem]


class SessionSwitchRequest(BaseModel):
    organization_id: UUID
