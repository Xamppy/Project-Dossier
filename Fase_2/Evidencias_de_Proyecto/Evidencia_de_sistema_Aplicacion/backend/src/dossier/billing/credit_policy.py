"""Política de créditos compartida (generación manual, calendario y jobs)."""
from __future__ import annotations

import os

from fastapi import HTTPException

from dossier.db.models import Organization
from dossier.schemas.dossier_generation import DEPTH_CREDITS, DossierDepth

# Módulo identidad (persona) — alineado con plan básico = 1 crédito.
PERSON_IDENTITY_CREDITS = 1


def credit_charging_enabled() -> bool:
    raw = os.getenv("DOSSIER_CHARGE_CREDITS", "true")
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def enterprise_unlimited(org: Organization) -> bool:
    return (org.plan or "").strip().lower() == "enterprise"


def assert_sufficient_credits(org: Organization, cost: int, *, charge: bool | None = None) -> None:
    """HTTP 402 si no hay saldo (Enterprise ilimitado y cobro desactivado exentos)."""
    if charge is None:
        charge = credit_charging_enabled()
    if not charge or cost <= 0 or enterprise_unlimited(org):
        return
    if org.credits_balance < cost:
        raise HTTPException(
            status_code=402,
            detail=(
                f"Créditos insuficientes: se requieren {cost} y la organización tiene "
                f"{org.credits_balance}."
            ),
        )


def person_research_credit_cost() -> int:
    return PERSON_IDENTITY_CREDITS if credit_charging_enabled() else 0


def calendar_event_credit_estimate(
    *,
    has_corporate: bool,
    has_person: bool = False,
    person_count: int = 0,
    depth: DossierDepth = "standard",
    charge: bool | None = None,
) -> int:
    """Créditos máximos si todo sale bien (corporativo + persona(s))."""
    if charge is None:
        charge = credit_charging_enabled()
    if not charge:
        return 0
    total = 0
    if has_corporate:
        total += DEPTH_CREDITS[depth]
    pc = person_count if person_count > 0 else (1 if has_person else 0)
    total += pc * PERSON_IDENTITY_CREDITS
    return total
