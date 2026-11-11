"""Worker en background que borra los dossiers vencidos y verifica el borrado (S6.5).

Cada vuelta toma el corte ``ahora − DOSSIER_RETENTION_HOURS`` y borra todo dossier creado antes,
de cualquier usuario, y los jobs de generación terminados antes del corte. Después del commit
vuelve a consultar para comprobar que no quedó nada: ni filas ni la entrada de Redis.

Cada borrado y cada verificación quedan en ``audit_logs`` (S6.6).
"""
from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import bindparam, delete, func, select, text
from sqlalchemy.orm import Session

from dossier.cache.corporate_dossier_redis import dossier_redis_key_exists
from dossier.db.connection import is_database_configured
from dossier.db.models import CalendarEvent, Dossier, DossierGenerationJob
from dossier.db.session import _factory
from dossier.services.audit_log import AuditEvent, record
from dossier.services.dossier_deletion_service import (
    delete_dossier_record,
    finalize_dossier_deletions,
)
from dossier.services.dossier_retention import dossier_retention_hours, retention_cutoff

logger = logging.getLogger(__name__)

# Mismos estados activos que ``dossier_generation_job_service._ACTIVE_STATUSES``: un job en curso
# no se borra aunque sea antiguo.
_JOBS_ACTIVOS = ("queued", "running")

# Tablas que guardan datos de un dossier. Todas tienen ON DELETE CASCADE hacia ``dossiers``.
_TABLAS_HIJAS = (
    "dossier_alerts",
    "dossier_media_mentions",
    "dossier_corporate_records",
    "dossier_career_entries",
    "dossier_ice_breakers",
    "dossier_shares",
    "dossier_access_links",  # S6.2
)


# Candado de Postgres que comparten todos los procesos: con varios workers (réplicas o procesos
# del servidor), solo uno borra por vuelta. El número es arbitrario y fijo.
_CANDADO_RETENCION = 6_005_240


@dataclass(frozen=True)
class ResultadoRetencion:
    """Lo que hizo una vuelta del worker. ``restos`` vacío significa borrado verificado.

    ``omitido`` indica que otro proceso estaba borrando y esta vuelta no hizo nada.
    """

    dossiers_borrados: int = 0
    jobs_borrados: int = 0
    restos: dict[str, int] = field(default_factory=dict)
    omitido: bool = False

    @property
    def verificado(self) -> bool:
        return not self.restos


def worker_enabled() -> bool:
    raw = os.getenv("DOSSIER_RETENTION_WORKER_ENABLED", "1").strip().lower()
    return raw in ("1", "true", "yes", "on")


def poll_interval_seconds() -> float:
    """Cada cuánto revisa. Es el atraso máximo del borrado: 10 minutos por omisión."""
    raw = os.getenv("DOSSIER_RETENTION_POLL_SECONDS", "600").strip()
    try:
        return max(60.0, float(raw))
    except ValueError:
        return 600.0


def _contar_por_dossier(db: Session, tabla: str, columna: str, ids: list[UUID]) -> int:
    consulta = text(f"SELECT count(*) FROM {tabla} WHERE {columna} IN :ids").bindparams(
        bindparam("ids", expanding=True)
    )
    return int(db.execute(consulta, {"ids": ids}).scalar_one())


def verificar_borrado(
    db: Session,
    *,
    dossier_ids: Iterable[UUID],
    cache_keys: Iterable[str],
    corte: datetime,
) -> dict[str, int]:
    """Cuenta lo que debería haber desaparecido. Devuelve solo lo que quedó, por tabla.

    Nunca registra datos de la persona consultada: solo nombres de tabla y cantidades.
    """
    ids = list(dossier_ids)
    restos: dict[str, int] = {}
    if ids:
        for tabla, columna in (("dossiers", "id"), *((t, "dossier_id") for t in _TABLAS_HIJAS)):
            quedan = _contar_por_dossier(db, tabla, columna, ids)
            if quedan:
                restos[tabla] = quedan
    jobs = db.execute(
        select(func.count())
        .select_from(DossierGenerationJob)
        .where(
            DossierGenerationJob.status.not_in(_JOBS_ACTIVOS),
            func.coalesce(DossierGenerationJob.completed_at, DossierGenerationJob.created_at) < corte,
        )
    ).scalar_one()
    if jobs:
        restos["dossier_generation_jobs"] = int(jobs)
    en_cache = sum(1 for clave in cache_keys if dossier_redis_key_exists(clave))
    if en_cache:
        restos["redis"] = en_cache
    if restos:
        logger.error("Retención: el borrado NO quedó verificado; quedan %s", restos)
    return restos


def _evento_retencion(
    action: str, resource_id: UUID | None, organization_id: UUID | None, datos: dict[str, Any]
) -> AuditEvent:
    """Registro de auditoría de la retención (S6.6): lo hace el servidor, no una persona."""
    return AuditEvent(
        action=action,
        resource_type="dossier" if resource_id else "dossier_generation_job",
        resource_id=resource_id,
        organization_id=organization_id,
        user_role="sistema",
        request_data=datos,
    )


def _auditar_verificacion(db: Session, resultado: ResultadoRetencion, horas: int) -> None:
    """Deja el resultado de la verificación en ``audit_logs``. Un fallo aquí solo queda en el log."""
    try:
        record(
            db,
            AuditEvent(
                action="RETENTION verification",
                user_role="sistema",
                success=resultado.verificado,
                error_message=None if resultado.verificado else "borrado no verificado",
                request_data={
                    "retention_hours": horas,
                    "dossiers": resultado.dossiers_borrados,
                    "jobs": resultado.jobs_borrados,
                    "restos": resultado.restos,
                },
            ),
        )
        db.commit()
    except Exception:
        logger.exception("Retención: no se pudo auditar la verificación")
        db.rollback()


def purge_expired_dossiers(db: Session, *, now: datetime | None = None) -> ResultadoRetencion:
    """Borra dossiers y jobs vencidos, hace commit y verifica que no quede nada."""
    # El candado dura hasta el commit de esta transacción; si otro proceso lo tiene, se omite.
    if not db.execute(text("SELECT pg_try_advisory_xact_lock(:k)"), {"k": _CANDADO_RETENCION}).scalar():
        db.rollback()
        logger.debug("Retención: otro proceso está borrando; se omite esta vuelta")
        return ResultadoRetencion(omitido=True)

    corte = retention_cutoff(now)
    horas = dossier_retention_hours()
    # S6.3: un dossier de una reunión vence 24 h después de lo más tardío entre su creación y el
    # inicio de la reunión; sin reunión, 24 h después de crearse.
    desde = func.greatest(Dossier.created_at, func.coalesce(CalendarEvent.starts_at, Dossier.created_at))
    vencidos = db.execute(
        select(Dossier)
        .outerjoin(CalendarEvent, Dossier.calendar_event_id == CalendarEvent.id)
        .where(desde < corte)
    ).scalars().all()

    dossier_ids = [d.id for d in vencidos]
    cache_keys = [(d.cache_key or "").strip() for d in vencidos if (d.cache_key or "").strip()]
    calendar_event_ids: set[UUID | None] = set()
    for dossier in vencidos:
        # S6.6: el registro va en la misma transacción que el borrado; sin registro no hay borrado.
        record(db, _evento_retencion("RETENTION dossier_deleted", dossier.id, dossier.organization_id,
                                     {"retention_hours": horas}))
        calendar_event_ids.add(delete_dossier_record(db, dossier))
    if vencidos:
        db.flush()
        finalize_dossier_deletions(db, calendar_event_ids)

    jobs = db.execute(
        delete(DossierGenerationJob)
        .where(
            DossierGenerationJob.status.not_in(_JOBS_ACTIVOS),
            func.coalesce(DossierGenerationJob.completed_at, DossierGenerationJob.created_at) < corte,
        )
        .execution_options(synchronize_session=False)
    )
    jobs_borrados = int(jobs.rowcount or 0)  # type: ignore[attr-defined]
    if jobs_borrados:
        record(db, _evento_retencion("RETENTION jobs_deleted", None, None,
                                     {"retention_hours": horas, "jobs": jobs_borrados}))

    db.commit()
    restos = verificar_borrado(db, dossier_ids=dossier_ids, cache_keys=cache_keys, corte=corte)
    resultado = ResultadoRetencion(
        dossiers_borrados=len(dossier_ids), jobs_borrados=jobs_borrados, restos=restos
    )
    if resultado.dossiers_borrados or resultado.jobs_borrados or restos:
        _auditar_verificacion(db, resultado, horas)
    if resultado.verificado and (resultado.dossiers_borrados or resultado.jobs_borrados):
        logger.info(
            "Retención (%s h): %s dossier(s) y %s job(s) borrados; borrado verificado",
            dossier_retention_hours(),
            resultado.dossiers_borrados,
            resultado.jobs_borrados,
        )
    return resultado


def _worker_loop(stop: threading.Event) -> None:
    interval = poll_interval_seconds()
    logger.info(
        "Worker retención dossiers: iniciado (plazo=%sh, intervalo=%ss, enabled=%s)",
        dossier_retention_hours(),
        interval,
        worker_enabled(),
    )
    while not stop.wait(interval):
        if not worker_enabled() or not is_database_configured():
            continue
        db = _factory()()
        try:
            purge_expired_dossiers(db)
        except Exception:
            logger.exception("Error en worker de retención de dossiers")
            db.rollback()
        finally:
            db.close()


def start_dossier_retention_worker() -> Callable[[], None]:
    stop = threading.Event()
    if not worker_enabled():
        logger.info(
            "Worker retención dossiers desactivado (DOSSIER_RETENTION_WORKER_ENABLED=0)"
        )
        return stop.set
    if not is_database_configured():
        logger.info("Worker retención dossiers omitido: PostgreSQL no configurado")
        return stop.set

    thread = threading.Thread(
        target=_worker_loop,
        args=(stop,),
        name="dossier-retention-worker",
        daemon=True,
    )
    thread.start()

    def shutdown() -> None:
        stop.set()
        thread.join(timeout=8)

    return shutdown
