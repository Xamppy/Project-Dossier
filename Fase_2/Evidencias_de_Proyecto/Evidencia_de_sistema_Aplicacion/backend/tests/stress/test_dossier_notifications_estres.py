"""S5.2 · Estrés del canal de notificaciones.

Cada pestaña abierta mantiene un stream. Con un generador síncrono, cada uno ocuparía
un hilo del pool de Starlette (40 por omisión) y con 40 pestañas el servidor dejaría
de responder. El generador es asíncrono: cientos de streams esperan a la vez sin hilos.
"""
from __future__ import annotations

import asyncio
import threading
import time

from starlette.concurrency import run_in_threadpool

from dossier.services.dossier_notifications_stream import stream_dossier_list

STREAMS = 300


def test_300_streams_a_la_vez_sin_un_hilo_por_stream():
    pico_hilos = 0
    lecturas = 0

    def huella_sync() -> str:
        nonlocal lecturas
        lecturas += 1
        time.sleep(0.001)  # una consulta corta a la base
        return "h"

    async def huella() -> str | None:
        return await run_in_threadpool(huella_sync)

    async def lista() -> dict:
        return {"organization_id": "o", "items": []}

    async def un_stream() -> int:
        frames = 0
        async for _ in stream_dossier_list(
            huella, lista, check_seconds=0.05, heartbeat_seconds=0.1, max_seconds=0.5
        ):
            frames += 1
        return frames

    async def todos() -> list[int]:
        nonlocal pico_hilos
        tarea = asyncio.gather(*(un_stream() for _ in range(STREAMS)))
        while not tarea.done():
            pico_hilos = max(pico_hilos, threading.active_count())
            await asyncio.sleep(0.02)
        return await tarea

    inicio = time.monotonic()
    frames = asyncio.run(todos())
    duracion = time.monotonic() - inicio

    assert len(frames) == STREAMS
    assert all(f >= 1 for f in frames)
    # Cada stream comparó la huella varias veces en su medio segundo de vida.
    assert lecturas >= STREAMS * 5
    # Los streams no ocupan un hilo cada uno: el pool de hilos queda acotado.
    assert pico_hilos < 80
    assert duracion < 10
