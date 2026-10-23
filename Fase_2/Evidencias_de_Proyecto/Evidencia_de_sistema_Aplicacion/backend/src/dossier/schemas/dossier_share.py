"""Esquemas para compartir dossiers dentro de la organización."""
from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class DossierShareCreate(BaseModel):
    user_id: UUID


class OrgMemberItem(BaseModel):
    user_id: UUID
    email: str
    full_name: str
    role: str


class OrgMemberManageItem(OrgMemberItem):
    joined_at: str | None = None
    is_self: bool = False


class OrgMembersResponse(BaseModel):
    items: list[OrgMemberItem]


class OrgMembersManageResponse(BaseModel):
    items: list[OrgMemberManageItem]


class OrgMemberRolePatch(BaseModel):
    role: str


class DossierShareItem(BaseModel):
    user_id: UUID
    email: str
    full_name: str
    shared_at: str | None = None


class DossierSharesResponse(BaseModel):
    dossier_id: UUID
    items: list[DossierShareItem]


class DossierPermissions(BaseModel):
    is_owner: bool
    can_share: bool
    can_delete: bool
    can_mutate: bool
