"""S4.10 · Toda lectura y generación de dossier queda en `audit_logs` (contra Postgres).

Criterio del plan: "con actor, organización, recurso e instante". Requiere
``TEST_DATABASE_URL`` (fixture ``pg_vacia``).
"""
from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from alembic import command
from dossier.api.app import app
from dossier.api.auth_routes import get_db_if_configured
from dossier.db.models import AuditLog, DossierGenerationJob
from dossier.security.jwt_tokens import create_access_token
from dossier.services import audit_log as al
from dossier.services import dossier_generation_job_service as servicio


@pytest.fixture
def mundo(pg_vacia, alembic_cfg) -> Iterator[SimpleNamespace]:
    command.upgrade(alembic_cfg, "head")
    with pg_vacia.begin() as c:
        org = c.execute(text("INSERT INTO organizations (name, slug) VALUES ('A', 'a') RETURNING id")).scalar_one()
        otra = c.execute(text("INSERT INTO organizations (name, slug) VALUES ('B', 'b') RETURNING id")).scalar_one()
        user = c.execute(text("INSERT INTO users (email) VALUES ('ana@example.com') RETURNING id")).scalar_one()
        c.execute(
            text("INSERT INTO org_memberships (organization_id, user_id, role, is_primary_org) VALUES (:o, :u, 'admin', TRUE)"),
            {"o": org, "u": user},
        )
        propio = c.execute(
            text(
                "INSERT INTO dossiers (organization_id, requested_by_user_id, status, dossier_data) "
                "VALUES (:o, :u, 'complete', CAST(:d AS JSONB)) RETURNING id"
            ),
            {"o": org, "u": user, "d": json.dumps({"markdown": "# Informe"})},
        ).scalar_one()
        ajeno = c.execute(
            text(
                "INSERT INTO dossiers (organization_id, requested_by_user_id, status, dossier_data) "
                "VALUES (:o, :u, 'complete', CAST('{}' AS JSONB)) RETURNING id"
            ),
            {"o": otra, "u": user},
        ).scalar_one()

    def _db():
        with Session(pg_vacia) as s:
            yield s

    app.dependency_overrides[get_db_if_configured] = _db
    token = create_access_token(user_id=str(user), email="ana@example.com", organization_id=str(org), role="admin")
    try:
        yield SimpleNamespace(
            engine=pg_vacia,
            org=org,
            user=user,
            propio=propio,
            ajeno=ajeno,
            cliente=TestClient(app, headers={"Authorization": f"Bearer {token}", "User-Agent": "pytest-s410"}),
        )
    finally:
        app.dependency_overrides.pop(get_db_if_configured, None)


def _registros(engine) -> list[AuditLog]:
    with Session(engine) as s:
        return list(s.scalars(select(AuditLog).order_by(AuditLog.created_at)))


def test_leer_un_dossier_queda_registrado_con_actor_organizacion_recurso_e_instante(mundo):
    r = mundo.cliente.get(f"/dossiers/{mundo.propio}")
    assert r.status_code == 200, r.text

    (fila,) = _registros(mundo.engine)
    assert fila.action == "GET /dossiers/{dossier_id}"
    assert (fila.resource_type, fila.resource_id) == ("dossier", mundo.propio)
    assert (fila.user_id, fila.organization_id, fila.user_role_at_time) == (mundo.user, mundo.org, "admin")
    assert fila.created_at is not None
    assert (fila.http_status, fila.success) == (200, True)
    assert fila.user_agent == "pytest-s410"
    assert fila.duration_ms is not None and fila.duration_ms >= 0
    assert al.verify_log_hash(fila) is True


def test_listar_dossiers_queda_registrado(mundo):
    mundo.cliente.get("/dossiers", params={"limit": 5})

    (fila,) = _registros(mundo.engine)
    assert fila.action == "GET /dossiers"
    assert fila.resource_id is None
    assert fila.request_data == {"params": {"limit": "5"}}


def test_intento_sobre_un_dossier_de_otra_organizacion_queda_como_fallido(mundo):
    r = mundo.cliente.get(f"/dossiers/{mundo.ajeno}")
    assert r.status_code in (403, 404)

    (fila,) = _registros(mundo.engine)
    assert (fila.resource_id, fila.success, fila.http_status) == (mundo.ajeno, False, r.status_code)
    assert fila.user_id == mundo.user


def test_peticion_sin_sesion_queda_registrada_sin_actor(mundo):
    r = TestClient(app).get(f"/dossiers/{mundo.propio}")
    assert r.status_code == 401

    (fila,) = _registros(mundo.engine)
    assert (fila.user_id, fila.success, fila.http_status) == (None, False, 401)


def test_borrar_un_dossier_queda_registrado(mundo):
    r = mundo.cliente.delete(f"/dossiers/{mundo.propio}")
    assert r.status_code == 204, r.text

    (fila,) = _registros(mundo.engine)
    assert (fila.action, fila.resource_id, fila.success) == ("DELETE /dossiers/{dossier_id}", mundo.propio, True)


def test_rutas_que_no_son_de_dossiers_no_se_registran(mundo):
    mundo.cliente.get("/auth/me")
    mundo.cliente.get("/health")

    assert _registros(mundo.engine) == []


def test_un_job_terminado_por_el_trabajador_queda_registrado(mundo, monkeypatch):
    """La generación en segundo plano no pasa por HTTP: el trabajador deja su propio registro."""
    dossier_generado = str(uuid.uuid4())

    def _proceso_falso(db, job):
        job.status = "completed"
        job.result_payload = {"saved_dossier": {"id": dossier_generado}}
        db.commit()

    monkeypatch.setattr(servicio, "_process_person_manual_job", _proceso_falso)
    monkeypatch.setattr(servicio, "_publicar_estado", lambda job: None)
    with Session(mundo.engine) as s:
        job = DossierGenerationJob(
            organization_id=mundo.org,
            requested_by_user_id=mundo.user,
            status="queued",
            job_type="person_manual",
            depth_level="standard",
            credits_estimated=1,
            credits_consumed=0,
            reunion_snapshot={"person_request": {"full_name": "Ana Prueba", "email": "ana@empresa.cl"}},
        )
        s.add(job)
        s.commit()
        job_id = job.id

        servicio.process_dossier_generation_job(s, job_id)

    (fila,) = _registros(mundo.engine)
    assert fila.action == "JOB person_manual"
    assert (fila.resource_type, fila.resource_id) == ("dossier_generation_job", job_id)
    assert (fila.user_id, fila.organization_id, fila.success) == (mundo.user, mundo.org, True)
    assert fila.request_data == {"status": "completed", "dossier_ids": [dossier_generado]}
    assert "ana@empresa.cl" not in json.dumps(fila.request_data)


def test_un_job_que_falla_queda_registrado_como_fallido(mundo, monkeypatch):
    def _proceso_que_falla(db, job):
        raise RuntimeError("proveedor caído")

    monkeypatch.setattr(servicio, "_process_person_manual_job", _proceso_que_falla)
    monkeypatch.setattr(servicio, "_publicar_estado", lambda job: None)
    with Session(mundo.engine) as s:
        job = DossierGenerationJob(
            organization_id=mundo.org,
            requested_by_user_id=mundo.user,
            status="queued",
            job_type="person_manual",
            depth_level="standard",
            credits_estimated=1,
            credits_consumed=0,
        )
        s.add(job)
        s.commit()
        servicio.process_dossier_generation_job(s, job.id)

    (fila,) = _registros(mundo.engine)
    assert (fila.action, fila.success) == ("JOB person_manual", False)
    assert fila.error_message == "proveedor caído"


def test_la_generacion_automatica_del_calendario_queda_registrada(mundo):
    """La automatización corre sin petición HTTP: deja su propio registro, solo con ids."""
    from dossier.services import calendar_automation as auto

    evento = SimpleNamespace(
        id=uuid.uuid4(), user_id=mundo.user, processing_status="completed", skip_reason=None
    )
    guardados = {"corporate": {"id": str(mundo.propio)}, "folder": {"id": str(uuid.uuid4())}}
    with Session(mundo.engine) as s:
        auto._auditar_generacion_automatica(s, evento, mundo.org, guardados)
        s.commit()

    (fila,) = _registros(mundo.engine)
    assert fila.action == "AUTO calendar_automation"
    assert (fila.resource_id, fila.user_id, fila.organization_id, fila.success) == (
        mundo.propio,
        mundo.user,
        mundo.org,
        True,
    )
    assert fila.request_data == {"calendar_event_id": str(evento.id), "dossier_ids": [str(mundo.propio)]}


def test_una_generacion_automatica_fallida_queda_como_fallida(mundo):
    from dossier.services import calendar_automation as auto

    evento = SimpleNamespace(
        id=uuid.uuid4(), user_id=mundo.user, processing_status="failed", skip_reason="sin_participantes"
    )
    with Session(mundo.engine) as s:
        auto._auditar_generacion_automatica(s, evento, mundo.org, None)
        s.commit()

    (fila,) = _registros(mundo.engine)
    assert (fila.success, fila.error_message, fila.resource_id) == (False, "sin_participantes", None)
