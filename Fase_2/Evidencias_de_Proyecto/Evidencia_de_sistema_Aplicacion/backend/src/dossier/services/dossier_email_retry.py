"""Reintento de los envíos automáticos de correo (S6.4).

Decisión de FD (2026-11-10): **3 intentos seguidos** (esperas de 2 s y 5 s) y, si siguen
fallando por algo pasajero, **uno cada 10 minutos hasta 1 hora** (6 reintentos). Un fallo
definitivo (5xx, credenciales) no se reintenta.

Los envíos en espera viven en ``dossier_email_retries``, sin la dirección del destinatario: al
reintentar se lee de ``users.email``. Un proceso de fondo los toma de a uno con
``FOR UPDATE SKIP LOCKED``, así dos procesos nunca reintentan el mismo envío.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from dossier.db.connection import is_database_configured
from dossier.db.models import Dossier, DossierEmailRetry, User
from dossier.db.session import _factory
from dossier.services.dossier_access_links import url_de_acceso_o_nada
from dossier.services.email_service import EmailDeliveryError

logger = logging.getLogger(__name__)

INTENTOS_SEGUIDOS = 3
ESPERAS_SEGUNDOS = (2.0, 5.0)
REINTENTO_CADA = timedelta(minutes=10)
REINTENTOS_MAXIMOS = 6

# Las pruebas lo reemplazan para no esperar de verdad.
_dormir: Callable[[float], None] = time.sleep


@dataclass(frozen=True)
class ResultadoIntentos:
    intentos: int
    error: Exception | None = None


def _es_transitorio(exc: BaseException | None) -> bool:
    return isinstance(exc, EmailDeliveryError) and exc.transitorio


def enviar_con_reintentos(
    enviar: Callable[[], None], *, dormir: Callable[[float], None] | None = None
) -> ResultadoIntentos:
    """Llama a ``enviar`` hasta 3 veces mientras falle por algo pasajero. Nunca lanza."""
    espera = dormir or _dormir
    for intento in range(1, INTENTOS_SEGUIDOS + 1):
        try:
            enviar()
            return ResultadoIntentos(intentos=intento)
        except Exception as exc:  # noqa: BLE001 - el resultado lleva el error a quien llama
            if not _es_transitorio(exc) or intento == INTENTOS_SEGUIDOS:
                return ResultadoIntentos(intentos=intento, error=exc)
            espera(ESPERAS_SEGUNDOS[intento - 1])
    raise AssertionError("inalcanzable")  # pragma: no cover


def encolar_reintento(
    db: Session,
    *,
    kind: str,
    dossiers: Sequence[Dossier],
    error: BaseException | None,
    calendar_event_id: UUID | None = None,
    meeting_title: str | None = None,
    language: str | None = None,
    now: datetime | None = None,
) -> DossierEmailRetry:
    """Deja el envío en espera para dentro de 10 minutos. No hace commit."""
    primero = dossiers[0]
    fila = DossierEmailRetry(
        organization_id=primero.organization_id,
        user_id=primero.requested_by_user_id,
        kind=kind,
        dossier_ids=[d.id for d in dossiers],
        calendar_event_id=calendar_event_id,
        meeting_title=(meeting_title or None) and meeting_title[:500],
        language=language,
        attempts=0,
        next_attempt_at=(now or datetime.now(UTC)) + REINTENTO_CADA,
        last_error=type(error).__name__[:100] if error is not None else None,
    )
    db.add(fila)
    db.flush()
    return fila


def _datos(fila: DossierEmailRetry, reintento: int, agotado: bool) -> dict[str, Any]:
    return {
        "origen": "calendario" if fila.kind == "reunion" else "persona",
        "calendar_event_id": str(fila.calendar_event_id) if fila.calendar_event_id else None,
        "reintento": reintento,
        "agotado": agotado,
    }


def _procesar_fila(db: Session, fila: DossierEmailRetry, now: datetime) -> str:
    """Un reintento de un envío en espera. Hace commit. Devuelve qué pasó."""
    from dossier.services import dossier_email as correo_mod

    usuario = db.get(User, fila.user_id)
    encontrados = {
        d.id: d
        for d in db.scalars(
            select(Dossier).where(
                Dossier.id.in_(list(fila.dossier_ids or [])),
                Dossier.organization_id == fila.organization_id,
                Dossier.requested_by_user_id == fila.user_id,
                Dossier.status == "complete",
            )
        )
    }
    dossiers = [encontrados[i] for i in fila.dossier_ids or [] if i in encontrados]
    destino = (usuario.email or "").strip() if usuario else ""
    if not dossiers or not destino:
        db.delete(fila)
        db.commit()
        return "descartados"

    reintento = (fila.attempts or 0) + 1

    def _enviar() -> None:
        if fila.kind == "reunion":
            correo = correo_mod.build_meeting_email(
                dossiers, meeting_title=fila.meeting_title, language=fila.language,
                access_for=correo_mod._enlaces_de(db),
            )
        else:
            d = dossiers[0]
            correo = correo_mod.build_dossier_email(
                d, language=fila.language, dossier_url=correo_mod.dossier_detail_url(d.id),
                access_url=url_de_acceso_o_nada(db, d, user_id=fila.user_id),
            )
        correo_mod.send_email(
            to=[destino],
            subject=correo.subject,
            text=correo.text,
            html=correo.html,
            attachments=list(correo.attachments),
        )

    try:
        # Savepoint (S6.2): si el envío falla, los enlaces de acceso creados se descartan.
        with db.begin_nested():
            _enviar()
    except Exception as exc:  # noqa: BLE001 - un fallo se reprograma o se da por perdido
        agotado = not _es_transitorio(exc) or reintento >= REINTENTOS_MAXIMOS
        for d in dossiers:
            correo_mod.auditar_envio(
                db, correo_mod.evento_envio(d, manual=False, error=exc, datos=_datos(fila, reintento, agotado))
            )
        if agotado:
            db.delete(fila)
            logger.warning("Correo en espera %s perdido tras %s reintento(s)", fila.id, reintento)
        else:
            fila.attempts = reintento
            fila.last_error = type(exc).__name__[:100]
            fila.next_attempt_at = now + REINTENTO_CADA
        db.commit()
        return "agotados" if agotado else "reprogramados"

    for d in dossiers:
        correo_mod.marcar_enviado(d, destino)
        correo_mod.auditar_envio(db, correo_mod.evento_envio(d, manual=False, datos=_datos(fila, reintento, False)))
    db.delete(fila)
    db.commit()
    return "enviados"


def procesar_reintentos(db: Session, *, now: datetime | None = None, limite: int = 20) -> dict[str, int]:
    """Reintenta los envíos en espera ya vencidos, de a uno por transacción."""
    ahora = now or datetime.now(UTC)
    resumen = {"enviados": 0, "reprogramados": 0, "agotados": 0, "descartados": 0}
    for _ in range(limite):
        fila = db.scalars(
            select(DossierEmailRetry)
            .where(DossierEmailRetry.next_attempt_at <= ahora)
            .order_by(DossierEmailRetry.next_attempt_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        ).first()
        if fila is None:
            db.rollback()
            break
        resumen[_procesar_fila(db, fila, ahora)] += 1
    return resumen


def worker_enabled() -> bool:
    raw = os.getenv("DOSSIER_EMAIL_RETRY_WORKER_ENABLED", "1").strip().lower()
    return raw in ("1", "true", "yes", "on")


def poll_interval_seconds() -> float:
    raw = os.getenv("DOSSIER_EMAIL_RETRY_POLL_SECONDS", "60").strip()
    try:
        return max(10.0, float(raw))
    except ValueError:
        return 60.0


def _worker_loop(stop: threading.Event) -> None:
    logger.info("Worker reintentos de correo: iniciado (intervalo=%ss)", poll_interval_seconds())
    while not stop.wait(poll_interval_seconds()):
        if not worker_enabled() or not is_database_configured():
            continue
        db = _factory()()
        try:
            procesar_reintentos(db)
        except Exception:
            logger.exception("Error en worker de reintentos de correo")
            db.rollback()
        finally:
            db.close()


def start_dossier_email_retry_worker() -> Callable[[], None]:
    stop = threading.Event()
    if not worker_enabled():
        logger.info("Worker reintentos de correo desactivado (DOSSIER_EMAIL_RETRY_WORKER_ENABLED=0)")
        return stop.set
    if not is_database_configured():
        logger.info("Worker reintentos de correo omitido: PostgreSQL no configurado")
        return stop.set

    thread = threading.Thread(target=_worker_loop, args=(stop,), name="dossier-email-retry-worker", daemon=True)
    thread.start()

    def shutdown() -> None:
        stop.set()
        thread.join(timeout=8)

    return shutdown
