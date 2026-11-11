"""Worker en background que procesa la cola de generación de dossiers."""
from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Callable

from dossier.db.connection import is_database_configured
from dossier.db.session import _factory
from dossier.services.dossier_generation_job_service import (
    claim_next_queued_job,
    process_dossier_generation_job,
)
from dossier.services.dossier_job_recovery import recover_stale_jobs

logger = logging.getLogger(__name__)


def worker_enabled() -> bool:
    raw = os.getenv("DOSSIER_GENERATION_WORKER_ENABLED", "1").strip().lower()
    return raw in ("1", "true", "yes", "on")


def poll_interval_seconds() -> float:
    raw = os.getenv("DOSSIER_GENERATION_POLL_SECONDS", "2").strip()
    try:
        return max(0.5, float(raw))
    except ValueError:
        return 2.0


def recovery_interval_seconds() -> float:
    """Cada cuánto se buscan trabajos colgados (``DOSSIER_JOB_RECOVERY_SECONDS``)."""
    raw = os.getenv("DOSSIER_JOB_RECOVERY_SECONDS", "60").strip()
    try:
        return max(10.0, float(raw))
    except ValueError:
        return 60.0


def recovery_due(ultimo: float | None, ahora: float, cada: float) -> bool:
    """Toca barrer: nunca se hizo (arranque del proceso) o pasó el intervalo."""
    return ultimo is None or ahora - ultimo >= cada


def _barrer_colgados() -> None:
    db = _factory()()
    try:
        recover_stale_jobs(db)
    except Exception:
        logger.exception("Error al recuperar trabajos de generación colgados")
        db.rollback()
    finally:
        db.close()


def _worker_loop(stop: threading.Event) -> None:
    interval = poll_interval_seconds()
    ultimo_barrido: float | None = None
    logger.info(
        "Worker generación dossiers: iniciado (intervalo=%ss, enabled=%s)",
        interval,
        worker_enabled(),
    )
    while not stop.wait(interval):
        if not worker_enabled() or not is_database_configured():
            continue
        # Al arrancar y luego cada minuto: lo que quedó «en curso» tras una caída pasa a fallido.
        if recovery_due(ultimo_barrido, time.monotonic(), recovery_interval_seconds()):
            _barrer_colgados()
            ultimo_barrido = time.monotonic()
        db = _factory()()
        try:
            while True:
                job = claim_next_queued_job(db)
                if job is None:
                    break
                process_dossier_generation_job(db, job.id)
        except Exception:
            logger.exception("Error en worker de generación de dossiers")
        finally:
            db.close()


def start_dossier_generation_worker() -> Callable[[], None]:
    stop = threading.Event()
    if not worker_enabled():
        logger.info("Worker generación dossiers desactivado (DOSSIER_GENERATION_WORKER_ENABLED=0)")
        return stop.set
    if not is_database_configured():
        logger.info("Worker generación dossiers omitido: PostgreSQL no configurado")
        return stop.set

    thread = threading.Thread(
        target=_worker_loop,
        args=(stop,),
        name="dossier-generation-worker",
        daemon=True,
    )
    thread.start()

    def shutdown() -> None:
        stop.set()
        thread.join(timeout=8)

    return shutdown
