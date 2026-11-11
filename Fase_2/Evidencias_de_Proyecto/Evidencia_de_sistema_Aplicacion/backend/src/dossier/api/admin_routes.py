"""
Rutas HTTP de administración de plataforma (panel de operaciones).

Requieren `users.is_platform_admin = TRUE`. Otorgar con SQL tras la migración
(ver `src/dossier/db/Migracion.md`).
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from dossier.api.auth_routes import get_current_user, get_db_if_configured, load_primary_membership
from dossier.db.models import Dossier, NewsSourceSetting, Organization, OrgMembership, PlanSetting, User
from dossier.news.proveedores.registro import proveedores_instalados
from dossier.org_workspace import read_workspace_kind
from dossier.schemas.admin import (
    AdminDossierListItem,
    AdminDossierListResponse,
    AdminNewsSourceItem,
    AdminNewsSourcePatch,
    AdminNewsSourcesResponse,
    AdminOrganizationListItem,
    AdminOrganizationListResponse,
    AdminOverviewResponse,
    AdminPlanSettingItem,
    AdminPlanSettingPatch,
    AdminPlanSettingsResponse,
    AdminUserListItem,
    AdminUserListResponse,
    AdminUserRolesPatch,
)
from dossier.services.account_service import admin_delete_user_account
from dossier.services.audit_log import AuditEvent, record
from dossier.services.news_sources import PLANES, AjusteFuente, leer_ajustes, uso_de_hoy
from dossier.services.plan_limits import (
    DEFAULT_MAX_CONCURRENT,
    DEFAULT_MONTHLY_CREDITS,
    PLAN_ORDER,
    is_known_plan,
)

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


# --- UX-ADMIN-01: ajustes por plan ---------------------------------------------


def _plan_item(db: Session, plan: str, fila: PlanSetting | None) -> AdminPlanSettingItem:
    email = None
    if fila is not None and fila.updated_by_user_id is not None:
        email = db.scalar(select(User.email).where(User.id == fila.updated_by_user_id))
    return AdminPlanSettingItem(
        plan=plan,
        max_concurrent_dossiers=fila.max_concurrent_dossiers if fila else DEFAULT_MAX_CONCURRENT[plan],
        monthly_credits=fila.monthly_credits if fila else DEFAULT_MONTHLY_CREDITS[plan],
        updated_at=fila.updated_at if fila else None,
        updated_by_email=email,
    )


@router.get("/plan-settings", response_model=AdminPlanSettingsResponse)
def admin_list_plan_settings(
    _admin: AdminUserDep,
    db: Session = Depends(get_db_if_configured),
) -> AdminPlanSettingsResponse:
    """Ajustes de cada plan; un plan sin fila muestra su valor inicial."""
    filas = {f.plan: f for f in db.scalars(select(PlanSetting)).all()}
    return AdminPlanSettingsResponse(plans=[_plan_item(db, p, filas.get(p)) for p in PLAN_ORDER])


@router.patch("/plan-settings/{plan}", response_model=AdminPlanSettingItem)
def admin_patch_plan_setting(
    plan: str,
    body: AdminPlanSettingPatch,
    admin: AdminUserDep,
    db: Session = Depends(get_db_if_configured),
) -> AdminPlanSettingItem:
    """Cambia el tope de dossiers a la vez y/o los créditos al mes de un plan. Queda en ``audit_logs``.

    Los créditos se aplican a quien se registre o cambie a este plan desde ahora; el saldo de
    las organizaciones existentes no cambia.
    """
    if not is_known_plan(plan):
        raise HTTPException(status_code=404, detail="Plan no encontrado.")
    fila = db.get(PlanSetting, plan, with_for_update=True)
    antes = {
        "max_concurrent_dossiers": fila.max_concurrent_dossiers if fila else DEFAULT_MAX_CONCURRENT[plan],
        "monthly_credits": fila.monthly_credits if fila else DEFAULT_MONTHLY_CREDITS[plan],
    }
    despues = dict(antes)
    for campo in body.model_fields_set:
        despues[campo] = getattr(body, campo)
    if fila is None:
        fila = PlanSetting(plan=plan, **despues)
        db.add(fila)
    fila.max_concurrent_dossiers = despues["max_concurrent_dossiers"]
    fila.monthly_credits = despues["monthly_credits"]
    fila.updated_at = datetime.now(UTC)
    fila.updated_by_user_id = admin.id
    cambios = {c: {"antes": antes[c], "despues": despues[c]} for c in antes if antes[c] != despues[c]}
    record(
        db,
        AuditEvent(
            action="ADMIN plan_settings",
            resource_type="plan_settings",
            user_id=admin.id,
            request_data={"plan": plan, **cambios},
        ),
    )
    db.commit()
    db.refresh(fila)
    return _plan_item(db, plan, fila)


# --- UX-ADMIN-02: fuentes de noticias -------------------------------------------------------

_CAMPOS_FUENTE = (
    "enabled",
    "use_for_corporate",
    "use_for_person",
    "min_depth",
    "plans",
    "extra_credits",
    "max_results",
    "daily_limit",
)


def _valores(ajuste: AjusteFuente) -> dict[str, Any]:
    return {
        "enabled": ajuste.enabled,
        "use_for_corporate": ajuste.use_for_corporate,
        "use_for_person": ajuste.use_for_person,
        "min_depth": ajuste.min_depth,
        "plans": [p for p in PLANES if p in ajuste.plans],
        "extra_credits": ajuste.extra_credits,
        "max_results": ajuste.max_results,
        "daily_limit": ajuste.daily_limit,
    }


def _fuente_item(db: Session, clave: str, ajuste: AjusteFuente, usos: dict[str, int]) -> AdminNewsSourceItem:
    proveedor = proveedores_instalados()[clave]
    email = None
    if ajuste.updated_by_user_id is not None:
        email = db.scalar(select(User.email).where(User.id == ajuste.updated_by_user_id))
    return AdminNewsSourceItem(
        key=clave,
        name=proveedor.nombre,
        description=proveedor.descripcion or "",
        configured=proveedor.configurado(),
        key_env_var=proveedor.variable_clave,
        default_enabled=bool(proveedor.activo_por_defecto),
        used_today=usos.get(clave, 0),
        updated_at=ajuste.updated_at,
        updated_by_email=email,
        **_valores(ajuste),
    )


@router.get("/news-sources", response_model=AdminNewsSourcesResponse)
def admin_list_news_sources(
    _admin: AdminUserDep,
    db: Session = Depends(get_db_if_configured),
) -> AdminNewsSourcesResponse:
    """Fuentes de noticias instaladas, sus ajustes y las consultas de hoy (UTC)."""
    ajustes = leer_ajustes(db)
    usos = uso_de_hoy(db)
    return AdminNewsSourcesResponse(sources=[_fuente_item(db, c, a, usos) for c, a in ajustes.items()])


@router.patch("/news-sources/{key}", response_model=AdminNewsSourceItem)
def admin_patch_news_source(
    key: str,
    body: AdminNewsSourcePatch,
    admin: AdminUserDep,
    db: Session = Depends(get_db_if_configured),
) -> AdminNewsSourceItem:
    """Cambia los ajustes de una fuente. Cada cambio queda en ``audit_logs`` con antes y después."""
    if key not in proveedores_instalados():
        raise HTTPException(status_code=404, detail="Fuente de noticias no encontrada.")
    actual = leer_ajustes(db)[key]
    antes = _valores(actual)
    despues = dict(antes)
    for campo in body.model_fields_set:
        despues[campo] = getattr(body, campo)
    planes = set(despues["plans"])

    fila = db.get(NewsSourceSetting, key, with_for_update=True)
    if fila is None:
        fila = NewsSourceSetting(provider_key=key)
        db.add(fila)
    fila.enabled = bool(despues["enabled"])
    fila.use_for_corporate = bool(despues["use_for_corporate"])
    fila.use_for_person = bool(despues["use_for_person"])
    fila.min_depth = str(despues["min_depth"])
    fila.plan_free, fila.plan_pro, fila.plan_enterprise = ("free" in planes, "pro" in planes, "enterprise" in planes)
    fila.extra_credits = int(despues["extra_credits"])
    fila.max_results = int(despues["max_results"])
    fila.daily_limit = despues["daily_limit"]
    fila.updated_at = datetime.now(UTC)
    fila.updated_by_user_id = admin.id

    cambios = {c: {"antes": antes[c], "despues": despues[c]} for c in _CAMPOS_FUENTE if antes[c] != despues[c]}
    if cambios:
        record(
            db,
            AuditEvent(
                action="ADMIN news_source_settings",
                resource_type="news_source_settings",
                user_id=admin.id,
                request_data={"source": key, "cambios": cambios},
            ),
        )
    db.commit()
    return _fuente_item(db, key, leer_ajustes(db)[key], uso_de_hoy(db))

