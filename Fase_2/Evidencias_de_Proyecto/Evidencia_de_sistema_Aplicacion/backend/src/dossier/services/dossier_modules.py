"""Datos por módulo del detalle del dossier (S5.5, S3.5, S3.6).

``GET /dossiers/{id}`` añade ``modules`` con los registros corporativos y la prensa ya
normalizados, para que el dashboard dibuje cada módulo sin leer el Markdown. Ver
specs/proposals/S5.5-dossier-por-modulos.md.

Reglas:

- ``corporate_records``: los del contrato estructurado si los trae; si no, los que el grafo
  corporativo guardó en ``dossier_data.modulos.registros_europeos``.
- ``press_mentions``: los del contrato si los trae; si no, las filas de
  ``dossier_media_mentions`` (S3.4).
- Cada elemento se valida con el contrato de S4.1. Uno inválido se descarta: la lectura nunca
  falla por datos viejos o corruptos.
- Ninguna URL que no sea ``http(s)`` sale de aquí (el frontend las usa como enlaces).
- ``datos_brutos`` (respuesta cruda del registro) nunca se devuelve.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any
from urllib.parse import urlsplit

from pydantic import ValidationError

from dossier.schemas.dossier_executive_payload import (
    CorporateRecordCitation,
    PressMention,
    SourceCitation,
)

MAX_MENCIONES = 50
MAX_REGISTROS = 50


def url_segura(url: Any) -> str | None:
    """La URL si es ``http(s)`` con dominio; ``None`` en cualquier otro caso."""
    if not isinstance(url, str):
        return None
    limpia = url.strip()
    try:
        partes = urlsplit(limpia)
    except ValueError:
        return None
    if partes.scheme.lower() not in ("http", "https") or not partes.netloc:
        return None
    return limpia


def _cita(datos: Any) -> dict[str, Any] | None:
    if not isinstance(datos, dict):
        return None
    try:
        cita = SourceCitation(**datos).model_dump(mode="json")
    except (ValidationError, TypeError):
        return None
    cita["url"] = url_segura(cita.get("url"))
    return cita


def registro_publico(datos: Any) -> dict[str, Any] | None:
    """Un ``CorporateRecordCitation`` validado, sin datos crudos y con URLs seguras."""
    if not isinstance(datos, dict):
        return None
    try:
        cita = CorporateRecordCitation(**datos)
    except (ValidationError, TypeError):
        return None
    salida = cita.model_dump(mode="json", exclude={"record": {"datos_brutos"}})
    registro = salida["record"]
    registro["url_fuente"] = url_segura(registro.get("url_fuente"))
    for presentacion in registro.get("presentaciones") or []:
        presentacion["url"] = url_segura(presentacion.get("url"))
    salida["source"]["url"] = url_segura(salida["source"].get("url"))
    return salida


def _mencion_del_contrato(datos: Any) -> dict[str, Any] | None:
    if not isinstance(datos, dict):
        return None
    try:
        mencion = PressMention(**datos).model_dump(mode="json")
    except (ValidationError, TypeError):
        return None
    mencion["url"] = url_segura(mencion.get("url"))
    mencion["source"]["url"] = url_segura(mencion["source"].get("url"))
    return mencion


def _mencion_de_fila(fila: Any) -> dict[str, Any] | None:
    titular = (getattr(fila, "title", None) or "").strip()
    if not titular:
        return None
    publicada = getattr(fila, "published_at", None)
    return {
        "headline": titular,
        "publisher": getattr(fila, "source_name", None) or "",
        "published_date": publicada.date().isoformat() if publicada else None,
        "summary": getattr(fila, "summary", None) or "",
        "url": url_segura(getattr(fila, "url", None)),
        "source": _cita(getattr(fila, "source_citation", None)),
    }


def _validos(
    elementos: Iterable[Any], convertir: Callable[[Any], dict[str, Any] | None], tope: int
) -> list[dict[str, Any]]:
    salida: list[dict[str, Any]] = []
    for elemento in elementos:
        convertido = convertir(elemento)
        if convertido is not None:
            salida.append(convertido)
            if len(salida) >= tope:
                break
    return salida


def _lista(valor: Any) -> list[Any]:
    return valor if isinstance(valor, list) else []


def modulos_del_dossier(
    dossier_data: Any,
    executive_payload: dict[str, Any] | None,
    filas_prensa: Iterable[Any],
) -> dict[str, list[dict[str, Any]]]:
    """``modules`` del detalle: registros corporativos y prensa, siempre listas."""
    payload = executive_payload if isinstance(executive_payload, dict) else {}
    datos = dossier_data if isinstance(dossier_data, dict) else {}
    crudo = datos.get("modulos")
    modulos: dict[str, Any] = crudo if isinstance(crudo, dict) else {}

    registros = _validos(_lista(payload.get("corporate_records")), registro_publico, MAX_REGISTROS)
    if not registros:
        registros = _validos(_lista(modulos.get("registros_europeos")), registro_publico, MAX_REGISTROS)

    menciones = _validos(_lista(payload.get("press_mentions")), _mencion_del_contrato, MAX_MENCIONES)
    if not menciones:
        menciones = _validos(filas_prensa, _mencion_de_fila, MAX_MENCIONES)

    return {"corporate_records": registros, "press_mentions": menciones}
