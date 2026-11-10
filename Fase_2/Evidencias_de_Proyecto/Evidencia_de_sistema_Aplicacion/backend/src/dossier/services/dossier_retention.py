"""Retención de dossiers: un plazo fijo para todos (S6.5, objetivo específico 8).

El plazo lo fija el servidor con ``DOSSIER_RETENTION_HOURS`` (24 por omisión). El usuario ya no
elige: la columna ``users.dossier_retention_days`` quedó sin uso.
"""
from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

DEFAULT_DOSSIER_RETENTION_HOURS = 24


def dossier_retention_hours() -> int:
    """Horas que vive un dossier antes de borrarse. Un valor inválido o ≤ 0 vuelve a 24."""
    raw = os.getenv("DOSSIER_RETENTION_HOURS", "").strip()
    try:
        horas = int(raw)
    except ValueError:
        return DEFAULT_DOSSIER_RETENTION_HOURS
    return horas if horas > 0 else DEFAULT_DOSSIER_RETENTION_HOURS


def retention_cutoff(now: datetime | None = None) -> datetime:
    """Todo lo creado antes de este instante está vencido."""
    return (now or datetime.now(UTC)) - timedelta(hours=dossier_retention_hours())
