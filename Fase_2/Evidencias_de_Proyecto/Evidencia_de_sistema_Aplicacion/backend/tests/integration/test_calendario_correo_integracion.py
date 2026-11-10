"""S6.3, integración: envío automático de los dossiers de una reunión y su retención.

Especificación: ``specs/proposals/S6.3-calendario-correo.md`` (CA1, CA3–CA7, CA10–CA12).
Postgres real (``pg_vacia``) y el SMTP de loopback (``servidor_smtp``). La generación con IA
se simula: lo que se prueba es lo que pasa después de guardar los dossiers.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from alembic import command
from dossier.db.models import (
    AuditLog,
    CalendarEvent,
    CalendarIntegration,
    Dossier,
    Organization,
    OrgMembership,
    User,
)
from dossier.services import calendar_automation as automatizacion
from dossier.services.dossier_email import deliver_meeting_dossiers
from dossier.services.dossier_retention_worker import purge_expired_dossiers

TITULO = "Reunión comercial Acme"


class Mundo:
    def __init__(self, engine, auto_send=True):
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
        self.integracion = CalendarIntegration(
            user_id=self.yo.id, organization_id=self.org.id, provider="google",
            provider_email=self.yo.email, access_token_encrypted="t", auto_send_email=auto_send,
        )
        self.s.add(self.integracion)
        self.s.commit()

    def evento(self, *, empieza_en: timedelta, titulo: str | None = TITULO, estado="scheduled") -> CalendarEvent:
        ahora = datetime.now(UTC)
        ev = CalendarEvent(
            calendar_integration_id=self.integracion.id,
            organization_id=self.org.id,
            user_id=self.yo.id,
            external_event_id=f"ev-{uuid.uuid4().hex[:8]}",
            title=titulo,
            starts_at=ahora + empieza_en,
            dossier_scheduled_at=ahora - timedelta(minutes=1),
            processing_status=estado,
        )
        self.s.add(ev)
        self.s.commit()
        return ev

    def dossier(self, nombre, *, evento=None, status="complete", horas=0.0) -> uuid.UUID:
        d = Dossier(
            organization_id=self.org.id,
            requested_by_user_id=self.yo.id,
            subject_name=nombre,
            status=status,
            calendar_event_id=evento.id if evento else None,
            dossier_data={"format": "markdown", "body": f"## {nombre}\n\nInforme.", "billing": "none",
                          "output_language": "es"},
        )
        self.s.add(d)
        self.s.commit()
        if horas:
            self.s.execute(text("UPDATE dossiers SET created_at = :c WHERE id = :i"),
                           {"c": datetime.now(UTC) - timedelta(hours=horas), "i": d.id})
            self.s.commit()
        return d.id

    def leer(self, dossier_id) -> Dossier | None:
        self.s.expire_all()
        return self.s.get(Dossier, dossier_id)

    def envios(self) -> list[AuditLog]:
        with Session(self.engine) as s:
            return [f for f in s.scalars(select(AuditLog)).all() if f.action.startswith("EMAIL")]


@pytest.fixture
def mundo(pg_vacia, alembic_cfg, monkeypatch):
    command.upgrade(alembic_cfg, "head")
    monkeypatch.delenv("DOSSIER_RETENTION_HOURS", raising=False)
    m = Mundo(pg_vacia)
    yield m
    m.s.close()


def _adjuntos(mensaje) -> list:
    return [a for a in mensaje.iter_attachments() if a.get_content_type() == "application/pdf"]


# --------------------------------------------------------------------------
# Envío de la reunión
# --------------------------------------------------------------------------


def test_ca1_ca3_un_correo_con_los_tres_dossiers_marcados_y_auditados(mundo, servidor_smtp):
    ev = mundo.evento(empieza_en=timedelta(minutes=20))
    ids = [mundo.dossier(n, evento=ev) for n in ("Acme SA", "Ana Prueba", "Luis Prueba")]

    with Session(mundo.engine) as db:
        enviado = deliver_meeting_dossiers(db, dossier_ids=ids, recipient=mundo.yo.email,
                                           meeting_title=TITULO, language="es", calendar_event_id=ev.id)

    assert enviado is True
    (mensaje,) = servidor_smtp.mensajes
    assert mensaje["Subject"] == f"Dossiers: {TITULO}"
    assert len(_adjuntos(mensaje)) == 3
    for i in ids:
        d = mundo.leer(i)
        assert d.email_sent is True
        assert d.email_recipients == [mundo.yo.email]
    envios = mundo.envios()
    assert sorted(f.resource_id for f in envios) == sorted(ids)
    assert all(f.action == "EMAIL dossier_auto" and f.success for f in envios)
    assert all(f.request_data["calendar_event_id"] == str(ev.id) for f in envios)
    assert all(f.request_data["origen"] == "calendario" for f in envios)


def test_ca6_un_fallo_smtp_no_marca_y_queda_auditado(mundo, servidor_smtp):
    servidor_smtp.rechazar = True
    ev = mundo.evento(empieza_en=timedelta(minutes=20))
    ids = [mundo.dossier(n, evento=ev) for n in ("Acme SA", "Ana Prueba")]

    with Session(mundo.engine) as db:
        enviado = deliver_meeting_dossiers(db, dossier_ids=ids, recipient=mundo.yo.email,
                                           meeting_title=TITULO, language="es", calendar_event_id=ev.id)

    assert enviado is False
    assert all(mundo.leer(i).email_sent is not True for i in ids)
    envios = mundo.envios()
    assert len(envios) == 2
    assert all(f.success is False and f.error_message == "EmailDeliveryError" for f in envios)


def test_ca7_solo_van_los_completos_y_sin_completos_no_hay_correo(mundo, servidor_smtp):
    ev = mundo.evento(empieza_en=timedelta(minutes=20))
    completo = mundo.dossier("Acme SA", evento=ev)
    fallido = mundo.dossier("Ana Prueba", evento=ev, status="failed")

    with Session(mundo.engine) as db:
        assert deliver_meeting_dossiers(db, dossier_ids=[completo, fallido], recipient=mundo.yo.email,
                                        meeting_title=TITULO, language="es", calendar_event_id=ev.id)
    (mensaje,) = servidor_smtp.mensajes
    assert len(_adjuntos(mensaje)) == 1

    with Session(mundo.engine) as db:
        assert not deliver_meeting_dossiers(db, dossier_ids=[fallido], recipient=mundo.yo.email,
                                            meeting_title=TITULO, language="es", calendar_event_id=ev.id)
    assert len(servidor_smtp.mensajes) == 1


# --------------------------------------------------------------------------
# La automatización completa, con la generación simulada
# --------------------------------------------------------------------------


@pytest.fixture
def generacion_simulada(mundo, monkeypatch):
    """La IA no corre: «persistir» crea tres dossiers completos ligados al evento."""
    monkeypatch.setattr(automatizacion, "_reunion_for_processing",
                        lambda integracion, db, ev: {"id": ev.external_event_id, "tema": ev.title,
                                                     "participantes": "ana@cliente.example"})
    monkeypatch.setattr(automatizacion, "calendar_event_passes_filters", lambda *_a, **_k: (True, None))
    monkeypatch.setattr(automatizacion, "generate_dossiers_from_calendar_event", lambda *_a, **_k: {})

    def _persistir(db, *, calendar_event_id, result, **_k):
        ev = db.get(CalendarEvent, calendar_event_id)
        ids = [mundo.dossier(n, evento=ev) for n in ("Acme SA", "Ana Prueba", "Luis Prueba")]
        result["saved_dossiers"] = {"corporate": {"id": str(ids[0])},
                                    "persons": [{"id": str(i)} for i in ids[1:]]}
        return result["saved_dossiers"]

    monkeypatch.setattr(automatizacion, "persist_calendar_dossiers", _persistir)
    return SimpleNamespace()


def _correr_automatizacion(mundo):
    with Session(mundo.engine) as db:
        automatizacion.process_due_calendar_events(db)


def test_ca1_la_automatizacion_envia_un_correo_por_reunion(mundo, servidor_smtp, generacion_simulada):
    ev = mundo.evento(empieza_en=timedelta(minutes=20))
    _correr_automatizacion(mundo)

    mundo.s.expire_all()
    assert mundo.s.get(CalendarEvent, ev.id).processing_status == "completed"
    (mensaje,) = servidor_smtp.mensajes
    assert mensaje["Subject"] == f"Dossiers: {TITULO}"
    assert len(_adjuntos(mensaje)) == 3


def test_ca4_con_auto_send_email_apagado_no_se_envia(mundo, servidor_smtp, generacion_simulada):
    mundo.integracion.auto_send_email = False
    mundo.s.commit()
    ev = mundo.evento(empieza_en=timedelta(minutes=20))
    _correr_automatizacion(mundo)

    mundo.s.expire_all()
    assert mundo.s.get(CalendarEvent, ev.id).processing_status == "completed"
    assert servidor_smtp.conexiones == 0


def test_ca5_sin_smtp_configurado_no_se_intenta(mundo, servidor_smtp, generacion_simulada, monkeypatch):
    monkeypatch.setenv("SMTP_SECURITY", "starttls")  # exige usuario y contraseña, que no hay
    ev = mundo.evento(empieza_en=timedelta(minutes=20))
    _correr_automatizacion(mundo)

    mundo.s.expire_all()
    assert mundo.s.get(CalendarEvent, ev.id).processing_status == "completed"
    assert servidor_smtp.conexiones == 0


def test_ca6_un_fallo_smtp_no_cambia_el_estado_del_evento(mundo, servidor_smtp, generacion_simulada):
    servidor_smtp.rechazar = True
    ev = mundo.evento(empieza_en=timedelta(minutes=20))
    _correr_automatizacion(mundo)

    mundo.s.expire_all()
    assert mundo.s.get(CalendarEvent, ev.id).processing_status == "completed"
    assert len(mundo.envios()) == 3


# --------------------------------------------------------------------------
# Retención de los dossiers de una reunión
# --------------------------------------------------------------------------


def test_ca10_un_dossier_de_una_reunion_reciente_no_se_borra(mundo):
    ev = mundo.evento(empieza_en=-timedelta(hours=2), estado="completed")
    d = mundo.dossier("Acme SA", evento=ev, horas=26)  # creado 1 día antes de la reunión

    with Session(mundo.engine) as db:
        purge_expired_dossiers(db)
    assert mundo.leer(d) is not None


def test_ca11_un_dossier_de_una_reunion_de_hace_mas_de_24_horas_se_borra(mundo):
    ev = mundo.evento(empieza_en=-timedelta(hours=25), estado="completed")
    d = mundo.dossier("Acme SA", evento=ev, horas=26)

    with Session(mundo.engine) as db:
        assert purge_expired_dossiers(db).dossiers_borrados == 1
    assert mundo.leer(d) is None


def test_ca12_un_dossier_sin_evento_vence_desde_su_creacion(mundo):
    viejo = mundo.dossier("Acme SA", horas=25)
    nuevo = mundo.dossier("Ana Prueba", horas=23)

    with Session(mundo.engine) as db:
        purge_expired_dossiers(db)
    assert mundo.leer(viejo) is None
    assert mundo.leer(nuevo) is not None


def test_un_dossier_creado_despues_de_la_reunion_dura_sus_24_horas(mundo):
    ev = mundo.evento(empieza_en=-timedelta(hours=30), estado="completed")
    d = mundo.dossier("Acme SA", evento=ev, horas=2)

    with Session(mundo.engine) as db:
        purge_expired_dossiers(db)
    assert mundo.leer(d) is not None
