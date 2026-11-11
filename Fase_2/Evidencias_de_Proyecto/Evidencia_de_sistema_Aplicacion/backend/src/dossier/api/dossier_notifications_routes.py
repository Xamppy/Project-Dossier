"""Canal SSE de notificaciones del dashboard (S5.2): ``GET /dossier-notifications/stream``.

Misma autenticación y visibilidad por rol que ``GET /dossiers``. El primer evento
``dossiers`` trae el mismo cuerpo que ``GET /dossiers?limit=25``; los siguientes, solo
cuando la lista cambia. Ver services/dossier_notifications_stream.py.
"""
from __future__ import annotations

import hashlib
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import Select, select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from dossier.api.auth_routes import OrgAuthContext, get_db_if_configured, get_org_auth_context
from dossier.db.models import Dossier, OrgMembership, User
from dossier.services.dossier_folder_utils import build_dossier_list_entries
from dossier.services.dossier_notifications_stream import (
    LIMITE_LISTA,
    LectorHuella,
    LectorLista,
    check_seconds,
    max_seconds,
    stream_dossier_list,
)
from dossier.services.dossier_visibility import apply_dossier_visibility

router = APIRouter(tags=["Dossiers"])


def lectores_de_lista(
    db: Session,
    *,
    user_id: UUID,
    org_id: UUID,
    role: str | None,
    tz_name: str,
) -> tuple[LectorHuella, LectorLista]:
    """Lectores para el stream. Cada uno cierra su transacción al terminar.

    Sin el ``rollback`` la sesión quedaría en transacción y cada pestaña retendría una
    conexión del pool durante todo el stream (lo mismo que se corrigió en S4.8).
    """

    def visibles(stmt: Select) -> Select:
        return (
            apply_dossier_visibility(stmt, user_id=user_id, organization_id=org_id, role=role)
            .order_by(Dossier.created_at.desc())
            .limit(LIMITE_LISTA)
        )

    def huella() -> str | None:
        try:
            miembro = db.execute(
                select(OrgMembership.id)
                .join(User, User.id == OrgMembership.user_id)
                .where(
                    OrgMembership.user_id == user_id,
                    OrgMembership.organization_id == org_id,
                    User.is_active.is_(True),
                )
            ).first()
            if miembro is None:
                return None
            filas = db.execute(
                visibles(select(Dossier.id, Dossier.status, Dossier.dossier_folder_id))
            ).all()
            texto = "|".join(f"{i}:{s}:{f}" for i, s, f in filas)
            return hashlib.sha256(texto.encode("utf-8")).hexdigest()
        finally:
            db.rollback()

    def lista() -> dict[str, Any] | None:
        try:
            db.expire_all()
            filas = list(db.execute(visibles(select(Dossier))).scalars().all())
            return {
                "organization_id": str(org_id),
                "items": build_dossier_list_entries(filas, tz_name=tz_name),
            }
        finally:
            db.rollback()

    async def leer_huella() -> str | None:
        return await run_in_threadpool(huella)

    async def leer_lista() -> dict[str, Any] | None:
        return await run_in_threadpool(lista)

    return leer_huella, leer_lista


@router.get("/dossier-notifications/stream")
async def api_stream_notificaciones(
    ctx: Annotated[OrgAuthContext, Depends(get_org_auth_context)],
    db: Session = Depends(get_db_if_configured),
) -> StreamingResponse:
    user, org = ctx.user, ctx.org
    leer_huella, leer_lista = lectores_de_lista(
        db,
        user_id=user.id,
        org_id=org.id,
        role=ctx.role,
        tz_name=getattr(user, "timezone", None) or "UTC",
    )
    return StreamingResponse(
        stream_dossier_list(
            leer_huella,
            leer_lista,
            check_seconds=check_seconds(),
            max_seconds=max_seconds(),
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
