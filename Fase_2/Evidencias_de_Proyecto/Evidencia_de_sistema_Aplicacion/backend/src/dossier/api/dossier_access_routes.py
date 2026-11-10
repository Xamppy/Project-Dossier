"""Canje del enlace de un solo uso del correo (S6.2). Sin sesión: el token es la credencial.

``POST /dossier-access`` con ``{"token": "…"}``. El token va en el cuerpo, no en la URL, para que
no quede en los logs de acceso.
"""
from __future__ import annotations

import ipaddress
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from dossier.api.auth_routes import get_db_if_configured
from dossier.security.rate_limit import limit_access_link
from dossier.services.audit_log import AuditEvent, record
from dossier.services.dossier_access_links import canjear_enlace

logger = logging.getLogger(__name__)

router = APIRouter(tags=["dossier-access"])

ENLACE_INVALIDO = "El enlace ya no es válido."


class CanjeEnlace(BaseModel):
    token: str = Field(default="", max_length=200)


def _ip(request: Request) -> str | None:
    """IP válida para la columna INET de ``audit_logs``; si no lo es, ninguna."""
    try:
        return str(ipaddress.ip_address(request.client.host)) if request.client else None
    except ValueError:
        return None


def _auditar(db: Session, request: Request, dossier: Any | None) -> None:
    """Registro del canje sin el token. Un fallo de auditoría no cambia la respuesta (S4.10)."""
    try:
        with db.begin_nested():
            record(
                db,
                AuditEvent(
                    action="ACCESS dossier_link",
                    resource_type="dossier",
                    resource_id=dossier.id if dossier else None,
                    user_id=dossier.requested_by_user_id if dossier else None,
                    organization_id=dossier.organization_id if dossier else None,
                    http_status=200 if dossier else 410,
                    success=dossier is not None,
                    error_message=None if dossier else "enlace no válido",
                    ip=_ip(request),
                    user_agent=request.headers.get("user-agent"),
                ),
            )
        db.commit()
    except Exception:
        logger.warning("No se pudo auditar el canje de un enlace de acceso", exc_info=True)
        db.rollback()


@router.post("/dossier-access", dependencies=[Depends(limit_access_link)])
def redeem_dossier_access_link(
    body: CanjeEnlace,
    request: Request,
    db: Session = Depends(get_db_if_configured),
) -> dict[str, Any]:
    """Gasta el enlace y devuelve el dossier en solo lectura. 410 si no sirve, sin decir por qué."""
    dossier = canjear_enlace(db, body.token.strip())
    _auditar(db, request, dossier)
    if dossier is None:
        raise HTTPException(status_code=410, detail=ENLACE_INVALIDO)
    data = dossier.dossier_data if isinstance(dossier.dossier_data, dict) else {}
    return {
        "subject_name": dossier.subject_name,
        "body": data.get("body") if isinstance(data.get("body"), str) else "",
        "created_at": dossier.created_at.isoformat() if dossier.created_at else None,
        "output_language": data.get("output_language") or "es",
    }
