"""Cliente HTTP del proveedor de noticias decidido en ADR 0004 (GDELT + NewsAPI).

Solo hace la llamada HTTP y devuelve la lista cruda de articulos del proveedor
(misma responsabilidad que ``eu_registry/client.py`` para sus fuentes). Deduplicar
articulos entre proveedores (S3.2), filtrar homonimos (S3.3) y registrar
procedencia completa (S3.4) es tarea del agente de noticias, no de este modulo.
"""
from __future__ import annotations

import os
import threading
import time
from typing import Any

import requests

GDELT_SEARCH_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
NEWSAPI_SEARCH_URL = "https://newsapi.org/v2/everything"

DEFAULT_TIMEOUT = 20

# CHORE-2026-11-27-01: GDELT saturado tardaba 7 s en aceptar la conexión y 12-25 s en el TLS.
# (conexión, lectura) por separado: con un solo número, ``requests`` lo aplica a cada fase y la
# espera real llegaba a sumar varias veces ese valor. Ambos caben en el plazo total de la prensa
# (``agent.TIEMPO_ESPERA_PROVEEDOR_SEG``).
GDELT_TIMEOUT = (3.0, 6.0)

# GDELT pide no más de una consulta cada 5 s por IP y responde 429 si se excede. El turno se
# lleva en todo el proceso (varios dossiers a la vez comparten la IP): una consulta antes de
# tiempo se omite sin salir a la red, en vez de esperar o provocar el 429.
GDELT_INTERVALO_SEG = 5.0
# Reemplazable en las pruebas.
_reloj = time.monotonic
_candado_turno_gdelt = threading.Lock()
_ultima_consulta_gdelt: float | None = None


class ProveedorNoticiasError(RuntimeError):
    """Error al consultar un proveedor de noticias (HTTP, timeout, formato inesperado)."""


class LimiteProveedorNoticias(ProveedorNoticiasError):
    """El proveedor rechazó la consulta por exceso de pedidos (HTTP 429)."""


def reiniciar_turno_gdelt() -> None:
    """Olvida la última consulta a GDELT (pruebas)."""
    global _ultima_consulta_gdelt
    with _candado_turno_gdelt:
        _ultima_consulta_gdelt = None


def _tomar_turno_gdelt() -> bool:
    """``True`` y ocupa el turno si pasó el intervalo desde la última consulta; si no, ``False``."""
    global _ultima_consulta_gdelt
    with _candado_turno_gdelt:
        ahora = _reloj()
        if _ultima_consulta_gdelt is not None and ahora - _ultima_consulta_gdelt < GDELT_INTERVALO_SEG:
            return False
        _ultima_consulta_gdelt = ahora
        return True


def search_gdelt_articles(query: str, *, limite: int = 10) -> list[dict[str, Any]]:
    """Busca articulos en GDELT DOC 2.0 de los ultimos 30 dias (fuente base, ADR 0004).

    Sin costo ni API key. ``query`` ya debe venir compuesta por el llamador
    (p.ej. ``'"Nombre Participante" AND "Empresa"'``, formato que exige el ADR).
    """
    q = (query or "").strip()
    if not q:
        return []

    params = {
        "query": q,
        "mode": "artlist",
        "format": "json",
        "timespan": "30d",
        "maxrecords": str(max(1, min(limite, 250))),
    }
    if not _tomar_turno_gdelt():
        raise LimiteProveedorNoticias(
            f"GDELT se omite: hubo otra consulta hace menos de {GDELT_INTERVALO_SEG:g} s"
        )
    try:
        resp = requests.get(GDELT_SEARCH_URL, params=params, timeout=GDELT_TIMEOUT)
        if resp.status_code == 429:
            # Sin reintento: esperar el intervalo y volver a pedir no cabe en el plazo de la prensa.
            raise LimiteProveedorNoticias("GDELT rechazó la consulta por exceso de pedidos (429)")
        resp.raise_for_status()
        data = resp.json()
    except ProveedorNoticiasError:
        raise
    except Exception as e:
        raise ProveedorNoticiasError(f"Error al consultar GDELT: {e}") from e

    if not isinstance(data, dict):
        raise ProveedorNoticiasError(
            "Forma de respuesta inesperada de GDELT (se esperaba un objeto)"
        )
    return list(data.get("articles") or [])


def search_newsapi_articles(query: str, *, limite: int = 10) -> list[dict[str, Any]]:
    """Busca articulos en NewsAPI.org (conector secundario configurable del ADR 0004).

    Requiere ``NEWS_API_KEY`` en el entorno; sin ella no hay suscripcion que
    consultar y se marca como error, no como lista vacia silenciosa.
    """
    q = (query or "").strip()
    if not q:
        return []

    api_key = os.getenv("NEWS_API_KEY")
    if not api_key:
        raise ProveedorNoticiasError("Falta NEWS_API_KEY para consultar NewsAPI")

    try:
        resp = requests.get(
            NEWSAPI_SEARCH_URL,
            params={"q": q, "pageSize": max(1, min(limite, 100))},  # type: ignore[arg-type]  # valores str/int validos para requests; mypy infiere dict[str, object]
            headers={"X-Api-Key": api_key},
            timeout=DEFAULT_TIMEOUT,
        )
        if resp.status_code == 429:
            # Cuota diaria o por minuto agotada: reintentar no sirve.
            raise LimiteProveedorNoticias("NewsAPI rechazó la consulta por exceso de pedidos (429)")
        resp.raise_for_status()
        data = resp.json()
    except ProveedorNoticiasError:
        raise
    except Exception as e:
        raise ProveedorNoticiasError(f"Error al consultar NewsAPI: {e}") from e

    if not isinstance(data, dict):
        raise ProveedorNoticiasError(
            "Forma de respuesta inesperada de NewsAPI (se esperaba un objeto)"
        )
    return list(data.get("articles") or [])
