"""Tope de dossiers generándose a la vez por usuario según el plan (UX-ADMIN-01).

Ver specs/proposals/UX-ADMIN-01-limites-por-plan.md. El admin de plataforma cambia los
valores en ``plan_settings`` desde ``/dashboard/admin``; aquí se aplican al encolar.

- Cuentan solo los pedidos del usuario (``person_manual``, ``calendar_manual``) en cola o en
  curso, de su organización, creados en los últimos ``DOSSIER_CONCURRENCY_WINDOW_MINUTES``.
  La ventana evita que un trabajo colgado por una caída del servidor bloquee al usuario.
- Se bloquea la fila del usuario (``FOR UPDATE``) antes de contar: dos pedidos simultáneos
  no pueden saltarse el tope. El bloqueo dura hasta el ``commit`` de quien encola.
- Se responde 409 (no 429): el frontend traduce todo 429 como «espera N segundos».
"""
from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Final
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from dossier.billing.plan_catalog import ALLOWED_PLANS, normalize_plan
from dossier.db.models import DossierGenerationJob, Organization, PlanSetting, User

DEFAULT_MAX_CONCURRENT: Final[dict[str, int]] = {"free": 1, "pro": 3, "enterprise": 10}
# UX-ADMIN-03: créditos al mes de cada plan (valores iniciales; los cambia el admin de plataforma).
DEFAULT_MONTHLY_CREDITS: Final[dict[str, int]] = {"free": 10, "pro": 500, "enterprise": 50_000}
MIN_MONTHLY_CREDITS: Final = 0
MAX_MONTHLY_CREDITS: Final = 1_000_000
MIN_CONCURRENT: Final = 1
MAX_CONCURRENT: Final = 100
PLAN_ORDER: Final = ("free", "pro", "enterprise")
LIMIT_ERROR_CODE: Final = "CONCURRENT_DOSSIER_LIMIT"

_JOBS_CONTADOS: Final = ("person_manual", "calendar_manual", "corporate_manual")
_ACTIVOS: Final = ("queued", "running")
DEFAULT_WINDOW_MINUTES: Final = 30


def window_minutes() -> int:
    """Antigüedad máxima de un trabajo activo para que cuente (``DOSSIER_CONCURRENCY_WINDOW_MINUTES``)."""
    try:
        valor = int((os.getenv("DOSSIER_CONCURRENCY_WINDOW_MINUTES") or "").strip() or DEFAULT_WINDOW_MINUTES)
    except ValueError:
        return DEFAULT_WINDOW_MINUTES
    return valor if valor > 0 else DEFAULT_WINDOW_MINUTES


def is_known_plan(plan: str) -> bool:
    return plan in ALLOWED_PLANS


def max_concurrent_dossiers(db: Session, plan: str | None) -> int:
    """Tope del plan; sin fila en ``plan_settings``, el valor inicial."""
    pid = normalize_plan(plan)
    valor = db.scalar(select(PlanSetting.max_concurrent_dossiers).where(PlanSetting.plan == pid))
    return int(valor) if valor is not None else DEFAULT_MAX_CONCURRENT[pid]


def monthly_credits(db: Session | None, plan: str | None) -> int:
    """Créditos al mes del plan; sin fila (o sin base), el valor inicial."""
    pid = normalize_plan(plan)
    if db is not None:
        valor = db.scalar(select(PlanSetting.monthly_credits).where(PlanSetting.plan == pid))
        if valor is not None:
            return int(valor)
    return DEFAULT_MONTHLY_CREDITS[pid]


def active_dossier_jobs(db: Session, *, user_id: UUID, organization_id: UUID, now: datetime | None = None) -> int:
    desde = (now or datetime.now(UTC)) - timedelta(minutes=window_minutes())
    return int(
        db.scalar(
            select(func.count())
            .select_from(DossierGenerationJob)
            .where(
                DossierGenerationJob.requested_by_user_id == user_id,
                DossierGenerationJob.organization_id == organization_id,
                DossierGenerationJob.status.in_(_ACTIVOS),
                DossierGenerationJob.job_type.in_(_JOBS_CONTADOS),
                DossierGenerationJob.created_at >= desde,
            )
        )
        or 0
    )


def assert_can_start_dossiers(db: Session, *, user: User, org: Organization, nuevos: int = 1) -> None:
    """Lanza 409 si ``nuevos`` trabajos más superan el tope del plan.

    Bloquea la fila del usuario: el llamador debe crear sus trabajos y hacer ``commit`` en la
    misma transacción para que el bloqueo cubra la cuenta y el alta.
    """
    if nuevos <= 0:
        return
    db.execute(select(User.id).where(User.id == user.id).with_for_update())
    limite = max_concurrent_dossiers(db, org.plan)
    activos = active_dossier_jobs(db, user_id=user.id, organization_id=org.id)
    if activos + nuevos > limite:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail={"code": LIMIT_ERROR_CODE, "limit": limite, "active": activos},
        )
