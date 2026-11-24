"""
Personas de una reunión de calendario y elección de una de ellas (UX-CAL-03).

Con varias personas la automatización no sabe de quién hacer el dossier: no genera, y en la
generación manual el usuario elige una. Reglas en ``specs/proposals/UX-CAL-03-reunion-varias-personas.md``.
"""
from __future__ import annotations

import re
from collections.abc import Set
from typing import Any

from dossier.services.calendar_event_dossiers import (
    PERSONA_ELEGIDA,
    extract_all_persons_from_description,
)
from dossier.services.calendar_event_filters import extract_attendee_emails
from dossier.services.lusha_company import strip_accents
from dossier.utils.html_text import strip_html_to_text

MOTIVO_VARIAS_PERSONAS = (
    "La reunión tiene varias personas: ábrela en el calendario y elige de quién generar el dossier."
)

PERSONA_REQUERIDA = "CALENDAR_PERSON_REQUIRED"
PERSONA_NO_ENCONTRADA = "CALENDAR_PERSON_NOT_FOUND"

_SEPARADORES_CORREO = re.compile(r"[._\-]+")


def correos_propios(user: Any, integration: Any) -> set[str]:
    """Correos del usuario: el de su cuenta y el del calendario conectado."""
    crudos = (getattr(user, "email", None), getattr(integration, "provider_email", None))
    return {c.strip().lower() for c in crudos if isinstance(c, str) and c.strip()}


def _nombre_desde_correo(correo: str) -> str:
    """``ana.perez23+ventas@…`` → «Ana Perez»; si no queda un nombre, la parte local o el correo."""
    local = correo.split("@", 1)[0].split("+", 1)[0]
    partes = [re.sub(r"\d+", "", p) for p in _SEPARADORES_CORREO.split(local)]
    nombre = " ".join(p[:1].upper() + p[1:].lower() for p in partes if p) or local
    return nombre if len(nombre) >= 2 else correo


def _palabras(nombre: str) -> frozenset[str]:
    return frozenset(re.findall(r"\w+", strip_accents(nombre).lower()))


def _asistentes(reunion: dict[str, Any], propios: Set[str]) -> list[dict[str, str | None]]:
    """Asistentes y organizador sin el usuario ni repetidos: ``{nombre, correo}``."""
    crudos = reunion.get("asistentes")
    if not isinstance(crudos, list):
        # Eventos guardados antes de UX-CAL-03: solo hay correos en el texto de participantes.
        crudos = [{"correo": c} for c in extract_attendee_emails(reunion)]
    por_clave: dict[str, dict[str, str | None]] = {}
    for a in crudos:
        if not isinstance(a, dict) or a.get("yo") is True:
            continue
        correo = str(a.get("correo") or "").strip().lower() or None
        nombre = str(a.get("nombre") or "").strip() or None
        if correo in propios or not (correo or nombre):
            continue
        previo = por_clave.setdefault(correo or f"contacto:{nombre}".lower(), {"nombre": nombre, "correo": correo})
        previo["nombre"] = previo["nombre"] or nombre
    return list(por_clave.values())


def claves_asistentes(reunion: dict[str, Any], propios: Set[str]) -> frozenset[str]:
    """Quiénes asisten, sin el usuario y sin orden: el correo o, si falta, el nombre."""
    return frozenset((a["correo"] or a["nombre"] or "").lower() for a in _asistentes(reunion, propios))


def _mismo_nombre(declarado: str, asistente: dict[str, str | None]) -> bool:
    """Coinciden al menos dos palabras: un nombre de pila suelto no basta (BUG-2026-10-19-02)."""
    nombre = asistente["nombre"] or _nombre_desde_correo(asistente["correo"] or "")
    a, b = _palabras(declarado), _palabras(nombre)
    return min(len(a), len(b)) >= 2 and (a <= b or b <= a)


def _buscar_asistente(
    contacto: dict[str, Any], asistentes: list[dict[str, str | None]], *, unicos: bool
) -> dict[str, str | None] | None:
    if unicos:
        return asistentes[0]
    if contacto.get("email"):
        return next((a for a in asistentes if a["correo"] == contacto["email"]), None)
    coinciden = [a for a in asistentes if _mismo_nombre(contacto["full_name"], a)]
    return coinciden[0] if len(coinciden) == 1 else None


def personas_de_la_reunion(reunion: dict[str, Any], propios: Set[str]) -> list[dict[str, Any]]:
    """
    Personas de las que se puede pedir un dossier: ``{id, nombre, correo, cargo, pais}``.

    Primero los contactos declarados en la descripción, después los demás asistentes. El usuario
    (``propios`` y la marca ``yo``) no cuenta. El asunto no aporta personas: «Reunión con Acme»
    haría pasar una empresa por una persona más.
    """
    descripcion = strip_html_to_text(reunion.get("descripcion"))[:2000]
    contactos = [
        c
        for c in extract_all_persons_from_description(descripcion)
        if len(c["full_name"]) >= 2 and (c.get("email") or "") not in propios
    ]
    asistentes = _asistentes(reunion, propios)
    unicos = len(contactos) == 1 and len(asistentes) == 1

    personas: dict[str, dict[str, Any]] = {}

    def agregar(nombre: str, correo: str | None, contacto: dict[str, Any] | None = None) -> None:
        ident = correo or "contacto:" + " ".join(strip_accents(nombre).lower().split())
        c = contacto or {}
        personas.setdefault(
            ident,
            {
                "id": ident,
                "nombre": nombre,
                "correo": correo,
                "cargo": c.get("job_area"),
                "pais": c.get("country"),
                "indice": c.get("index"),
            },
        )

    for c in contactos:
        asistente = _buscar_asistente(c, asistentes, unicos=unicos) if asistentes else None
        if asistente is not None:
            asistentes.remove(asistente)
        agregar(c["full_name"], c.get("email") or (asistente or {}).get("correo"), c)
    for a in asistentes:
        agregar(a["nombre"] or _nombre_desde_correo(a["correo"] or ""), a["correo"])
    return list(personas.values())


def requiere_elegir_persona(personas: list[dict[str, Any]]) -> bool:
    return len(personas) > 1


def personas_publicas(personas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Lo que ve el cliente; ``indice`` es interno."""
    return [{k: p[k] for k in ("id", "nombre", "correo", "cargo", "pais")} for p in personas]


def elegir_persona(reunion: dict[str, Any], persona_id: str, personas: list[dict[str, Any]]) -> dict[str, Any]:
    """Copia de la reunión con la persona elegida. ``LookupError`` si no es de la reunión."""
    clave = persona_id.strip().lower()
    elegida = next((p for p in personas if p["id"] == clave), None)
    if elegida is None:
        raise LookupError(PERSONA_NO_ENCONTRADA)
    return {
        **reunion,
        PERSONA_ELEGIDA: {
            "index": elegida["indice"] or 1,
            "full_name": elegida["nombre"],
            "job_area": elegida["cargo"],
            "country": elegida["pais"],
            "email": elegida["correo"],
        },
    }
