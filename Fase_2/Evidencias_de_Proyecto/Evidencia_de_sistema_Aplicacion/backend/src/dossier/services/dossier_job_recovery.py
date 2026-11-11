"""Recuperación de trabajos de generación colgados.

Si el proceso se cae a mitad de una generación (despliegue, reinicio, falta de memoria), el
trabajo quedaba ``running`` para siempre: el aviso del dashboard no terminaba y el usuario podía
quedar sin cupo (UX-ADMIN-01). Mientras genera, el proceso actualiza ``heartbeat_at`` cada
``DOSSIER_JOB_HEARTBEAT_SECONDS``. Este barrido marca como ``failed`` los trabajos en curso sin
latido en ``DOSSIER_JOB_STALE_SECONDS`` (180 por omisión). Sin latido (trabajos anteriores a la
columna) se usa la hora de inicio.

No hay créditos que devolver: se descuentan al guardar el dossier, y un trabajo cortado no
llegó a guardarlo.
"""
from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta
from typing import Final
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from dossier.db.models import DossierGenerationJob

logger = logging.getLogger(__name__)

INTERRUPTED_MESSAGE: Final = "La generación se interrumpió porque el servidor se reinició. Vuelve a intentarlo."
DEFAULT_STALE_SECONDS: Final = 180
MIN_STALE_SECONDS: Final = 60
# Un barrido a la vez entre procesos (mismo patrón que la retención, S6.5).
_LOCK_ID: Final = 6005241


def stale_after_seconds() -> int:
    try:
        valor = int((os.getenv("DOSSIER_JOB_STALE_SECONDS") or "").strip() or DEFAULT_STALE_SECONDS)
    except ValueError:
        return DEFAULT_STALE_SECONDS
    return max(MIN_STALE_SECONDS, valor)


def recover_stale_jobs(db: Session) -> list[UUID]:
    """Marca como fallidos los trabajos en curso sin latido reciente y devuelve sus ids."""
    from dossier.services.dossier_generation_job_service import (
        _auditar_job,
        _final_payload,
        _publicar_estado,
    )

    if not db.execute(select(func.pg_try_advisory_xact_lock(_LOCK_ID))).scalar():
        db.rollback()
        return []
    limite = func.now() - timedelta(seconds=stale_after_seconds())
    ultima_senal = func.coalesce(
        DossierGenerationJob.heartbeat_at, DossierGenerationJob.started_at, DossierGenerationJob.created_at
    )
    jobs = list(
        db.scalars(
            select(DossierGenerationJob)
            .where(DossierGenerationJob.status == "running", ultima_senal < limite)
            .with_for_update(skip_locked=True)
        ).all()
    )
    if not jobs:
        db.rollback()
        return []
    ahora = datetime.now(UTC)
    for job in jobs:
        job.status = "failed"
        job.error_message = INTERRUPTED_MESSAGE
        job.completed_at = ahora
        job.result_payload = _final_payload(None, job)
    db.commit()
    ids = [job.id for job in jobs]
    for job in jobs:
        _publicar_estado(job)
        _auditar_job(db, job.id)
    logger.warning("Trabajos de generación colgados marcados como fallidos: %s", [str(i) for i in ids])
    return ids
