"""S6.6, integración: auditoría de envíos por correo y de borrados por retención.

Especificación: ``specs/proposals/S6.6-auditoria-correo-borrado.md`` (CA1–CA3, CA5, CA7–CA9,
CA11). Postgres real (``pg_vacia``) y el SMTP de loopback (``servidor_smtp``).
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from alembic import command
from dossier.api.app import app
from dossier.api.auth_routes import get_db_if_configured
from dossier.db.models import AuditLog, Dossier, DossierGenerationJob, Organization, OrgMembership, User
from dossier.security.jwt_tokens import create_access_token
from dossier.services import audit_log as al
from dossier.services import dossier_email
from dossier.services import dossier_retention_worker as worker

INFORME = "## Resumen\n\nAna Prueba dirige Empresa de Prueba SA."


class Mundo:
    def __init__(self, engine):
        self.engine = engine
        self.s = Session(engine)
        sufijo = uuid.uuid4().hex[:8]
        self.org = Organization(name=f"Org {sufijo}", slug=f"org-{sufijo}", plan="pro")
        self.otra = Organization(name=f"Otra {sufijo}", slug=f"otra-{sufijo}", plan="pro")
        self.s.add_all([self.org, self.otra])
        self.s.commit()
        self.yo = User(email=f"yo-{sufijo}@example.com")
        self.s.add(self.yo)
        self.s.flush()
        self.s.add(OrgMembership(organization_id=self.org.id, user_id=self.yo.id, role="user", is_primary_org=True))
        self.s.commit()

    def token(self) -> dict:
        t = create_access_token(user_id=str(self.yo.id), email=self.yo.email,
                                organization_id=str(self.org.id), role="user")
        return {"Authorization": f"Bearer {t}"}

    def dossier(self, org=None, horas: float = 0) -> Dossier:
        d = Dossier(
            organization_id=(org or self.org).id,
            requested_by_user_id=self.yo.id,
            subject_name="Ana Prueba",
            status="complete",
            dossier_data={"format": "markdown", "body": INFORME, "billing": "none", "output_language": "es"},
        )
        self.s.add(d)
        self.s.commit()
        if horas:
            self.s.execute(
                text("UPDATE dossiers SET created_at = :c WHERE id = :i"),
                {"c": datetime.now(UTC) - timedelta(hours=horas), "i": d.id},
            )
            self.s.commit()
        return d

    def leer(self, dossier_id) -> Dossier:
        self.s.expire_all()
        return self.s.get(Dossier, dossier_id)

    def registros(self, prefijo: str) -> list[AuditLog]:
        with Session(self.engine) as s:
            filas = s.scalars(select(AuditLog).order_by(AuditLog.created_at)).all()
            return [f for f in filas if f.action.startswith(prefijo)]


@pytest.fixture
def mundo(pg_vacia, alembic_cfg, monkeypatch):
    command.upgrade(alembic_cfg, "head")
    DossierGenerationJob.__table__.create(bind=pg_vacia, checkfirst=True)
    monkeypatch.delenv("DOSSIER_RETENTION_HOURS", raising=False)
    m = Mundo(pg_vacia)

    def _db():
        with Session(pg_vacia) as sesion:
            yield sesion

    app.dependency_overrides[get_db_if_configured] = _db
    yield m
    app.dependency_overrides.pop(get_db_if_configured, None)
    m.s.close()


@pytest.fixture
def client():
    return TestClient(app)


def _enviar(client, mundo, d):
    return client.post(f"/dossiers/{d.id}/email", headers=mundo.token())


# --------------------------------------------------------------------------
# Envío manual
# --------------------------------------------------------------------------


def test_ca1_envio_manual_exitoso_queda_registrado(mundo, client, servidor_smtp):
    d = mundo.dossier()
    assert _enviar(client, mundo, d).status_code == 200

    (fila,) = mundo.registros("EMAIL")
    assert fila.action == "EMAIL dossier_manual"
    assert (fila.resource_type, fila.resource_id) == ("dossier", d.id)
    assert (fila.user_id, fila.organization_id) == (mundo.yo.id, mundo.org.id)
    assert fila.success is True
    assert al.verify_log_hash(fila) is True


def test_ca2_envio_manual_fallido_queda_registrado_y_no_marca_el_dossier(mundo, client, servidor_smtp):
    servidor_smtp.rechazar = True
    d = mundo.dossier()
    assert _enviar(client, mundo, d).status_code == 502

    (fila,) = mundo.registros("EMAIL")
    assert fila.action == "EMAIL dossier_manual"
    assert fila.success is False
    assert fila.error_message == "EmailDeliveryError"
    assert al.verify_log_hash(fila) is True
    assert mundo.leer(d.id).email_sent is not True


def test_ca5_el_middleware_audita_la_ruta_de_envio(mundo, client, servidor_smtp):
    propio = mundo.dossier()
    ajeno = mundo.dossier(org=mundo.otra)
    assert _enviar(client, mundo, propio).status_code == 200
    assert _enviar(client, mundo, ajeno).status_code == 404

    http = mundo.registros("POST /dossiers/{dossier_id}/email")
    assert [(f.resource_id, f.http_status) for f in http] == [(propio.id, 200), (ajeno.id, 404)]


def test_ca11_si_la_auditoria_falla_el_envio_responde_igual(mundo, client, servidor_smtp, monkeypatch):
    def _falla(*_a, **_k):
        raise RuntimeError("audit_logs no disponible")

    monkeypatch.setattr(dossier_email, "record", _falla)
    d = mundo.dossier()
    resp = _enviar(client, mundo, d)

    assert resp.status_code == 200, resp.text
    assert resp.json()["email_sent"] is True
    assert mundo.leer(d.id).email_sent is True


# --------------------------------------------------------------------------
# Envío automático
# --------------------------------------------------------------------------


@pytest.mark.parametrize("rechazar", [False, True])
def test_ca3_envio_automatico_queda_registrado(mundo, servidor_smtp, rechazar):
    servidor_smtp.rechazar = rechazar
    d = mundo.dossier()
    with Session(mundo.engine) as db:
        enviado = dossier_email.deliver_dossier_after_generation(db, dossier_id=d.id, recipient=mundo.yo.email)

    assert enviado is (not rechazar)
    (fila,) = mundo.registros("EMAIL")
    assert fila.action == "EMAIL dossier_auto"
    assert (fila.resource_id, fila.user_id, fila.organization_id) == (d.id, mundo.yo.id, mundo.org.id)
    assert fila.success is (not rechazar)
    assert al.verify_log_hash(fila) is True


# --------------------------------------------------------------------------
# Borrado por retención
# --------------------------------------------------------------------------


def _job(mundo, horas: float) -> None:
    momento = datetime.now(UTC) - timedelta(hours=horas)
    mundo.s.execute(
        text(
            "INSERT INTO dossier_generation_jobs (id, organization_id, requested_by_user_id, status, "
            "job_type, depth_level, credits_estimated, credits_consumed, created_at, completed_at) "
            "VALUES (:i, :o, :u, 'completed', 'person', 'standard', 1, 1, :c, :c)"
        ),
        {"i": uuid.uuid4(), "o": mundo.org.id, "u": mundo.yo.id, "c": momento},
    )
    mundo.s.commit()


def test_ca7_ca8_borrados_jobs_y_verificacion_quedan_registrados(mundo):
    viejos = [mundo.dossier(horas=30).id, mundo.dossier(horas=48).id]
    mundo.dossier(horas=1)  # reciente: no se borra ni se registra
    _job(mundo, horas=30)
    _job(mundo, horas=40)

    with Session(mundo.engine) as db:
        resultado = worker.purge_expired_dossiers(db)
    assert resultado.verificado is True

    borrados = mundo.registros("RETENTION dossier_deleted")
    assert sorted(f.resource_id for f in borrados) == sorted(viejos)
    (jobs,) = mundo.registros("RETENTION jobs_deleted")
    assert jobs.request_data["jobs"] == 2
    (verif,) = mundo.registros("RETENTION verification")
    assert verif.success is True
    assert verif.request_data["dossiers"] == 2
    assert verif.request_data["restos"] == {}
    assert all(al.verify_log_hash(f) for f in [*borrados, jobs, verif])


def test_ca8_con_restos_la_verificacion_queda_fallida(mundo, monkeypatch):
    mundo.dossier(horas=30)
    monkeypatch.setattr(worker, "verificar_borrado", lambda *_a, **_k: {"redis": 1})

    with Session(mundo.engine) as db:
        resultado = worker.purge_expired_dossiers(db)
    assert resultado.verificado is False

    (verif,) = mundo.registros("RETENTION verification")
    assert verif.success is False
    assert verif.request_data["restos"] == {"redis": 1}


def test_ca9_una_vuelta_sin_nada_que_borrar_no_deja_registro(mundo):
    mundo.dossier(horas=2)
    with Session(mundo.engine) as db:
        worker.purge_expired_dossiers(db)
    assert mundo.registros("RETENTION") == []
