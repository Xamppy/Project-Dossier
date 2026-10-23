"""Dominio de correo corporativo de la organización (para invitaciones)."""
from __future__ import annotations

from dossier.api_errors import CORPORATE_EMAIL_REQUIRED, OrgApiError
from dossier.db.models import Organization
from dossier.services.lusha_company import email_to_company_domain

EMAIL_DOMAIN_KEY = "email_domain"


def _as_settings_dict(org: Organization) -> dict:
    s = org.settings
    return dict(s) if isinstance(s, dict) else {}


def read_org_email_domain(org: Organization) -> str | None:
    raw = _as_settings_dict(org).get(EMAIL_DOMAIN_KEY)
    if isinstance(raw, str):
        dom = raw.strip().lower()
        if dom:
            return dom
    return None


def ensure_org_email_domain(org: Organization, *, email: str) -> str:
    """Devuelve el dominio corporativo de la org; lo fija en settings si aún no existe."""
    existing = read_org_email_domain(org)
    if existing:
        return existing
    dom = email_to_company_domain(email)
    if not dom:
        raise OrgApiError(CORPORATE_EMAIL_REQUIRED)
    settings = _as_settings_dict(org)
    settings[EMAIL_DOMAIN_KEY] = dom
    org.settings = settings
    return dom


def email_matches_org_domain(org: Organization, email: str, *, fallback_admin_email: str | None = None) -> bool:
    org_dom = read_org_email_domain(org)
    if not org_dom and fallback_admin_email:
        org_dom = email_to_company_domain(fallback_admin_email)
    invite_dom = email_to_company_domain(email)
    if not org_dom or not invite_dom:
        return False
    return org_dom == invite_dom
