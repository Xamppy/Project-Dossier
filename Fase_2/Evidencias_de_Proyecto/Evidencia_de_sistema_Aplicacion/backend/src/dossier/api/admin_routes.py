"""
Rutas HTTP de administración de plataforma (panel de operaciones).

Requieren `users.is_platform_admin = TRUE`. Otorgar con SQL tras la migración
(ver `src/dossier/db/Migracion.md`).
"""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from dossier.api.auth_routes import get_current_user, get_db_if_configured, load_primary_membership
from dossier.db.models import Dossier, Organization, OrgMembership, User
from dossier.org_workspace import read_workspace_kind
from dossier.schemas.admin import (
    AdminDossierListItem,
    AdminDossierListResponse,
    AdminOrganizationListItem,
    AdminOrganizationListResponse,
    AdminOverviewResponse,
    AdminUserListItem,
    AdminUserListResponse,
    AdminUserRolesPatch,
)
from dossier.services.account_service import admin_delete_user_account

router = APIRouter(prefix="/admin", tags=["Administración plataforma"])


def require_platform_admin(
    user: User = Depends(get_current_user),
) -> User:
    if not user.is_platform_admin:
        raise HTTPException(
            status_code=403,
            detail="Se requiere rol de administrador de plataforma.",
        )
    return user


AdminUserDep = Annotated[User, Depends(require_platform_admin)]


def _build_admin_user_item(db: Session, u: User) -> AdminUserListItem:
    pair = load_primary_membership(db, u.id)
    dossiers_count = db.execute(
        select(func.count()).select_from(Dossier).where(Dossier.requested_by_user_id == u.id)
    ).scalar_one()
    dc = int(dossiers_count or 0)
    if pair:
        org, _ = pair
        wk = read_workspace_kind(org)
        return AdminUserListItem(
            id=u.id,
            email=u.email,
            full_name=u.full_name,
            is_active=u.is_active,
            is_platform_admin=bool(u.is_platform_admin),
            created_at=u.created_at,
            organization_id=org.id,
            organization_name=org.name,
            workspace_kind=wk,
            plan=org.plan,
            credits_balance=org.credits_balance,
            credits_monthly_limit=org.credits_monthly_limit,
            dossiers_count=dc,
        )
    return AdminUserListItem(
        id=u.id,
        email=u.email,
        full_name=u.full_name,
        is_active=u.is_active,
        is_platform_admin=bool(u.is_platform_admin),
        created_at=u.created_at,
        dossiers_count=dc,
    )


@router.patch(
    "/users/{user_id}",
    response_model=AdminUserListItem,
    operation_id="admin_patch_user_roles",
)
@router.put(
    "/users/{user_id}",
    response_model=AdminUserListItem,
    operation_id="admin_put_user_roles",
)
def admin_patch_user_roles(
    user_id: UUID,
    body: AdminUserRolesPatch,
    admin: AdminUserDep,
    db: Session = Depends(get_db_if_configured),
) -> AdminUserListItem:
    target = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if target is None:
        raise HTTPException(
            status_code=404,
            detail="Usuario no encontrado para el id indicado.",
        )

    if body.is_platform_admin is False and user_id == admin.id:
        raise HTTPException(
            status_code=400,
            detail="No puedes quitarte el rol de administrador de plataforma a ti mismo.",
        )
    target.is_platform_admin = body.is_platform_admin
    db.add(target)

    db.commit()
    db.refresh(target)
    return _build_admin_user_item(db, target)


@router.delete("/users/{user_id}", status_code=204)
def admin_delete_user(
    user_id: UUID,
    admin: AdminUserDep,
    db: Session = Depends(get_db_if_configured),
) -> None:
    target = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if target is None:
        raise HTTPException(
            status_code=404,
            detail="Usuario no encontrado para el id indicado.",
        )
    admin_delete_user_account(db, actor=admin, target=target)


@router.get("/overview", response_model=AdminOverviewResponse)
def admin_overview(
    _: AdminUserDep,
    db: Session = Depends(get_db_if_configured),
) -> AdminOverviewResponse:
    users_total = db.execute(select(func.count()).select_from(User)).scalar_one()
    organizations_total = db.execute(select(func.count()).select_from(Organization)).scalar_one()
    dossiers_total = db.execute(select(func.count()).select_from(Dossier)).scalar_one()
    return AdminOverviewResponse(
        users_total=int(users_total or 0),
        organizations_total=int(organizations_total or 0),
        dossiers_total=int(dossiers_total or 0),
    )


@router.get("/users", response_model=AdminUserListResponse)
def admin_list_users(
    _: AdminUserDep,
    db: Session = Depends(get_db_if_configured),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=100_000),
) -> AdminUserListResponse:
    total = db.execute(select(func.count()).select_from(User)).scalar_one()
    users = (
        db.execute(select(User).order_by(User.created_at.desc()).offset(offset).limit(limit))
        .scalars()
        .all()
    )
    items = [_build_admin_user_item(db, u) for u in users]
    return AdminUserListResponse(total=int(total or 0), items=items)


@router.get("/organizations", response_model=AdminOrganizationListResponse)
def admin_list_organizations(
    _: AdminUserDep,
    db: Session = Depends(get_db_if_configured),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=100_000),
) -> AdminOrganizationListResponse:
    total = db.execute(select(func.count()).select_from(Organization)).scalar_one()
    orgs = (
        db.execute(select(Organization).order_by(Organization.created_at.desc()).offset(offset).limit(limit))
        .scalars()
        .all()
    )
    items: list[AdminOrganizationListItem] = []
    for org in orgs:
        members_count = db.execute(
            select(func.count()).select_from(OrgMembership).where(OrgMembership.organization_id == org.id)
        ).scalar_one()
        dossiers_count = db.execute(
            select(func.count()).select_from(Dossier).where(Dossier.organization_id == org.id)
        ).scalar_one()
        items.append(
            AdminOrganizationListItem(
                id=org.id,
                name=org.name,
                slug=org.slug,
                plan=org.plan,
                credits_balance=org.credits_balance,
                credits_monthly_limit=org.credits_monthly_limit,
                is_active=org.is_active,
                members_count=int(members_count or 0),
                dossiers_count=int(dossiers_count or 0),
                created_at=org.created_at,
                workspace_kind=read_workspace_kind(org),
            )
        )
    return AdminOrganizationListResponse(total=int(total or 0), items=items)


@router.get("/dossiers", response_model=AdminDossierListResponse)
def admin_list_dossiers(
    _: AdminUserDep,
    db: Session = Depends(get_db_if_configured),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=100_000),
) -> AdminDossierListResponse:
    total = db.execute(select(func.count()).select_from(Dossier)).scalar_one()
    stmt = (
        select(Dossier, Organization, User.email)
        .join(Organization, Organization.id == Dossier.organization_id)
        .join(User, User.id == Dossier.requested_by_user_id)
        .order_by(Dossier.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    rows = db.execute(stmt).all()
    items = [
        AdminDossierListItem(
            id=d.id,
            organization_id=d.organization_id,
            organization_name=org.name,
            workspace_kind=read_workspace_kind(org),
            requested_by_user_id=d.requested_by_user_id,
            requested_by_email=user_email,
            subject_name=d.subject_name,
            subject_email=d.subject_email,
            status=d.status,
            credits_consumed=d.credits_consumed,
            created_at=d.created_at,
        )
        for d, org, user_email in rows
    ]
    return AdminDossierListResponse(total=int(total or 0), items=items)
