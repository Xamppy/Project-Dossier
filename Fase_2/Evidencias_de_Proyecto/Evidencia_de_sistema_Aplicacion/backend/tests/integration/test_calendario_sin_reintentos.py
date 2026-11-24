"""Calendario, integración: la sincronización no vuelve a generar lo que ya falló ni lo que el
usuario borró.

Un evento ``failed`` solo se reintenta si cambió la reunión (asunto, descripción, asistentes u
horario). Un dossier borrado por el usuario no se regenera. Postgres real (``pg_vacia``); el
calendario y la generación con IA son dobles.
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
    CalendarEvent,
    CalendarIntegration,
    Dossier,
    Organization,
    OrgMembership,
    User,
)
from dossier.services import calendar_automation as auto
from dossier.services import calendar_event_dossiers as eventos
from dossier.services import google_calendar_api as google
from dossier.services.dossier_deletion_service import (
    delete_dossier_record,
    finalize_dossier_deletions,
)
from dossier.services.dossier_retention_worker import purge_expired_dossiers

GENERAR_REAL = eventos.generate_dossiers_from_calendar_event
PERSISTIR_REAL = eventos.persist_calendar_dossiers

YO = "yo@mi-empresa.example"
ANA = "ana@acme.example"
BETO = "beto@acme.example"
DESCRIPCION = "Empresa: Acme\nContacto: Ana Prueba"


def evento(
    *correos: str,
    asunto: str = "Avance del proyecto",
    descripcion: str = DESCRIPCION,
    en_minutos: int = 10,
    dura_minutos: int = 60,
    ubicacion: str = "",
) -> dict:
    """Evento normalizado. El inicio se trunca al minuto: dos lecturas dan el mismo horario."""
    inicio = AHORA + timedelta(minutes=en_minutos)
    return google.normalizar_evento_google({
        "id": "ev-1",
        "summary": asunto,
        "description": descripcion,
        "location": ubicacion,
        "start": {"dateTime": inicio.isoformat()},
        "end": {"dateTime": (inicio + timedelta(minutes=dura_minutos)).isoformat()},
        "organizer": {"email": YO, "self": True},
        "attendees": [{"email": c} for c in (YO, *(correos or (ANA,)))],
    })


AHORA = datetime.now(UTC)


@pytest.fixture
def mundo(pg_vacia, alembic_cfg, monkeypatch):
    global AHORA
    AHORA = datetime.now(UTC).replace(microsecond=0)
    command.upgrade(alembic_cfg, "head")
    m = SimpleNamespace(engine=pg_vacia, reunion=evento(), generadas=[], falla=True)
    with Session(pg_vacia) as s:
        org = Organization(name="Org", slug=f"org-{uuid.uuid4().hex[:6]}", plan="pro")
        user = User(email=YO)
        s.add_all([org, user])
        s.flush()
        s.add(OrgMembership(organization_id=org.id, user_id=user.id, role="user", is_primary_org=True))
        s.add(CalendarIntegration(
            user_id=user.id, organization_id=org.id, provider="google", provider_email=YO,
            access_token_encrypted="t", advance_minutes=20, auto_send_email=False,
        ))
        s.commit()
        m.org_id, m.user_id = org.id, user.id

    def generar(reunion, **_k):
        m.generadas.append(reunion)
        if m.falla:
            raise RuntimeError("proveedor caído")
        return {}

    def persistir(db, *, calendar_event_id, result, **_k):
        d = Dossier(
            organization_id=m.org_id, requested_by_user_id=m.user_id, subject_name="Ana Prueba",
            status="complete", calendar_event_id=calendar_event_id,
            dossier_data={"format": "markdown", "body": "## Ana", "billing": "none"},
        )
        db.add(d)
        db.commit()
        result["saved_dossiers"] = {"person": {"id": str(d.id)}}

    monkeypatch.setattr(auto, "_list_upcoming_reuniones", lambda integ, db: [dict(m.reunion)])
    monkeypatch.setattr(auto, "_fetch_reunion", lambda integ, db, ext: dict(m.reunion))
    monkeypatch.setattr(auto, "generate_dossiers_from_calendar_event", generar)
    monkeypatch.setattr(auto, "persist_calendar_dossiers", persistir)
    return m


def tick(m, veces: int = 1) -> None:
    for _ in range(veces):
        with Session(m.engine) as db:
            auto.run_calendar_automation_tick(db)


def fila(m) -> CalendarEvent:
    with Session(m.engine) as db:
        return db.scalars(select(CalendarEvent)).one()


def actualizar(m, sql: str, **valores) -> None:
    with m.engine.begin() as conn:
        conn.execute(text(sql), valores)


def borrar_dossier(m) -> None:
    """Como la API: borra el dossier y marca el evento en la misma transacción."""
    with Session(m.engine) as db:
        d = db.scalars(select(Dossier)).one()
        evento_id = delete_dossier_record(db, d)
        db.flush()
        finalize_dossier_deletions(db, {evento_id})
        db.commit()


# ── Evento fallido ───────────────────────────────────────────────────────────


def test_un_evento_fallido_no_se_vuelve_a_generar_en_cada_sincronizacion(mundo):
    tick(mundo, veces=4)
    assert len(mundo.generadas) == 1
    ev = fila(mundo)
    assert ev.processing_status == "failed"
    assert ev.skip_reason == "proveedor caído"  # el motivo no se pierde


def test_sin_dossier_valido_tampoco_se_reintenta(mundo, monkeypatch):
    mundo.falla = False
    monkeypatch.setattr(auto, "persist_calendar_dossiers", lambda db, **_k: {})
    tick(mundo, veces=4)
    assert len(mundo.generadas) == 1
    assert fila(mundo).processing_status == "failed"


@pytest.mark.parametrize(
    "cambio",
    [
        {"asunto": "Reunión con Acme"},
        {"descripcion": "Empresa: Acme\nContacto: Ana Prueba Soto"},
        {"en_minutos": 12},
        {"dura_minutos": 30},
    ],
    ids=["asunto", "descripcion", "inicio", "fin"],
)
def test_un_evento_fallido_se_reintenta_una_vez_por_cambio(mundo, cambio):
    tick(mundo, veces=2)
    mundo.reunion = evento(**cambio)
    tick(mundo, veces=3)
    assert len(mundo.generadas) == 2
    assert fila(mundo).processing_status == "failed"


def test_un_cambio_de_asistentes_reintenta_el_evento_fallido(mundo):
    tick(mundo, veces=2)
    mundo.reunion = evento(BETO)
    mundo.falla = False
    tick(mundo, veces=3)
    assert len(mundo.generadas) == 2
    ev = fila(mundo)
    assert ev.processing_status == "completed"
    assert ev.skip_reason is None


def test_lo_que_no_afecta_al_dossier_no_reintenta(mundo):
    """Otra sala, el mismo horario en otra zona o los asistentes en otro orden no son un cambio."""
    mundo.reunion = evento(ANA, descripcion="Contacto: Ana Prueba")
    tick(mundo)
    otra = evento(ANA, descripcion="Contacto: Ana Prueba", ubicacion="Sala 2")
    inicio = datetime.fromisoformat(otra["inicio"])
    otra["inicio"] = inicio.astimezone(tz=datetime.strptime("-0300", "%z").tzinfo).isoformat()
    otra["asistentes"] = list(reversed(otra["asistentes"]))
    mundo.reunion = otra
    tick(mundo, veces=2)
    assert len(mundo.generadas) == 1
    assert fila(mundo).meeting_url == "Sala 2"  # los datos del evento sí se actualizan


def test_un_evento_fallido_reprogramado_a_futuro_espera_su_nueva_hora(mundo):
    tick(mundo)
    mundo.reunion = evento(en_minutos=24 * 60)
    tick(mundo, veces=2)
    ev = fila(mundo)
    assert ev.processing_status == "scheduled"
    assert ev.skip_reason is None
    assert ev.dossier_scheduled_at == ev.starts_at - timedelta(minutes=20)
    assert len(mundo.generadas) == 1


def test_un_fallo_antiguo_con_varias_personas_queda_omitido_como_manda_ux_cal_03(mundo):
    """Fila ``failed`` anterior a UX-CAL-03: la reunión no cambió, pero ya no es un error."""
    mundo.reunion = evento(ANA, BETO, descripcion="")
    tick(mundo)
    actualizar(mundo, "UPDATE calendar_events SET processing_status = 'failed', skip_reason = 'No se detectó'")
    tick(mundo, veces=2)
    ev = fila(mundo)
    assert ev.processing_status == "skipped"
    assert "varias personas" in ev.skip_reason
    assert mundo.generadas == []


def test_un_evento_fallido_que_suma_gente_y_vuelve_a_una_persona_se_reintenta(mundo):
    tick(mundo)
    mundo.reunion = evento(ANA, BETO)
    tick(mundo, veces=2)
    assert fila(mundo).processing_status == "skipped"
    mundo.falla = False
    mundo.reunion = evento(ANA)
    tick(mundo)
    assert fila(mundo).processing_status == "completed"
    assert len(mundo.generadas) == 2


def test_un_fallo_que_deja_de_pasar_los_filtros_no_vuelve_a_generarse_al_pasarlos(mundo):
    tick(mundo)
    buena = mundo.reunion
    mundo.reunion = {**buena, "todo_el_dia": True}
    tick(mundo, veces=2)
    mundo.reunion = buena
    tick(mundo, veces=2)
    assert len(mundo.generadas) == 1


# ── Con la generación y el guardado reales ───────────────────────────────────


@pytest.fixture
def llamadas(mundo, monkeypatch):
    """Solo se simulan las dos consultas con costo. ``llamadas.falla`` nombra las que caen."""
    ll = SimpleNamespace(empresa=0, persona=0, falla={"empresa"})

    def empresa(**_k):
        ll.empresa += 1
        if "empresa" in ll.falla:
            raise RuntimeError("IA caída")
        return "# Acme\n\nInforme de prueba.", False, None, None

    def persona(**_k):
        ll.persona += 1
        if "persona" in ll.falla:
            raise RuntimeError("IA caída")
        return {"llm_analysis_markdown": "# Ana\n\nInforme de prueba."}, False, None

    monkeypatch.setattr(auto, "generate_dossiers_from_calendar_event", GENERAR_REAL)
    monkeypatch.setattr(auto, "persist_calendar_dossiers", PERSISTIR_REAL)
    monkeypatch.setattr(eventos, "resolve_corporate_brief", lambda q: (q, "dual"))
    monkeypatch.setattr(eventos, "_corporate_md_from_cache_or_langgraph", empresa)
    monkeypatch.setattr(eventos, "_person_research_from_cache_or_pipeline", persona)
    return ll


def dossiers(m) -> list[tuple[str, str]]:
    with Session(m.engine) as db:
        return sorted((d.subject_name, d.status) for d in db.scalars(select(Dossier)).all())


def test_si_falla_el_dossier_de_empresa_queda_fallido_y_no_se_repite(mundo, llamadas):
    mundo.reunion = evento(descripcion="Empresa: Acme")
    tick(mundo, veces=5)
    assert llamadas.empresa == 1
    ev = fila(mundo)
    assert ev.processing_status == "failed"
    assert "Corporativo" in ev.skip_reason
    assert dossiers(mundo) == []


def test_sin_empresa_ni_contacto_queda_fallido_y_no_se_repite(mundo, llamadas, monkeypatch):
    intentos = []
    monkeypatch.setattr(
        auto, "generate_dossiers_from_calendar_event",
        lambda *a, **k: intentos.append(1) or GENERAR_REAL(*a, **k),
    )
    mundo.reunion = evento(asunto="Reunión", descripcion="Sin datos")
    tick(mundo, veces=5)
    assert len(intentos) == 1
    assert fila(mundo).processing_status == "failed"


def test_el_fallo_de_empresa_se_reintenta_una_vez_al_editar_la_reunion(mundo, llamadas):
    mundo.reunion = evento(descripcion="Empresa: Acme")
    tick(mundo, veces=2)
    llamadas.falla = set()
    mundo.reunion = evento(descripcion="Empresa: Acme SpA")
    tick(mundo, veces=3)
    assert llamadas.empresa == 2
    assert fila(mundo).processing_status == "completed"
    assert [estado for _, estado in dossiers(mundo)] == ["complete"]


def test_si_falla_la_empresa_pero_sale_la_persona_queda_completado(mundo, llamadas):
    tick(mundo, veces=4)
    assert (llamadas.empresa, llamadas.persona) == (1, 1)
    assert fila(mundo).processing_status == "completed"
    assert dossiers(mundo) == [("Ana Prueba", "complete")]


def test_un_dossier_de_persona_fallido_queda_guardado_y_no_se_repite(mundo, llamadas):
    llamadas.falla = {"persona"}
    mundo.reunion = evento(descripcion="Contacto: Ana Prueba")
    tick(mundo, veces=4)
    assert llamadas.persona == 1
    assert dossiers(mundo) == [("Ana Prueba", "failed")]


# ── Dossier borrado por el usuario ───────────────────────────────────────────


@pytest.fixture
def borrado(mundo):
    mundo.falla = False
    tick(mundo)
    assert fila(mundo).processing_status == "completed"
    borrar_dossier(mundo)
    mundo.generadas.clear()
    return mundo


def test_un_dossier_borrado_por_el_usuario_no_se_regenera(borrado):
    tick(borrado, veces=3)
    assert borrado.generadas == []
    ev = fila(borrado)
    assert ev.processing_status == "skipped"
    assert ev.skip_reason == auto.MOTIVO_DOSSIER_ELIMINADO


@pytest.mark.parametrize(
    "cambio",
    [{"descripcion": "Contacto: Ana Prueba Soto"}, {"en_minutos": 15}, {"asunto": "Otro asunto"}],
    ids=["descripcion", "horario", "asunto"],
)
def test_un_dossier_borrado_no_se_regenera_aunque_cambie_la_reunion(borrado, cambio):
    borrado.reunion = evento(**cambio)
    tick(borrado, veces=3)
    assert borrado.generadas == []
    assert fila(borrado).skip_reason == auto.MOTIVO_DOSSIER_ELIMINADO


def test_un_dossier_borrado_no_se_regenera_por_pasar_por_varias_personas(borrado):
    borrado.reunion = evento(ANA, BETO)
    tick(borrado, veces=2)
    borrado.reunion = evento(ANA)
    tick(borrado, veces=2)
    assert borrado.generadas == []
    assert fila(borrado).skip_reason == auto.MOTIVO_DOSSIER_ELIMINADO


def test_un_dossier_borrado_no_se_regenera_por_pasar_por_el_plan_free(borrado):
    for plan in ("free", "pro"):
        actualizar(borrado, "UPDATE organizations SET plan = :p", p=plan)
        tick(borrado, veces=2)
    assert borrado.generadas == []
    assert fila(borrado).skip_reason == auto.MOTIVO_DOSSIER_ELIMINADO


def test_un_dossier_borrado_antes_de_este_arreglo_tampoco_se_regenera(borrado):
    """El texto ya guardado trae «?» en vez de tildes; hay que reconocerlo igual."""
    actualizar(
        borrado,
        "UPDATE calendar_events SET skip_reason = "
        "'Dossier eliminado por el usuario; no se regenerar? autom?ticamente.'",
    )
    tick(borrado, veces=2)
    assert borrado.generadas == []


def test_lo_que_borra_la_retencion_no_cuenta_como_borrado_por_el_usuario(mundo):
    """Reunión pasada cuyo dossier venció; al moverla a una fecha futura se genera otra vez."""
    mundo.falla = False
    tick(mundo)
    actualizar(mundo, "UPDATE calendar_events SET starts_at = now() - interval '30 hours'")
    actualizar(mundo, "UPDATE dossiers SET created_at = now() - interval '31 hours'")
    with Session(mundo.engine) as db:
        assert purge_expired_dossiers(db).dossiers_borrados == 1
    ev = fila(mundo)
    assert ev.processing_status == "skipped"
    assert "usuario" not in ev.skip_reason

    mundo.reunion = evento(en_minutos=15)
    tick(mundo, veces=2)
    assert fila(mundo).processing_status == "completed"
    assert len(mundo.generadas) == 2


# ── Lo que debe seguir igual ─────────────────────────────────────────────────


def test_un_evento_programado_se_reprograma_al_cambiar_el_horario(mundo):
    mundo.reunion = evento(en_minutos=120)
    tick(mundo)
    mundo.reunion = evento(en_minutos=180)
    tick(mundo)
    ev = fila(mundo)
    assert ev.processing_status == "scheduled"
    assert ev.dossier_scheduled_at == AHORA + timedelta(minutes=160)
    assert mundo.generadas == []


def test_un_evento_omitido_por_los_filtros_vuelve_a_programarse_al_pasarlos(mundo):
    mundo.reunion = evento(en_minutos=120)
    tick(mundo)
    mundo.reunion = {**mundo.reunion, "todo_el_dia": True}
    tick(mundo)
    assert fila(mundo).processing_status == "skipped"
    mundo.reunion = evento(en_minutos=120)
    tick(mundo)
    assert fila(mundo).processing_status == "scheduled"
