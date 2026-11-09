"""
Cookie del token de renovación (S3.9).

- ``HttpOnly``: JavaScript no puede leerla.
- ``Secure``: solo por HTTPS. Para desarrollo por HTTP en un host distinto de
  ``localhost`` se apaga con ``AUTH_REFRESH_COOKIE_SECURE=0``.
- ``SameSite=Strict`` por omisión (``AUTH_REFRESH_COOKIE_SAMESITE=lax`` como alternativa;
  ``none`` no se acepta: enviaría la cookie desde cualquier sitio).
- ``Path`` = rutas de autenticación (``/auth``, o ``/api/auth`` detrás de Caddy, que
  publica la API bajo ``/api`` y uvicorn lo conoce por ``--root-path``).
- Sesión recordada: ``Max-Age`` hasta el vencimiento. Sin recordar: cookie de sesión del
  navegador (se pierde al cerrarlo).
"""
from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import Request, Response

from dossier.security.refresh_tokens import REFRESH_COOKIE_NAME, is_persistent


def cookie_path(request: Any) -> str:
    root = str(request.scope.get("root_path") or "").rstrip("/")
    return f"{root}/auth"


def cookie_samesite() -> Literal["strict", "lax"]:
    valor = (os.getenv("AUTH_REFRESH_COOKIE_SAMESITE") or "").strip().lower()
    return "lax" if valor == "lax" else "strict"


def cookie_secure() -> bool:
    valor = (os.getenv("AUTH_REFRESH_COOKIE_SECURE") or "1").strip().lower()
    return valor not in ("0", "false", "no", "off")


def read_refresh_cookie(request: Request) -> str | None:
    return request.cookies.get(REFRESH_COOKIE_NAME) or None


def set_refresh_cookie(
    response: Response,
    request: Request,
    raw_token: str,
    expires_at: datetime,
    *,
    now: datetime | None = None,
) -> None:
    max_age: int | None = None
    if is_persistent(raw_token):
        max_age = max(0, int((expires_at - (now or datetime.now(UTC))).total_seconds()))
    response.set_cookie(
        REFRESH_COOKIE_NAME,
        raw_token,
        max_age=max_age,
        httponly=True,
        secure=cookie_secure(),
        samesite=cookie_samesite(),
        path=cookie_path(request),
    )


def clear_refresh_cookie(response: Response, request: Request) -> None:
    response.delete_cookie(
        REFRESH_COOKIE_NAME,
        httponly=True,
        secure=cookie_secure(),
        samesite=cookie_samesite(),
        path=cookie_path(request),
    )
