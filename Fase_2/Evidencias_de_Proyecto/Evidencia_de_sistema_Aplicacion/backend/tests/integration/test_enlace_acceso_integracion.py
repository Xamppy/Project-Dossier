"""S6.2, integración: el enlace de un solo uso contra Postgres real, la API y el SMTP de loopback.

Especificación: ``specs/proposals/S6.2-enlace-un-solo-uso.md`` (CA1–CA4, CA7–CA9, CA14).
"""
from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from alembic import command
from dossier.api.app import app
from dossier.api.auth_routes import get_db_if_configured
from dossier.db.models import (
    AuditLog,
    Dossier,
    DossierAccessLink,
    DossierEmailRetry,
    Organization,
    OrgMembership,
    User,
)
from dossier.security.jwt_tokens import create_access_token
from dossier.services import dossier_email_retry
from dossier.services.dossier_access_links import crear_enlace
from dossier.services.dossier_email import deliver_dossier_after_generation, deliver_meeting_dossiers
from dossier.services.dossier_email_retry import encolar_reintento, procesar_reintentos
from dossier.services.dossier_retention_worker import purge_expired_dossiers
from dossier.services.email_service import EmailDeliveryError

REVISION_ANTERIOR = "a9d3e5f7b1c4"
INVALIDO = "El enlace ya no es válido."
_TOKEN = re.compile(r"/acceso#t=([A-Za-z0-9_\-]+)")


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

    def dossier(self, nombre="Ana Prueba", status="complete") -> Dossier:
        d = Dossier(
            organization_id=self.org.id, requested_by_user_id=self.yo.id, subject_name=nombre, status=status,
            dossier_data={"format": "markdown", "body": f"## {nombre}\n\nInforme de prueba.", "billing": "none",
                          "output_language": "es"},
        )
        self.s.add(d)
        self.s.commit()
        return d

    def enlace(self, d, *, now=None) -> str:
        with Session(self.engine) as db:
            token = crear_enlace(db, db.get(Dossier, d.id), user_id=self.yo.id, now=now)
            db.commit()
        return token

    def enlaces(self) -> list[DossierAccessLink]:
        with Session(self.engine) as s:
            return list(s.scalars(select(DossierAccessLink)).all())

    def registros(self, prefijo) -> list[AuditLog]:
        with Session(self.engine) as s:
            return [f for f in s.scalars(select(AuditLog).order_by(AuditLog.created_at)) if f.action.startswith(prefijo)]


@pytest.fixture
def mundo(pg_vacia, alembic_cfg, monkeypatch):
    command.upgrade(alembic_cfg, "head")
    monkeypatch.setattr(dossier_email_retry, "_dormir", lambda _s: None)
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


def _canjear(client, token):
    return client.post("/dossier-access", json={"token": token})


# --------------------------------------------------------------------------
# CA1–CA4 · el canje
# --------------------------------------------------------------------------


def test_ca1_ca2_se_canjea_una_sola_vez(mundo, client):
    d = mundo.dossier()
    token = mundo.enlace(d)

    primero = _canjear(client, token)
    assert primero.status_code == 200, primero.text
    cuerpo = primero.json()
    assert cuerpo["subject_name"] == "Ana Prueba"
    assert "Informe de prueba." in cuerpo["body"]
    assert cuerpo["output_language"] == "es"
    assert cuerpo["created_at"]

    segundo = _canjear(client, token)
    assert segundo.status_code == 410
    assert segundo.json()["detail"] == INVALIDO


def test_ca3_un_enlace_vencido_no_sirve(mundo, client):
    d = mundo.dossier()
    token = mundo.enlace(d, now=datetime.now(UTC) - timedelta(hours=25))
    r = _canjear(client, token)
    assert (r.status_code, r.json()["detail"]) == (410, INVALIDO)


@pytest.mark.parametrize("caso", ["inexistente", "borrado", "incompleto"])
def test_ca4_los_demas_casos_responden_igual(mundo, client, caso):
    if caso == "inexistente":
        token = "no-existe-" + uuid.uuid4().hex
    else:
        d = mundo.dossier(status="failed" if caso == "incompleto" else "complete")
        token = mundo.enlace(d)
        if caso == "borrado":
            mundo.s.delete(mundo.s.get(Dossier, d.id))
            mundo.s.commit()
    r = _canjear(client, token)
    assert (r.status_code, r.json()["detail"]) == (410, INVALIDO)


# --------------------------------------------------------------------------
# CA9 · auditoría
# --------------------------------------------------------------------------


def test_ca9_cada_canje_queda_auditado_sin_el_token(mundo, client):
    d = mundo.dossier()
    token = mundo.enlace(d)
    _canjear(client, token)
    _canjear(client, token)

    exito, fallo = mundo.registros("ACCESS dossier_link")
    assert (exito.success, exito.resource_id, exito.organization_id) == (True, d.id, mundo.org.id)
    assert (fallo.success, fallo.resource_id) == (False, None)
    for f in (exito, fallo):
        assert token not in str(f.request_data) + str(f.error_message)


# --------------------------------------------------------------------------
# CA7, CA8 · los correos llevan un enlace que funciona
# --------------------------------------------------------------------------


def _token_del_correo(mensaje) -> str:
    html = mensaje.get_body(("html",)).get_content()
    (token,) = set(_TOKEN.findall(html))
    return token


def test_ca7_el_boton_manual_envia_un_enlace_que_funciona(mundo, client, servidor_smtp):
    d = mundo.dossier()
    t = create_access_token(user_id=str(mundo.yo.id), email=mundo.yo.email,
                            organization_id=str(mundo.org.id), role="user")
    assert client.post(f"/dossiers/{d.id}/email", headers={"Authorization": f"Bearer {t}"}).status_code == 200

    (mensaje,) = servidor_smtp.mensajes
    assert _canjear(client, _token_del_correo(mensaje)).status_code == 200


def test_ca7_el_envio_automatico_envia_un_enlace_que_funciona(mundo, client, servidor_smtp):
    d = mundo.dossier()
    with Session(mundo.engine) as db:
        assert deliver_dossier_after_generation(db, dossier_id=d.id, recipient=mundo.yo.email)

    (mensaje,) = servidor_smtp.mensajes
    assert _canjear(client, _token_del_correo(mensaje)).status_code == 200


def test_ca7_la_reunion_envia_un_enlace_por_dossier(mundo, client, servidor_smtp):
    ids = [mundo.dossier("Acme SA").id, mundo.dossier("Ana Prueba").id]
    with Session(mundo.engine) as db:
        assert deliver_meeting_dossiers(db, dossier_ids=ids, recipient=mundo.yo.email, meeting_title="Demo",
                                        language="es", calendar_event_id=None)

    (mensaje,) = servidor_smtp.mensajes
    tokens = set(_TOKEN.findall(mensaje.get_body(("html",)).get_content()))
    assert len(tokens) == 2
    assert {_canjear(client, t).json()["subject_name"] for t in tokens} == {"Acme SA", "Ana Prueba"}


def test_ca8_si_el_envio_falla_no_queda_ningun_enlace(mundo, servidor_smtp):
    servidor_smtp.rechazar = True
    d = mundo.dossier()
    with Session(mundo.engine) as db:
        assert not deliver_dossier_after_generation(db, dossier_id=d.id, recipient=mundo.yo.email)
    assert mundo.enlaces() == []


def _en_espera(mundo, d):
    with Session(mundo.engine) as db:
        encolar_reintento(db, kind="persona", dossiers=[db.get(Dossier, d.id)],
                          error=EmailDeliveryError("x", transitorio=True))
        db.commit()


DESPUES = timedelta(minutes=11)


def test_ca8_un_reintento_fallido_no_deja_enlaces(mundo, servidor_smtp):
    servidor_smtp.rechazar = True
    _en_espera(mundo, mundo.dossier())

    with Session(mundo.engine) as db:
        assert procesar_reintentos(db, now=datetime.now(UTC) + DESPUES)["agotados"] == 1
    assert mundo.enlaces() == []


def test_ca8_un_reintento_exitoso_deja_su_enlace(mundo, client, servidor_smtp):
    _en_espera(mundo, mundo.dossier())

    with Session(mundo.engine) as db:
        assert procesar_reintentos(db, now=datetime.now(UTC) + DESPUES)["enviados"] == 1
    assert len(mundo.enlaces()) == 1
    with Session(mundo.engine) as s:
        assert s.scalars(select(DossierEmailRetry)).all() == []
    (mensaje,) = servidor_smtp.mensajes
    assert _canjear(client, _token_del_correo(mensaje)).status_code == 200


# --------------------------------------------------------------------------
# CA14 · migración y retención
# --------------------------------------------------------------------------


def test_ca14_la_retencion_borra_los_enlaces_con_el_dossier(mundo):
    d = mundo.dossier()
    mundo.enlace(d)
    mundo.s.execute(text("UPDATE dossiers SET created_at = :c WHERE id = :i"),
                    {"c": datetime.now(UTC) - timedelta(hours=25), "i": d.id})
    mundo.s.commit()

    with Session(mundo.engine) as db:
        assert purge_expired_dossiers(db).verificado is True
    assert mundo.enlaces() == []


def test_ca14_la_migracion_crea_la_tabla_como_el_orm_y_el_downgrade_la_quita(pg_vacia, alembic_cfg):
    command.upgrade(alembic_cfg, "head")
    columnas = {c["name"] for c in inspect(pg_vacia).get_columns("dossier_access_links")}
    assert columnas == set(DossierAccessLink.__table__.columns.keys())

    command.downgrade(alembic_cfg, REVISION_ANTERIOR)
    assert "dossier_access_links" not in inspect(pg_vacia).get_table_names()
