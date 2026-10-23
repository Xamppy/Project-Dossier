"""
Política CORS del API (S3.8).

Reglas:
- Métodos y cabeceras en lista explícita, nunca ``*``.
- Sin credenciales entre sitios: el dashboard autentica con ``Authorization: Bearer``,
  no con cookies, así que ``allow_credentials`` queda en ``False``.
- Los subdominios ``*.vercel.app`` solo se aceptan si se activa
  ``CORS_ALLOW_VERCEL_APP_REGEX`` de forma explícita.

``build_cors_settings`` recibe las variables de entorno como diccionario para poder
probarla sin recargar la aplicación.
"""
from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

ALLOWED_METHODS: tuple[str, ...] = ("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")

# Las que envía el dashboard: JWT, JSON y la reanudación del canal SSE.
ALLOWED_HEADERS: tuple[str, ...] = (
    "Authorization",
    "Content-Type",
    "Accept",
    "Accept-Language",
    "Last-Event-ID",
)

# Solo host *.vercel.app con HTTPS (el header Origin nunca incluye path).
DEFAULT_VERCEL_ORIGIN_REGEX = r"https://[a-z0-9-]+\.vercel\.app"

_VALORES_ACTIVOS = ("1", "true", "yes", "on")

# Comillas "curvas" típicas al copiar desde Word o Slack.
_COMILLAS_TIPOGRAFICAS: dict[str, str | int | None] = {
    "“": '"',
    "”": '"',
    "‘": "'",
    "’": "'",
}


def parse_cors_origins(raw: str) -> list[str]:
    """
    Normaliza CORS_ORIGINS: quita BOM/espacios, comillas (ASCII/tipográficas) y barra final.
    El navegador envía Origin sin barra final; si en el panel quedó una, no coincidía.
    """
    t = raw.strip().strip("﻿").translate(str.maketrans(_COMILLAS_TIPOGRAFICAS))
    out: list[str] = []
    for part in t.split(","):
        o = part.strip().strip('"').strip("'").rstrip("/")
        if o:
            out.append(o)
    return out


def default_cors_origins_csv() -> str:
    """Puertos 3000–3009 en localhost / 127.0.0.1 / ::1 (Next salta de puerto si 3000 está ocupado)."""
    parts: list[str] = []
    for port in range(3000, 3010):
        parts.extend(
            [
                f"http://localhost:{port}",
                f"http://127.0.0.1:{port}",
                f"http://[::1]:{port}",
            ]
        )
    return ",".join(parts)


@dataclass(frozen=True)
class CorsSettings:
    origins: list[str]
    origin_regex: str | None

    def middleware_kwargs(self) -> dict[str, Any]:
        """Argumentos para ``app.add_middleware(CORSMiddleware, **kwargs)``."""
        return {
            "allow_origins": list(self.origins),
            "allow_origin_regex": self.origin_regex,
            "allow_credentials": False,
            "allow_methods": list(ALLOWED_METHODS),
            "allow_headers": list(ALLOWED_HEADERS),
        }


def _vercel_origin_regex(env: Mapping[str, str]) -> str | None:
    if env.get("CORS_ALLOW_VERCEL_APP_REGEX", "0").strip().lower() not in _VALORES_ACTIVOS:
        return None
    custom = (env.get("CORS_VERCEL_ORIGIN_REGEX") or "").strip()
    if not custom:
        return DEFAULT_VERCEL_ORIGIN_REGEX
    try:
        re.compile(custom)
    except re.error:
        logger.warning("CORS_VERCEL_ORIGIN_REGEX inválida; se usa el patrón por defecto.")
        return DEFAULT_VERCEL_ORIGIN_REGEX
    return custom


def build_cors_settings(env: Mapping[str, str]) -> CorsSettings:
    """Arma la política CORS a partir de las variables de entorno."""
    raw = env.get("CORS_ORIGINS")
    origins = parse_cors_origins(default_cors_origins_csv() if raw is None else raw)
    return CorsSettings(origins=origins, origin_regex=_vercel_origin_regex(env))
