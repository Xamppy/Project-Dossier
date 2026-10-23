"""Retención configurable de dossiers (7–90 días o sin límite)."""
from __future__ import annotations

ALLOWED_DOSSIER_RETENTION_DAYS: frozenset[int] = frozenset({7, 14, 30, 90})
DEFAULT_DOSSIER_RETENTION_DAYS = 30


def normalize_dossier_retention_days(value: int | None) -> int | None:
    """``None`` = conservar indefinidamente; entero = días hasta purga automática."""
    if value is None:
        return None
    days = int(value)
    if days <= 0:
        return None
    if days not in ALLOWED_DOSSIER_RETENTION_DAYS:
        raise ValueError(
            f"dossier_retention_days debe ser uno de {sorted(ALLOWED_DOSSIER_RETENTION_DAYS)} "
            "o null para conservar indefinidamente."
        )
    return days


def dossier_retention_days_to_frontend(value: int | None) -> str:
    if value is None:
        return "never"
    return str(value)


def dossier_retention_days_from_frontend(value: str | None) -> int | None:
    raw = (value or "").strip().lower()
    if not raw or raw == "never":
        return None
    try:
        return normalize_dossier_retention_days(int(raw))
    except ValueError:
        raise ValueError(
            f"dossier_retention_days no soportado: {value!r}. "
            f"Use never o {sorted(ALLOWED_DOSSIER_RETENTION_DAYS)}."
        ) from None
