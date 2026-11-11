"""Datos de los planes para las pantallas (UX-ADMIN-03)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from dossier.api.auth_routes import get_current_user, get_db_if_configured
from dossier.db.models import User
from dossier.schemas.admin import BillingPlanItem, BillingPlansResponse
from dossier.services.plan_limits import PLAN_ORDER, monthly_credits

router = APIRouter(prefix="/billing", tags=["Planes"])


@router.get("/plans", response_model=BillingPlansResponse)
def billing_plans(
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db_if_configured),
) -> BillingPlansResponse:
    """Créditos al mes de cada plan, según los fija el admin de plataforma."""
    return BillingPlansResponse(
        plans=[BillingPlanItem(plan=p, monthly_credits=monthly_credits(db, p)) for p in PLAN_ORDER]
    )
