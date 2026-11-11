"""Recuperación de trabajos de generación colgados (Postgres).

Si el servidor se cae a mitad de una generación, el trabajo quedaba ``running`` para siempre:
el aviso no terminaba y, con el tope de dossiers a la vez (UX-ADMIN-01), el usuario podía
quedar bloqueado. Ahora el proceso que genera deja un latido (``heartbeat_at``) y un barrido
marca como ``failed`` los trabajos sin latido reciente. Requiere ``TEST_DATABASE_URL``.
"""
from __future__ import annotations

import threading
import time
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from alembic import command
from dossier.db.models import DossierGenerationJob
from dossier.services import dossier_generation_job_service as servicio
from dossier.services import dossier_progress_events as bus
from dossier.services.dossier_job_recovery import (
    INTERRUPTED_MESSAGE,
    recover_stale_jobs,
    stale_after_seconds,
)


@pytest.fixture
def base(pg_vacia, alembic_cfg, monkeypatch):
    monkeypatch.setenv("DOSSIER_CHARGE_CREDITS", "false")
    command.upgrade(alembic_cfg, "head")
    with pg_vacia.begin() as c:
        org_id = c.execute(
            text(
                "INSERT INTO organizations (name, slug, plan, credits_balance) "
                "VALUES ('Org', 'org-colgados', 'free', 100) RETURNING id"
            )
        ).scalar_one()
        user_id = c.execute(text("INSERT INTO users (email) VALUES ('u@colgados.com') RETURNING id")).scalar_one()
        c.execute(
            text(
                "INSERT INTO org_memberships (organization_id, user_id, role, is_primary_org) "
                "VALUES (:o, :u, 'user', true)"
            ),
            {"o": org_id, "u": user_id},
        )
    m = SimpleNamespace(engine=pg_vacia, org_id=org_id, user_id=user_id, jobs=[])
    yield m
    for job_id in m.jobs:
        bus.forget(job_id)


def trabajo(base, *, status="running", hace_inicio=None, hace_latido=None, job_type="person_manual") -> uuid.UUID:
    ahora = datetime.now(UTC)
    with Session(base.engine) as db:
        job = DossierGenerationJob(
            organization_id=base.org_id,
            requested_by_user_id=base.user_id,
            status=status,
            job_type=job_type,
            external_event_id=f"person:{uuid.uuid4().hex}",
            reunion_snapshot={"person_request": {"full_name": "Ana Prueba", "max_profiles": 1}},
            depth_level="basic",
            meeting_label="Ana Prueba",
            started_at=ahora - timedelta(seconds=hace_inicio) if hace_inicio is not None else None,
            heartbeat_at=ahora - timedelta(seconds=hace_latido) if hace_latido is not None else None,
        )
        db.add(job)
        db.commit()
        base.jobs.append(job.id)
        return job.id


def leer(base, job_id) -> DossierGenerationJob:
    with Session(base.engine) as db:
        job = db.get(DossierGenerationJob, job_id)
        db.expunge(job)
        return job


def barrer(base) -> list[uuid.UUID]:
    with Session(base.engine) as db:
        return recover_stale_jobs(db)


# --- Qué se considera colgado ---------------------------------------------------


def test_un_trabajo_sin_latido_reciente_pasa_a_fallido(base):
    job_id = trabajo(base, hace_inicio=900, hace_latido=600)
    assert barrer(base) == [job_id]
    job = leer(base, job_id)
    assert job.status == "failed"
    assert job.error_message == INTERRUPTED_MESSAGE
    assert job.completed_at is not None


def test_un_trabajo_con_latido_reciente_no_se_toca_aunque_lleve_mucho(base):
    job_id = trabajo(base, hace_inicio=3600, hace_latido=20)
    assert barrer(base) == []
    assert leer(base, job_id).status == "running"


def test_sin_latido_se_usa_la_hora_de_inicio(base):
    viejo = trabajo(base, hace_inicio=900)
    reciente = trabajo(base, hace_inicio=30)
    assert barrer(base) == [viejo]
    assert leer(base, reciente).status == "running"


@pytest.mark.parametrize("estado", ["queued", "completed", "failed", "cancelled"])
def test_solo_se_recuperan_los_que_estan_en_curso(base, estado):
    job_id = trabajo(base, status=estado, hace_inicio=9000, hace_latido=9000)
    assert barrer(base) == []
    assert leer(base, job_id).status == estado


def test_el_umbral_es_configurable_con_minimo(monkeypatch):
    monkeypatch.delenv("DOSSIER_JOB_STALE_SECONDS", raising=False)
    assert stale_after_seconds() == 180
    monkeypatch.setenv("DOSSIER_JOB_STALE_SECONDS", "600")
    assert stale_after_seconds() == 600
    monkeypatch.setenv("DOSSIER_JOB_STALE_SECONDS", "5")
    assert stale_after_seconds() == 60
    monkeypatch.setenv("DOSSIER_JOB_STALE_SECONDS", "x")
    assert stale_after_seconds() == 180


# --- Efectos de la recuperación ---------------------------------------------------


def test_el_canal_en_vivo_recibe_el_estado_fallido(base):
    job_id = trabajo(base, hace_inicio=900, hace_latido=900)
    barrer(base)
    evento = bus.latest_event(job_id)
    assert evento is not None
    assert evento[1] == "job_failed"
    assert evento[2]["error_message"] == INTERRUPTED_MESSAGE


def test_queda_en_la_auditoria(base):
    job_id = trabajo(base, hace_inicio=900, hace_latido=900)
    barrer(base)
    with base.engine.connect() as c:
        fila = c.execute(
            text("SELECT action, success, error_message FROM audit_logs WHERE resource_id = :i"), {"i": job_id}
        ).one()
    assert fila.action == "JOB person_manual"
    assert fila.success is False
    assert fila.error_message == INTERRUPTED_MESSAGE


def test_el_usuario_recupera_su_cupo(base):
    """Con el plan Free (1 a la vez), un trabajo colgado de hace 10 minutos lo bloqueaba."""
    from dossier.db.models import Organization, User
    from dossier.services.plan_limits import active_dossier_jobs

    trabajo(base, hace_inicio=600, hace_latido=600)
    with Session(base.engine) as db:
        assert active_dossier_jobs(db, user_id=base.user_id, organization_id=base.org_id) == 1
    barrer(base)
    with Session(base.engine) as db:
        assert active_dossier_jobs(db, user_id=base.user_id, organization_id=base.org_id) == 0
        from dossier.services.plan_limits import assert_can_start_dossiers

        assert_can_start_dossiers(db, user=db.get(User, base.user_id), org=db.get(Organization, base.org_id))


def test_dos_barridos_a_la_vez_no_recuperan_dos_veces(base):
    ids = {trabajo(base, hace_inicio=900, hace_latido=900) for _ in range(5)}
    resultados: list[list[uuid.UUID]] = []
    barrera = threading.Barrier(3)

    def correr():
        barrera.wait()
        resultados.append(barrer(base))

    hilos = [threading.Thread(target=correr) for _ in range(3)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    todos = [i for r in resultados for i in r]
    assert sorted(todos) == sorted(ids)
    with base.engine.connect() as c:
        auditados = c.execute(
            text("SELECT count(*) FROM audit_logs WHERE resource_id = ANY(:ids)"), {"ids": list(ids)}
        ).scalar_one()
    assert auditados == 5


# --- Latido y cierre del proceso que genera ---------------------------------------


def _pipeline_lento(segundos: float, guardado: dict | None = None):
    def correr(db, *, user, org, body, progress):
        time.sleep(segundos)
        return {"saved_dossier": guardado or {"id": str(uuid.uuid4()), "status": "complete", "credits_consumed": 0}}

    return correr


def test_mientras_genera_el_proceso_deja_latido(base, monkeypatch):
    monkeypatch.setenv("DOSSIER_JOB_HEARTBEAT_SECONDS", "0.3")
    monkeypatch.setattr(servicio, "run_person_research_and_persist", _pipeline_lento(1.5))
    monkeypatch.setattr(servicio, "enviar_dossier_al_solicitante", lambda *a, **k: None)
    job_id = trabajo(base, status="queued")
    vistos: list[datetime | None] = []

    def mirar():
        time.sleep(1.0)
        vistos.append(leer(base, job_id).heartbeat_at)

    hilo = threading.Thread(target=mirar)
    hilo.start()
    with Session(base.engine) as db:
        servicio.process_dossier_generation_job(db, job_id)
    hilo.join()

    job = leer(base, job_id)
    assert job.status == "completed"
    assert vistos[0] is not None
    assert vistos[0] > job.started_at + timedelta(seconds=0.2)


def test_si_lo_marcaron_fallido_el_proceso_no_lo_pisa_al_terminar(base, monkeypatch):
    """Un proceso que en realidad seguía vivo no convierte el «fallido» en «completado»."""
    job_id = trabajo(base, status="queued")

    def recuperado_a_mitad(db, *, user, org, body, progress):
        with base.engine.begin() as c:
            c.execute(
                text("UPDATE dossier_generation_jobs SET status = 'failed', error_message = :m WHERE id = :i"),
                {"m": INTERRUPTED_MESSAGE, "i": job_id},
            )
        return {"saved_dossier": {"id": str(uuid.uuid4()), "status": "complete", "credits_consumed": 0}}

    monkeypatch.setattr(servicio, "run_person_research_and_persist", recuperado_a_mitad)
    enviados = []
    monkeypatch.setattr(servicio, "enviar_dossier_al_solicitante", lambda *a, **k: enviados.append(1))
    with Session(base.engine) as db:
        servicio.process_dossier_generation_job(db, job_id)

    job = leer(base, job_id)
    assert job.status == "failed"
    assert job.error_message == INTERRUPTED_MESSAGE
    assert enviados == []


def test_si_lo_marcaron_fallido_un_error_posterior_no_cambia_el_mensaje(base, monkeypatch):
    job_id = trabajo(base, status="queued")

    def recuperado_y_revienta(db, *, user, org, body, progress):
        with base.engine.begin() as c:
            c.execute(
                text("UPDATE dossier_generation_jobs SET status = 'failed', error_message = :m WHERE id = :i"),
                {"m": INTERRUPTED_MESSAGE, "i": job_id},
            )
        raise RuntimeError("proveedor caído")

    monkeypatch.setattr(servicio, "run_person_research_and_persist", recuperado_y_revienta)
    with Session(base.engine) as db:
        servicio.process_dossier_generation_job(db, job_id)
    assert leer(base, job_id).error_message == INTERRUPTED_MESSAGE


def test_al_tomar_un_trabajo_de_la_cola_se_marca_el_primer_latido(base):
    job_id = trabajo(base, status="queued")
    with Session(base.engine) as db:
        tomado = servicio.claim_next_queued_job(db)
        assert tomado is not None and tomado.id == job_id
    job = leer(base, job_id)
    assert job.heartbeat_at is not None
    assert abs((job.heartbeat_at - job.started_at).total_seconds()) < 1


# --- Migración ----------------------------------------------------------------------


def test_la_migracion_agrega_y_quita_la_columna(base, alembic_cfg):
    def tiene_columna() -> bool:
        with base.engine.connect() as c:
            return bool(
                c.execute(
                    text(
                        "SELECT count(*) FROM information_schema.columns "
                        "WHERE table_name = 'dossier_generation_jobs' AND column_name = 'heartbeat_at'"
                    )
                ).scalar_one()
            )

    assert tiene_columna()
    command.downgrade(alembic_cfg, "-1")
    assert not tiene_columna()
    command.upgrade(alembic_cfg, "head")
    assert tiene_columna()
