"""
Registro de auditoría (S4.10).

Diseño de campos: ``db/Migracion.md``, sección 13 (estándar Alloxentric, sección 9.4):
WHO (usuario, rol, organización), WHAT (acción y recurso), WHEN (instante), WHERE (IP y
User-Agent) y RESULT (estado HTTP, éxito y error).

Reglas:
- Solo inserción: ``record`` agrega filas; la base rechaza UPDATE y DELETE
  (``trg_audit_logs_inmutable``).
- Sin datos personales: ``request_data`` pasa por ``redact`` y nunca guarda el contenido
  del dossier, solo identificadores.
- Firma: ``log_hash`` es un HMAC-SHA256 de los campos del registro con la clave
  ``AUDIT_LOG_HMAC_KEY`` (o ``JWT_SECRET`` si no se define). Quien modifique una fila sin
  la clave no puede recalcular la firma, y ``verify_log_hash`` lo delata. La firma no
  cubre ``user_id`` ni ``organization_id``: la base los deja en NULL al borrar la cuenta
  (derecho al olvido) y el registro debe seguir siendo verificable.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from dossier.db.models import AuditLog

REDACTED = "[oculto]"
MAX_VALUE_CHARS = 200

_CLAVES_PERSONALES = ("email", "name", "phone", "password", "token", "secret", "linkedin", "address", "authorization")
_CLAVES_EXACTAS = frozenset({"q", "query", "search", "company", "subject", "nombre", "empresa", "correo"})

_CAMPOS_FIRMADOS = (
    "action",
    "resource_type",
    "resource_id",
    "user_role_at_time",
    "created_at",
    "ip_address",
    "user_agent",
    "http_status",
    "success",
    "error_message",
    "request_data",
    "duration_ms",
)


@dataclass(frozen=True)
class AuditEvent:
    action: str
    resource_type: str | None = None
    resource_id: UUID | None = None
    user_id: UUID | None = None
    organization_id: UUID | None = None
    user_role: str | None = None
    http_status: int | None = None
    success: bool = True
    error_message: str | None = None
    ip: str | None = None
    user_agent: str | None = None
    request_data: dict[str, Any] | None = field(default=None)
    duration_ms: int | None = None


def _es_personal(clave: str) -> bool:
    k = clave.lower()
    return k in _CLAVES_EXACTAS or any(p in k for p in _CLAVES_PERSONALES)


def redact(data: Any) -> Any:
    """Copia de ``data`` con los valores personales reemplazados y los textos largos acortados."""
    if data is None:
        return None
    if isinstance(data, Mapping):
        return {str(k): (REDACTED if _es_personal(str(k)) else redact(v)) for k, v in data.items()}
    if isinstance(data, list | tuple):
        return [redact(v) for v in data]
    if isinstance(data, str) and len(data) > MAX_VALUE_CHARS:
        return data[:MAX_VALUE_CHARS] + "…"
    return data


def _clave() -> bytes:
    secreto = (os.getenv("AUDIT_LOG_HMAC_KEY") or os.getenv("JWT_SECRET") or "").strip()
    return (secreto or "dossier-audit-sin-clave").encode("utf-8")


def _valor(fila: Any, campo: str) -> Any:
    return fila.get(campo) if isinstance(fila, Mapping) else getattr(fila, campo, None)


def _normalizar(campo: str, valor: Any) -> Any:
    if valor is None:
        return None
    if campo == "created_at" and isinstance(valor, datetime):
        return valor.astimezone(UTC).isoformat(timespec="microseconds")
    if campo in ("resource_id", "ip_address"):
        return str(valor)
    return valor


def compute_log_hash(fila: Any) -> str:
    """HMAC-SHA256 de los campos firmados (acepta un dict o una fila ``AuditLog``)."""
    canonico = {c: _normalizar(c, _valor(fila, c)) for c in _CAMPOS_FIRMADOS}
    mensaje = json.dumps(canonico, sort_keys=True, ensure_ascii=False, default=str)
    return hmac.new(_clave(), mensaje.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_log_hash(fila: Any) -> bool:
    guardada = _valor(fila, "log_hash")
    return bool(guardada) and hmac.compare_digest(str(guardada), compute_log_hash(fila))


def _corto(texto: str | None, limite: int) -> str | None:
    return texto[:limite] if texto else None


def record(db: Session, event: AuditEvent, *, now: datetime | None = None) -> AuditLog:
    """Agrega un registro firmado. No hace commit (lo decide quien llama)."""
    fila = AuditLog(
        user_id=event.user_id,
        user_role_at_time=_corto(event.user_role, 20),
        organization_id=event.organization_id,
        action=event.action[:100],
        resource_type=_corto(event.resource_type, 50),
        resource_id=event.resource_id,
        # El instante lo fija la app (no el DEFAULT de la base) para que entre en la firma.
        created_at=now or datetime.now(UTC),
        ip_address=event.ip,
        user_agent=_corto(event.user_agent, 500),
        http_status=event.http_status,
        success=event.success,
        error_message=_corto(event.error_message, 500),
        request_data=redact(event.request_data),
        duration_ms=event.duration_ms,
    )
    fila.log_hash = compute_log_hash(fila)
    db.add(fila)
    db.flush()
    return fila


def _ids(items: Iterable[Any]) -> list[str]:
    vistos: list[str] = []
    for item in items:
        valor = item.get("id") if isinstance(item, Mapping) else None
        if valor and str(valor) not in vistos:
            vistos.append(str(valor))
    return vistos


def saved_dossier_ids(saved: Mapping[str, Any] | None) -> list[str]:
    """Ids de los dossiers guardados por una generación de calendario (sin la carpeta)."""
    if not saved:
        return []
    items: list[Any] = [saved.get("corporate"), saved.get("person")]
    items.extend(saved.get("persons") or [])
    return _ids(i for i in items if i)


def dossier_ids_from_result(result: Mapping[str, Any] | None) -> list[str]:
    """Ids de dossiers en el resultado de un job (persona o calendario)."""
    if not result:
        return []
    ids = saved_dossier_ids(result.get("saved_dossiers"))
    for extra in _ids([result.get("saved_dossier")] if result.get("saved_dossier") else []):
        if extra not in ids:
            ids.append(extra)
    return ids
