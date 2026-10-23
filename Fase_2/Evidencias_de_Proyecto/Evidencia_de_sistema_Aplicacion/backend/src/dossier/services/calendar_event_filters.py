"""
Filtros de eventos de calendario: reuniones de trabajo y asistentes externos.

Se aplica al listado en la web y a la automatización de dossiers.
"""
from __future__ import annotations

import re
from typing import Any

from dossier.db.models import CalendarIntegration, User
from dossier.services.calendar_meeting_labels import business_signal_patterns
from dossier.services.lusha_company import PERSONAL_EMAIL_DOMAINS

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.\w+")

_ONLINE_MEETING_MARKERS = (
    "meet.google.com",
    "teams.microsoft.com",
    "teams.live.com",
    "zoom.us",
    "webex.com",
    "gotomeeting.com",
    "whereby.com",
    "bluejeans.com",
)

_BUSINESS_SIGNAL_PATTERNS = business_signal_patterns()


def has_business_meeting_signals(reunion: dict[str, Any]) -> bool:
    """True si el evento declara empresa o contacto (formato de dossier en calendario)."""
    text = f"{reunion.get('tema') or ''}\n{reunion.get('descripcion') or ''}"
    return any(pat.search(text) for pat in _BUSINESS_SIGNAL_PATTERNS)


def extract_attendee_emails(reunion: dict[str, Any]) -> list[str]:
    participantes = reunion.get("participantes") or ""
    emails = _EMAIL_RE.findall(str(participantes))
    out: list[str] = []
    seen: set[str] = set()
    for em in emails:
        low = em.lower()
        if low not in seen:
            seen.add(low)
            out.append(low)
    return out


def owner_email_domain(integration: CalendarIntegration | None, user: User | None) -> str | None:
    for raw in (
        integration.provider_email if integration else None,
        user.email if user else None,
    ):
        if raw and "@" in raw:
            domain = raw.split("@", 1)[1].strip().lower()
            if domain:
                return domain
    return None


def has_online_meeting(reunion: dict[str, Any]) -> bool:
    text = f"{reunion.get('ubicacion') or ''} {reunion.get('descripcion') or ''}".lower()
    return any(marker in text for marker in _ONLINE_MEETING_MARKERS)


def is_work_meeting(reunion: dict[str, Any]) -> tuple[bool, str | None]:
    """Excluye eventos personales (día completo, recordatorios, cenas familiares, etc.)."""
    if reunion.get("todo_el_dia") is True:
        return False, "Evento de día completo (no es una reunión de trabajo)."

    if has_business_meeting_signals(reunion) or has_online_meeting(reunion):
        return True, None

    emails = extract_attendee_emails(reunion)
    if not emails:
        return False, "Sin señales de reunión de trabajo (añade Empresa: o Contacto: en la descripción)."

    domains = {em.split("@", 1)[1] for em in emails if "@" in em}
    if domains and domains.issubset(PERSONAL_EMAIL_DOMAINS):
        return False, "Solo participantes con correo personal (p. ej. familia o amigos)."

    return True, None


def has_external_attendee(reunion: dict[str, Any], owner_domain: str | None) -> tuple[bool, str | None]:
    """True solo si algún asistente tiene dominio de correo distinto al de la cuenta conectada."""
    if not owner_domain:
        return True, None

    owner = owner_domain.lower()
    emails = extract_attendee_emails(reunion)
    for em in emails:
        if "@" not in em:
            continue
        if em.split("@", 1)[1] != owner:
            return True, None

    return False, "Todos los participantes comparten el dominio de tu cuenta."


def calendar_event_passes_filters(
    reunion: dict[str, Any],
    integration: CalendarIntegration | None,
    user: User | None,
    *,
    work_meetings_only: bool = True,
    skip_internal_meetings: bool | None = None,
) -> tuple[bool, str | None]:
    """
    Devuelve (incluir, motivo_skip).

    ``skip_internal_meetings``: si True, solo reuniones con al menos un dominio externo.
    """
    if work_meetings_only:
        ok, reason = is_work_meeting(reunion)
        if not ok:
            return False, reason

    external_only = (
        skip_internal_meetings
        if skip_internal_meetings is not None
        else bool(integration.skip_internal_meetings if integration else False)
    )
    if external_only:
        domain = owner_email_domain(integration, user)
        ok, reason = has_external_attendee(reunion, domain)
        if not ok:
            return False, reason

    return True, None


def filter_calendar_reuniones(
    reuniones: list[dict[str, Any]],
    *,
    integration: CalendarIntegration | None,
    user: User | None,
    work_meetings_only: bool = True,
    skip_internal_meetings: bool | None = None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for reunion in reuniones:
        ok, _ = calendar_event_passes_filters(
            reunion,
            integration,
            user,
            work_meetings_only=work_meetings_only,
            skip_internal_meetings=skip_internal_meetings,
        )
        if ok:
            out.append(reunion)
    return out
