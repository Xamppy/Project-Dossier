"""Canal SSE de la lista de dossiers para las notificaciones del dashboard (S5.2).

Ver specs/proposals/S5.2-S5.3-notificaciones-canal.md. Sustituye el sondeo de
``NotificationsProvider`` (``GET /dossiers`` cada 15 s por pestaña): el cliente abre
un solo stream y recibe la lista solo cuando cambia.

El generador es asíncrono a propósito: entre comprobaciones espera con
``asyncio.sleep`` y no retiene un hilo del servidor. Cada lectura de la base la hace
quien lo llama (en el pool de hilos, cerrando su transacción enseguida).

Separado de FastAPI y de la base: recibe dos lectores asíncronos, así que se prueba
entero sin servidor ni Postgres.
"""
from __future__ import annotations

import asyncio
import os
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from dossier.services.dossier_progress_stream import sse_frame

EVENTO = "dossiers"
# Mismo tamaño que pedía el sondeo de la campana (`fetchDossiersFromApi(25)`).
LIMITE_LISTA = 25

DEFAULT_CHECK_SECONDS = 5.0
MIN_CHECK_SECONDS = 1.0
DEFAULT_HEARTBEAT_SECONDS = 15.0
DEFAULT_MAX_SECONDS = 600.0  # corte de seguridad; el cliente reconecta (S5.3)


def _float_env(nombre: str, por_omision: float) -> float:
    try:
        return float(os.getenv(nombre, "").strip() or por_omision)
    except ValueError:
        return por_omision


def check_seconds() -> float:
    """Cada cuánto se compara la huella de la lista (``DOSSIER_NOTIFICATIONS_CHECK_SECONDS``)."""
    return max(MIN_CHECK_SECONDS, _float_env("DOSSIER_NOTIFICATIONS_CHECK_SECONDS", DEFAULT_CHECK_SECONDS))


def max_seconds() -> float:
    """Duración máxima de un stream (``DOSSIER_NOTIFICATIONS_MAX_SECONDS``)."""
    return max(0.0, _float_env("DOSSIER_NOTIFICATIONS_MAX_SECONDS", DEFAULT_MAX_SECONDS))


LectorHuella = Callable[[], Awaitable[str | None]]
LectorLista = Callable[[], Awaitable[dict[str, Any] | None]]


async def stream_dossier_list(
    leer_huella: LectorHuella,
    leer_lista: LectorLista,
    *,
    check_seconds: float = DEFAULT_CHECK_SECONDS,
    heartbeat_seconds: float = DEFAULT_HEARTBEAT_SECONDS,
    max_seconds: float = DEFAULT_MAX_SECONDS,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> AsyncIterator[str]:
    """Genera frames SSE: la lista al conectar y otra cada vez que cambia su huella.

    ``leer_huella`` devuelve un texto barato de calcular que cambia cuando cambia la
    lista, o ``None`` si el usuario ya no puede verla (sesión, membresía): entonces
    el stream termina. ``leer_lista`` devuelve el mismo cuerpo que ``GET /dossiers``.
    Sin cambios, ``: ping`` tras ``heartbeat_seconds``.
    """
    inicio = clock()
    huella = await leer_huella()
    if huella is None:
        return
    lista = await leer_lista()
    if lista is None:
        return
    seq = 1
    yield sse_frame(EVENTO, lista, seq)
    ultimo_envio = clock()

    while clock() - inicio < max_seconds:
        await sleep(check_seconds)
        nueva = await leer_huella()
        if nueva is None:
            return
        if nueva != huella:
            lista = await leer_lista()
            if lista is None:
                return
            huella = nueva
            seq += 1
            yield sse_frame(EVENTO, lista, seq)
            ultimo_envio = clock()
        elif clock() - ultimo_envio >= heartbeat_seconds:
            yield ": ping\n\n"
            ultimo_envio = clock()
