"""
Middleware de auditoría (S4.10): toda lectura y generación de dossier queda registrada.

Criterio del plan: "con actor, organización, recurso e instante". Se registra cada
petición a una ruta de ``AUDITED_ROUTES``, **también las que fallan** (401, 403, 404,
500): un intento de leer un dossier ajeno es justamente lo que la auditoría debe ver.

- Acción: verbo HTTP + plantilla de la ruta (``GET /dossiers/{dossier_id}``), como pide
  Migracion.md, sección 13. La plantilla, no la URL concreta: el id va en ``resource_id``.
- Actor: se lee del JWT sin consultar la base; sin token válido queda anónimo.
- Recurso: el parámetro de ruta, o el ``id`` de la respuesta en las generaciones.
- La escritura usa la misma sesión que la API (respeta ``dependency_overrides``) y, si
  falla, solo se registra en el log: la respuesta al usuario no cambia.
"""
from __future__ import annotations

import ipaddress
import json
import logging
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from jwt.exceptions import PyJWTError
from starlette.concurrency import run_in_threadpool
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from dossier.api.auth_routes import get_db_if_configured
from dossier.security.jwt_tokens import decode_access_token
from dossier.services.audit_log import AuditEvent, record

logger = logging.getLogger(__name__)

_MAX_CUERPO = 64 * 1024


@dataclass(frozen=True)
class AuditRule:
    resource_type: str
    id_param: str | None = None


AUDITED_ROUTES: dict[str, AuditRule] = {
    # Lectura
    "/dossiers": AuditRule("dossier"),
    "/dossiers/{dossier_id}": AuditRule("dossier", "dossier_id"),
    "/dossiers/folders/{folder_id}": AuditRule("dossier_folder", "folder_id"),
    "/dossiers/{dossier_id}/shares": AuditRule("dossier", "dossier_id"),
    "/dossiers/{dossier_id}/shares/{target_user_id}": AuditRule("dossier", "dossier_id"),
    "/admin/dossiers": AuditRule("dossier"),
    "/dossier-generation-jobs": AuditRule("dossier_generation_job"),
    "/dossier-generation-jobs/{job_id}": AuditRule("dossier_generation_job", "job_id"),
    "/dossier-generation-jobs/{job_id}/cancel": AuditRule("dossier_generation_job", "job_id"),
    "/dossier-generation-jobs/{job_id}/stream": AuditRule("dossier_generation_job", "job_id"),
    # Generación
    "/dossiers/corporate/generate": AuditRule("dossier"),
    "/dossiers/person/research": AuditRule("dossier"),
    "/calendario/generar-dossiers": AuditRule("dossier"),
    "/calendario/generar-dossiers-google": AuditRule("dossier"),
    "/calendario/generar-dossiers-outlook": AuditRule("dossier"),
}


def audit_rule(method: str | None, template: str | None) -> AuditRule | None:
    if not template or not method or method.upper() in ("OPTIONS", "HEAD"):
        return None
    return AUDITED_ROUTES.get(template)


@dataclass(frozen=True)
class Actor:
    user_id: UUID | None = None
    organization_id: UUID | None = None
    role: str | None = None


def _uuid(valor: Any) -> UUID | None:
    try:
        return UUID(str(valor)) if valor else None
    except (ValueError, TypeError):
        return None


def actor_from_authorization(header: str | None) -> Actor:
    if not header or not header.lower().startswith("bearer "):
        return Actor()
    try:
        claims = decode_access_token(header[7:].strip())
    except (PyJWTError, RuntimeError, ValueError):
        return Actor()
    rol = claims.get("role")
    return Actor(
        user_id=_uuid(claims.get("sub")),
        organization_id=_uuid(claims.get("org_id")),
        role=rol if isinstance(rol, str) else None,
    )


def resource_id_from_body(body: Any) -> UUID | None:
    if not isinstance(body, Mapping):
        return None
    for clave in ("id", "dossier_id"):
        if body.get(clave):
            return _uuid(body.get(clave))
    for anidado in ("saved_dossier", "job"):
        valor = body.get(anidado)
        if isinstance(valor, Mapping) and valor.get("id"):
            return _uuid(valor.get("id"))
    return None


def _plantilla(scope: Scope) -> str | None:
    ruta = scope.get("route")
    return getattr(ruta, "path_format", None) or getattr(ruta, "path", None)


def _cabecera(scope: Scope, nombre: bytes) -> str | None:
    for clave, valor in scope.get("headers") or []:
        if clave.lower() == nombre:
            return valor.decode("latin-1")
    return None


def _ip(scope: Scope) -> str | None:
    cliente = scope.get("client")
    try:
        return str(ipaddress.ip_address(cliente[0])) if cliente else None
    except ValueError:
        return None


def _consulta(scope: Scope) -> dict[str, Any] | None:
    from urllib.parse import parse_qsl

    crudo = (scope.get("query_string") or b"").decode("latin-1")
    pares = parse_qsl(crudo, keep_blank_values=True)
    return {"params": dict(pares)} if pares else None


def _detalle_error(cuerpo: Any, estado: int) -> str:
    detalle = cuerpo.get("detail") if isinstance(cuerpo, Mapping) else None
    if isinstance(detalle, Mapping):
        detalle = detalle.get("code") or detalle.get("message")
    return str(detalle)[:300] if isinstance(detalle, str) and detalle else f"HTTP {estado}"


class AuditMiddleware:
    """ASGI puro: no interfiere con el streaming (SSE) ni con el cuerpo de la respuesta."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        inicio = time.perf_counter()
        estado: int | None = None
        capturar = False
        partes: list[bytes] = []
        tamano = 0

        async def _send(message: Message) -> None:
            nonlocal estado, capturar, tamano
            if message["type"] == "http.response.start":
                estado = int(message["status"])
                tipo = ""
                for clave, valor in message.get("headers") or []:
                    if clave.lower() == b"content-type":
                        tipo = valor.decode("latin-1")
                capturar = "application/json" in tipo
            elif message["type"] == "http.response.body" and capturar and tamano <= _MAX_CUERPO:
                trozo = message.get("body", b"")
                partes.append(trozo)
                tamano += len(trozo)
            await send(message)

        error: BaseException | None = None
        try:
            await self.app(scope, receive, _send)
        except BaseException as exc:
            error = exc
            raise
        finally:
            regla = audit_rule(scope.get("method"), _plantilla(scope))
            if regla is not None:
                duracion = int((time.perf_counter() - inicio) * 1000)
                cuerpo = b"".join(partes) if tamano <= _MAX_CUERPO else b""
                await run_in_threadpool(
                    self._guardar, scope, regla, estado or 500, error, cuerpo, duracion
                )

    def _evento(
        self,
        scope: Scope,
        regla: AuditRule,
        estado: int,
        error: BaseException | None,
        cuerpo_crudo: bytes,
        duracion: int,
    ) -> AuditEvent:
        cuerpo: Any = None
        if cuerpo_crudo:
            try:
                cuerpo = json.loads(cuerpo_crudo)
            except ValueError:
                cuerpo = None
        if regla.id_param:
            recurso = _uuid((scope.get("path_params") or {}).get(regla.id_param))
        else:
            recurso = resource_id_from_body(cuerpo)
        exito = error is None and estado < 400
        mensaje = None
        if error is not None:
            mensaje = f"{type(error).__name__}: {str(error)[:200]}"
        elif not exito:
            mensaje = _detalle_error(cuerpo, estado)
        actor = actor_from_authorization(_cabecera(scope, b"authorization"))
        return AuditEvent(
            action=f"{scope.get('method')} {_plantilla(scope)}",
            resource_type=regla.resource_type,
            resource_id=recurso,
            user_id=actor.user_id,
            organization_id=actor.organization_id,
            user_role=actor.role,
            http_status=estado,
            success=exito,
            error_message=mensaje,
            ip=_ip(scope),
            user_agent=_cabecera(scope, b"user-agent"),
            request_data=_consulta(scope),
            duration_ms=duracion,
        )

    def _guardar(
        self,
        scope: Scope,
        regla: AuditRule,
        estado: int,
        error: BaseException | None,
        cuerpo: bytes,
        duracion: int,
    ) -> None:
        app = scope.get("app")
        overrides = getattr(app, "dependency_overrides", {}) or {}
        proveedor = overrides.get(get_db_if_configured, get_db_if_configured)
        try:
            fuente = proveedor()
            db = next(fuente) if hasattr(fuente, "__next__") else fuente
        except (HTTPException, StopIteration):
            return  # sin base configurada no hay dónde registrar (pruebas sin Postgres)
        try:
            record(db, self._evento(scope, regla, estado, error, cuerpo, duracion))
            db.commit()
        except Exception:
            logger.warning("No se pudo guardar el registro de auditoría", exc_info=True)
            try:
                db.rollback()
            except Exception:
                logger.debug("rollback de auditoría falló", exc_info=True)
        finally:
            cerrar = getattr(fuente, "close", None)
            if callable(cerrar):
                try:
                    cerrar()
                except Exception:
                    logger.debug("cierre de sesión de auditoría falló", exc_info=True)
