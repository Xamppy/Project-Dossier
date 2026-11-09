"""Persiste las menciones de prensa de un dossier con su procedencia (S3.4).

Criterio del plan: ninguna mención se persiste sin sus cuatro campos de procedencia
(título, medio, URL y fecha de publicación) más la fecha de consulta. Una mención
incompleta no se guarda: queda solo en el texto del informe, si llegó a él.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from dossier.db.models import DossierMediaMention

# Valor que pone el agente (news/agent.py) cuando el proveedor no informa el medio.
_MEDIO_DESCONOCIDO = "desconocido"


def _fecha(valor: Any) -> datetime | None:
    """ISO 8601 (NewsAPI, ``2026-11-01T10:00:00Z``) o compacta de GDELT (``20261101T100000Z``)."""
    texto = str(valor or "").strip()
    if not texto:
        return None
    for intento in (texto.replace("Z", "+00:00"), texto):
        try:
            fecha = datetime.fromisoformat(intento)
        except ValueError:
            continue
        return fecha if fecha.tzinfo else fecha.replace(tzinfo=UTC)
    try:
        return datetime.strptime(texto, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    except ValueError:
        return None


def _fila(mencion: dict[str, Any], consulta: str) -> dict[str, Any] | None:
    """Columnas de ``dossier_media_mentions``, o ``None`` si falta algún dato de procedencia."""
    titulo = str(mencion.get("headline") or "").strip()
    medio = str(mencion.get("publisher") or "").strip()
    url = str(mencion.get("url") or "").strip()
    publicada = _fecha(mencion.get("published_date"))
    fuente = mencion.get("source") or {}
    consultada = _fecha(fuente.get("retrieved_at"))
    if not (titulo and url and publicada and consultada) or medio.lower() in ("", _MEDIO_DESCONOCIDO):
        return None
    return {
        "title": titulo,
        "url": url,
        "published_at": publicada,
        "source_name": medio[:255],
        "source_type": str(fuente.get("source_type") or "")[:50] or None,
        "summary": str(mencion.get("summary") or "").strip() or None,
        "source_citation": fuente,
        "query_context": consulta[:255],
    }


def escribir_menciones_prensa(
    db: Session,
    *,
    dossier_id: uuid.UUID,
    menciones: list[dict[str, Any]] | None,
    consulta: str,
) -> int:
    """Agrega a la sesión una fila por mención completa y devuelve cuántas.

    ``menciones`` son ``PressMention`` serializados (``model_dump(mode="json")``), tal
    como viajan en el resultado del job. Se llama antes del ``commit`` del dossier, para
    quedar en la misma transacción.
    """
    guardadas = 0
    for mencion in menciones or []:
        fila = _fila(mencion, consulta)
        if fila is None:
            continue
        db.add(DossierMediaMention(dossier_id=dossier_id, **fila))
        guardadas += 1
    return guardadas
