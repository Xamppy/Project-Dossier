"""
Contexto de empresa para personalizar dossiers (persistido en `organizations.settings`).

Clave JSON: ``dossier_context`` con ``company_summary`` e ``industry_or_area`` (texto libre).
"""
from __future__ import annotations

from dossier.db.models import Organization

CONTEXT_KEY = "dossier_context"


def _as_settings_dict(org: Organization) -> dict:
    s = org.settings
    return dict(s) if isinstance(s, dict) else {}


def read_dossier_context(org: Organization) -> tuple[str | None, str | None]:
    """Devuelve (resumen de empresa, área/sector) o (None, None) si no hay datos."""
    raw = _as_settings_dict(org).get(CONTEXT_KEY)
    if not isinstance(raw, dict):
        return None, None
    summary = (raw.get("company_summary") or "").strip() or None
    industry = (raw.get("industry_or_area") or "").strip() or None
    return summary, industry


def format_dossier_context_for_prompt(org: Organization) -> str:
    """Bloque de texto para prompts (vacío si no hay nada configurado)."""
    summary, industry = read_dossier_context(org)
    if not summary and not industry:
        return ""
    lines = [
        "Contexto de la organización del cliente (personalizar el análisis según este perfil):",
    ]
    if summary:
        lines.append(f"- Qué es la empresa / actividad: {summary}")
    if industry:
        lines.append(f"- Área o sector de trabajo: {industry}")
    return "\n".join(lines)


def apply_dossier_context_patch(
    org: Organization,
    *,
    company_summary: str,
    industry_or_area: str,
) -> None:
    """
    Actualiza ``settings.dossier_context`` (merge con el resto de ``settings``).
    Cadenas vacías tras strip eliminan cada campo.
    """
    settings = _as_settings_dict(org)
    ctx: dict[str, str] = {}
    s = company_summary.strip()
    i = industry_or_area.strip()
    if s:
        ctx["company_summary"] = s
    if i:
        ctx["industry_or_area"] = i
    if ctx:
        settings[CONTEXT_KEY] = ctx
    else:
        settings.pop(CONTEXT_KEY, None)
    org.settings = settings
