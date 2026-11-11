"""S6.4, integración: reintentos de envío contra Postgres real y el SMTP de loopback.

Especificación: ``specs/proposals/S6.4-reintento-correo.md`` (CA3–CA9, CA13, CA14).
Un puerto cerrado simula el servidor caído (fallo pasajero); ``servidor_smtp.rechazar``, un 550
(definitivo). Las esperas entre intentos seguidos se anulan.
"""
from __future__ import annotations

import os
import socket
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from alembic import command
from dossier.api.app import app
from dossier.api.auth_routes import get_db_if_configured
from dossier.db.models import AuditLog, Dossier, DossierEmailRetry, Organization, OrgMembership, User
from dossier.security.jwt_tokens import create_access_token
from dossier.services import dossier_email, dossier_email_retry
from dossier.services.dossier_email import deliver_dossier_after_generation, deliver_meeting_dossiers
from dossier.services.dossier_email_retry import encolar_reintento, procesar_reintentos
from dossier.services.email_service import EmailDeliveryError

REVISION_ANTERIOR = "e8b1f4a6c2d9"


def _puerto_cerrado() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Mundo:
    def __init__(self, engine):
        self.engine = engine
        self.s = Session(engine)
        sufijo = uuid.uuid4().hex[:8]
        self.org = Organization(name=f"Org {sufijo}", slug=f"org-{sufijo}", plan="pro")
        self.s.add(self.org)
        self.s.commit()
        self.yo = User(email=f"yo-{sufijo}@mi-empresa.example")
        self.s.add(self.yo)
        self.s.flush()
        self.s.add(OrgMembership(organization_id=self.org.id, user_id=self.yo.id, role="user", is_primary_org=True))
        self.s.commit()

    def dossier(self, nombre="Ana Prueba") -> Dossier:
        d = Dossier(
            organization_id=self.org.id, requested_by_user_id=self.yo.id, subject_name=nombre, status="complete",
            dossier_data={"format": "markdown", "body": f"## {nombre}", "billing": "none", "output_language": "es"},
        )
        self.s.add(d)
        self.s.commit()
        return d

    def filas(self) -> list[DossierEmailRetry]:
        with Session(self.engine) as s:
            return list(s.scalars(select(DossierEmailRetry)).all())

    def envios(self) -> list[AuditLog]:
        with Session(self.engine) as s:
            return [f for f in s.scalars(select(AuditLog).order_by(AuditLog.created_at)) if f.action.startswith("EMAIL")]

    def leer(self, dossier_id):
        self.s.expire_all()
        return self.s.get(Dossier, dossier_id)


@pytest.fixture
def mundo(pg_vacia, alembic_cfg, monkeypatch):
    command.upgrade(alembic_cfg, "head")
    monkeypatch.setattr(dossier_email_retry, "_dormir", lambda _s: None)
    m = Mundo(pg_vacia)
    yield m
    m.s.close()


@pytest.fixture
def smtp_caido(servidor_smtp, monkeypatch):
    """El SMTP de loopback existe, pero el envío apunta a un puerto cerrado.

    ``smtp_caido.puerto_real`` permite "levantarlo" de nuevo a mitad de la prueba.
    """
    servidor_smtp.puerto_real = os.environ["SMTP_PORT"]
    monkeypatch.setenv("SMTP_PORT", str(_puerto_cerrado()))
    return servidor_smtp


def _en_espera(mundo, d, *, intentos_previos=0):
    """Un envío de Personas en espera, ya vencido a la hora que use la prueba."""
    with Session(mundo.engine) as db:
        dossier = db.get(Dossier, d.id)
        encolar_reintento(db, kind="persona", dossiers=[dossier], error=EmailDeliveryError("x", transitorio=True))
        db.commit()
        fila = db.scalars(select(DossierEmailRetry)).one()
        fila.attempts = intentos_previos
        db.commit()


DESPUES = timedelta(minutes=11)


# --------------------------------------------------------------------------
# CA3 · intentos seguidos y paso a la espera
# --------------------------------------------------------------------------


def test_ca3_un_fallo_pasajero_queda_en_espera_10_minutos(mundo, smtp_caido):
    d = mundo.dossier()
    antes = datetime.now(UTC)
    with Session(mundo.engine) as db:
        assert deliver_dossier_after_generation(db, dossier_id=d.id, recipient=mundo.yo.email) is False

    (fila,) = mundo.filas()
    assert fila.kind == "persona"
    assert fila.dossier_ids == [d.id]
    assert (fila.user_id, fila.organization_id, fila.attempts) == (mundo.yo.id, mundo.org.id, 0)
    assert antes + timedelta(minutes=9) < fila.next_attempt_at < antes + timedelta(minutes=11)
    assert fila.last_error == "EmailDeliveryError"
    (envio,) = mundo.envios()
    assert envio.success is False
    assert envio.request_data["intentos"] == 3
    assert envio.request_data["reintento_programado"] is True


def test_ca3_una_reunion_caida_queda_en_espera_con_todos_sus_dossiers(mundo, smtp_caido):
    ids = [mundo.dossier("Acme SA").id, mundo.dossier("Ana Prueba").id]
    with Session(mundo.engine) as db:
        assert not deliver_meeting_dossiers(db, dossier_ids=ids, recipient=mundo.yo.email,
                                            meeting_title="Demo", language="es", calendar_event_id=None)
    (fila,) = mundo.filas()
    assert fila.kind == "reunion"
    assert sorted(fila.dossier_ids) == sorted(ids)
    assert (fila.meeting_title, fila.language) == ("Demo", "es")


def test_ca3_un_fallo_definitivo_no_queda_en_espera(mundo, servidor_smtp):
    servidor_smtp.rechazar = True
    d = mundo.dossier()
    with Session(mundo.engine) as db:
        assert deliver_dossier_after_generation(db, dossier_id=d.id, recipient=mundo.yo.email) is False

    assert mundo.filas() == []
    (envio,) = mundo.envios()
    assert envio.request_data["intentos"] == 1
    assert envio.request_data["reintento_programado"] is False


# --------------------------------------------------------------------------
# CA4–CA8 · el proceso de reintentos
# --------------------------------------------------------------------------


def test_ca4_un_reintento_que_sale_marca_y_borra_la_fila(mundo, servidor_smtp):
    d = mundo.dossier()
    _en_espera(mundo, d)

    with Session(mundo.engine) as db:
        resumen = procesar_reintentos(db, now=datetime.now(UTC) + DESPUES)

    assert resumen["enviados"] == 1
    assert len(servidor_smtp.mensajes) == 1
    assert mundo.leer(d.id).email_sent is True
    assert mundo.filas() == []
    (envio,) = mundo.envios()
    assert envio.success is True
    assert envio.request_data["reintento"] == 1


def test_ca5_un_reintento_fallido_se_programa_10_minutos_despues(mundo, smtp_caido):
    d = mundo.dossier()
    _en_espera(mundo, d)
    ahora = datetime.now(UTC) + DESPUES

    with Session(mundo.engine) as db:
        assert procesar_reintentos(db, now=ahora)["reprogramados"] == 1

    (fila,) = mundo.filas()
    assert fila.attempts == 1
    assert fila.next_attempt_at == ahora + timedelta(minutes=10)
    (envio,) = mundo.envios()
    assert (envio.success, envio.request_data["reintento"], envio.request_data["agotado"]) == (False, 1, False)


def test_ca6_el_sexto_reintento_fallido_lo_da_por_perdido(mundo, smtp_caido):
    d = mundo.dossier()
    _en_espera(mundo, d, intentos_previos=5)

    with Session(mundo.engine) as db:
        assert procesar_reintentos(db, now=datetime.now(UTC) + DESPUES)["agotados"] == 1

    assert mundo.filas() == []
    (envio,) = mundo.envios()
    assert (envio.request_data["reintento"], envio.request_data["agotado"]) == (6, True)
    assert mundo.leer(d.id).email_sent is not True


def test_ca6_un_fallo_definitivo_en_el_reintento_borra_la_fila(mundo, servidor_smtp):
    servidor_smtp.rechazar = True
    d = mundo.dossier()
    _en_espera(mundo, d)

    with Session(mundo.engine) as db:
        assert procesar_reintentos(db, now=datetime.now(UTC) + DESPUES)["agotados"] == 1
    assert mundo.filas() == []


def test_ca7_si_el_dossier_ya_no_existe_se_descarta(mundo, servidor_smtp):
    d = mundo.dossier()
    _en_espera(mundo, d)
    mundo.s.delete(mundo.s.get(Dossier, d.id))
    mundo.s.commit()

    with Session(mundo.engine) as db:
        assert procesar_reintentos(db, now=datetime.now(UTC) + DESPUES)["descartados"] == 1
    assert mundo.filas() == []
    assert servidor_smtp.conexiones == 0


def test_ca8_un_envio_que_no_vence_no_se_toca(mundo, servidor_smtp):
    d = mundo.dossier()
    _en_espera(mundo, d)

    with Session(mundo.engine) as db:
        resumen = procesar_reintentos(db, now=datetime.now(UTC) + timedelta(minutes=2))
    assert sum(resumen.values()) == 0
    assert len(mundo.filas()) == 1
    assert servidor_smtp.conexiones == 0


def test_ca4_una_reunion_en_espera_se_reenvia_en_un_solo_correo(mundo, smtp_caido, monkeypatch):
    ids = [mundo.dossier("Acme SA").id, mundo.dossier("Ana Prueba").id]
    with Session(mundo.engine) as db:
        deliver_meeting_dossiers(db, dossier_ids=ids, recipient=mundo.yo.email,
                                 meeting_title="Demo", language="es", calendar_event_id=None)
    monkeypatch.setenv("SMTP_PORT", smtp_caido.puerto_real)  # vuelve el servidor

    with Session(mundo.engine) as db:
        assert procesar_reintentos(db, now=datetime.now(UTC) + DESPUES)["enviados"] == 1

    (mensaje,) = smtp_caido.mensajes
    assert mensaje["Subject"] == "Dossiers: Demo"
    assert len(list(mensaje.iter_attachments())) == 2


# --------------------------------------------------------------------------
# CA14 · el envío manual intenta una sola vez
# --------------------------------------------------------------------------


def test_ca14_el_boton_intenta_una_sola_vez(mundo, servidor_smtp, monkeypatch):
    llamadas = []

    def _caido(**_k):
        llamadas.append(1)
        raise EmailDeliveryError("sin conexión", transitorio=True)

    monkeypatch.setattr(dossier_email, "send_email", _caido)

    def _db():
        with Session(mundo.engine) as sesion:
            yield sesion

    app.dependency_overrides[get_db_if_configured] = _db
    try:
        token = create_access_token(user_id=str(mundo.yo.id), email=mundo.yo.email,
                                    organization_id=str(mundo.org.id), role="user")
        d = mundo.dossier()
        r = TestClient(app).post(f"/dossiers/{d.id}/email", headers={"Authorization": f"Bearer {token}"})
    finally:
        app.dependency_overrides.pop(get_db_if_configured, None)

    assert r.status_code == 502
    assert llamadas == [1]
    assert mundo.filas() == []


# --------------------------------------------------------------------------
# CA13 · migración
# --------------------------------------------------------------------------


def test_ca13_la_migracion_crea_la_tabla_como_el_orm_y_el_downgrade_la_quita(pg_vacia, alembic_cfg):
    command.upgrade(alembic_cfg, "head")
    columnas = {c["name"] for c in inspect(pg_vacia).get_columns("dossier_email_retries")}
    assert columnas == set(DossierEmailRetry.__table__.columns.keys())

    command.downgrade(alembic_cfg, REVISION_ANTERIOR)
    assert "dossier_email_retries" not in inspect(pg_vacia).get_table_names()
