"""Telemetría del grafo corporativo para la fila ``dossiers`` (S2.4, S2.5).

Las dos rutas que guardan un dossier corporativo (calendario y generación manual)
escribían listas fijas en ``agents_activated`` y ``data_sources_used``. Este módulo
las arma con lo que el grafo realmente ejecutó y consultó.
"""
from __future__ import annotations

from typing import Any


def telemetria_de(generado: Any) -> dict[str, Any]:
    """Resumen serializable a JSON de un ``CorporateDossierResult``.

    Va dentro del resultado del job (JSONB), así que no lleva objetos Pydantic. Usa
    ``getattr`` porque hay dobles de prueba con solo parte de los campos.
    """
    return {
        "agents_failed": list(getattr(generado, "agents_failed", None) or []),
        "agents_succeeded": list(getattr(generado, "agents_succeeded", None) or []),
        "agents_skipped": list(getattr(generado, "agents_skipped", None) or []),
        "fuentes_consultadas": list(getattr(generado, "fuentes_consultadas", None) or []),
        "menciones_prensa": [
            m.model_dump(mode="json") for m in (getattr(generado, "menciones_prensa", None) or [])
        ],
    }


def columnas_telemetria(telemetria: dict[str, Any] | None, *, es_error: bool) -> dict[str, Any]:
    """Columnas de agentes y fuentes de la fila ``dossiers``, más lo que va a ``dossier_data``.

    Sin telemetría (el Markdown vino de la caché, no se ejecutó el grafo en esta
    llamada) no se inventan fuentes: las listas quedan vacías y ``agents_failed`` cae al
    criterio anterior (¿el Markdown final es un error?).
    """
    if telemetria is None:
        return {
            "agents_activated": [],
            "agents_failed": ["synthesize_llm"] if es_error else [],
            "data_sources_used": [],
            "dossier_data": {},
        }
    fallidos = list(telemetria.get("agents_failed") or [])
    exitosos = list(telemetria.get("agents_succeeded") or [])
    fuentes = list(telemetria.get("fuentes_consultadas") or [])
    return {
        "agents_activated": list(dict.fromkeys(exitosos + fallidos)),
        "agents_failed": fallidos,
        # Solo lo que respondió; lo caído queda en fuentes_consultadas con resultado "error".
        "data_sources_used": list(dict.fromkeys(f["fuente"] for f in fuentes if f.get("resultado") != "error")),
        "dossier_data": {
            "fuentes_consultadas": fuentes,
            "agents_skipped": list(telemetria.get("agents_skipped") or []),
        },
    }
