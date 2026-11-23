"""UX-CAL-03, integración: la automatización no genera reuniones con varias personas (CA1, CA2)
y la generación manual exige elegir una (CA5, CA6).

Postgres real (``pg_vacia``); Google y la generación con IA son dobles.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from alembic import command
from dossier.api.auth_routes import get_db_if_configured
from dossier.db.models import (
    CalendarEvent,
    CalendarIntegration,
    Dossier,
    DossierGenerationJob,
    Organization,
    OrgMembership,
    User,
)
from dossier.services import calendar_automation as auto
from dossier.services import calendar_event_dossiers as eventos
from dossier.services import dossier_generation_job_service as servicio
from dossier.services import google_calendar_api as google

YO = "yo@mi-empresa.example"


def evento_google(*correos: str, descripcion: str = "", ident: str = "ev-1") -> dict:
    inicio = datetime.now(UTC) + timedelta(minutes=10)
    return google.normalizar_evento_google({
        "id": ident,
        "summary": "Avance del proyecto",
        "description": descripcion,
        "start": {"dateTime": inicio.isoformat()},
        "end": {"dateTime": (inicio + timedelta(hours=1)).isoformat()},
        "organizer": {"email": YO, "self": True},
        "attendees": [{"email": c} for c in (YO, *correos)],
    })


VARIAS = ("carla.diaz@acme.example", "max@acme.example")


@pytest.fixture
def mundo(pg_vacia, alembic_cfg, monkeypatch):
    command.upgrade(alembic_cfg, "head")
    m = SimpleNamespace(engine=pg_vacia, reunion=evento_google(*VARIAS), generadas=[])
    with Session(pg_vacia) as s:
        org = Organization(name="Org", slug=f"org-{uuid.uuid4().hex[:6]}", plan="pro", credits_balance=100)
        user = User(email=YO)
        s.add_all([org, user])
        s.flush()
        s.add(OrgMembership(organization_id=org.id, user_id=user.id, role="user", is_primary_org=True))
        integ = CalendarIntegration(
            user_id=user.id, organization_id=org.id, provider="google", provider_email=YO,
            access_token_encrypted="t", advance_minutes=20, auto_send_email=False,
        )
        s.add(integ)
        s.commit()
        m.org_id, m.user_id, m.integ_id = org.id, user.id, integ.id

    def generar(reunion, **_k):
        m.generadas.append(reunion)
        return {}

    monkeypatch.setattr(auto, "_list_upcoming_reuniones", lambda integ, db: [m.reunion])
    monkeypatch.setattr(auto, "_fetch_reunion", lambda integ, db, ext: m.reunion)
    monkeypatch.setattr(auto, "generate_dossiers_from_calendar_event", generar)
    monkeypatch.setattr(
        auto, "persist_calendar_dossiers",
        lambda db, *, result, **_k: result.update(saved_dossiers={"person": {"id": str(uuid.uuid4())}}),
    )
    return m


def tick(m):
    with Session(m.engine) as db:
        return auto.run_calendar_automation_tick(db)


def fila(m) -> CalendarEvent:
    with Session(m.engine) as db:
        return db.scalars(select(CalendarEvent)).one()


# ── Automatización ───────────────────────────────────────────────────────────


def test_ca1_con_varias_personas_no_se_genera_ni_queda_como_error(mundo):
    for _ in range(3):  # el sync corre cada minuto: no debe volver a programarla
        tick(mundo)
        ev = fila(mundo)
        assert ev.processing_status == "skipped"
        assert "varias personas" in ev.skip_reason
        assert ev.dossier_scheduled_at is None
    assert mundo.generadas == []


def test_ca1_varios_contactos_declarados_tampoco_se_generan_solos(mundo):
    mundo.reunion = evento_google(descripcion="Empresa: Acme\nContacto 1: Ana Prueba\nContacto 2: Beto Ruiz")
    tick(mundo)
    assert fila(mundo).processing_status == "skipped"
    assert mundo.generadas == []


def test_una_sola_persona_se_genera_como_siempre(mundo):
    mundo.reunion = evento_google("ana@acme.example", descripcion="Empresa: Acme\nContacto: Ana Prueba")
    tick(mundo)
    assert fila(mundo).processing_status == "completed"
    assert len(mundo.generadas) == 1


def test_ca1_si_se_suman_personas_despues_de_programarla_no_se_genera(mundo, monkeypatch):
    """El evento se programó con una persona; al leerlo otra vez antes de generar ya tiene dos."""
    una = evento_google("ana@acme.example", descripcion="Contacto: Ana Prueba")
    varias = mundo.reunion
    mundo.reunion = una
    monkeypatch.setattr(auto, "_fetch_reunion", lambda integ, db, ext: varias)
    tick(mundo)
    assert fila(mundo).processing_status == "skipped"
    assert mundo.generadas == []


def test_ca2_al_quedar_una_sola_persona_vuelve_a_programarse(mundo):
    tick(mundo)
    assert fila(mundo).processing_status == "skipped"
    mundo.reunion = evento_google("ana@acme.example", descripcion="Contacto: Ana Prueba")
    tick(mundo)
    assert fila(mundo).processing_status == "completed"


def test_un_dossier_ya_generado_no_se_toca_si_luego_se_suma_gente(mundo):
    mundo.reunion = evento_google("ana@acme.example", descripcion="Contacto: Ana Prueba")
    with Session(mundo.engine) as db:
        auto.sync_calendar_events_for_integration(db, db.get(CalendarIntegration, mundo.integ_id))
        ev = db.scalars(select(CalendarEvent)).one()
        ev.processing_status = "completed"
        db.commit()
        mundo.reunion = evento_google(*VARIAS)
        auto.sync_calendar_events_for_integration(db, db.get(CalendarIntegration, mundo.integ_id))
    assert fila(mundo).processing_status == "completed"


# ── Generación manual ────────────────────────────────────────────────────────


@pytest.fixture
def api(mundo, monkeypatch):
    import sys

    from fastapi.testclient import TestClient

    from dossier.api.app import app
    from dossier.security.jwt_tokens import create_access_token

    modulo = sys.modules["dossier.api.app"]

    def _db():
        with Session(mundo.engine) as s:
            yield s

    app.dependency_overrides[get_db_if_configured] = _db
    monkeypatch.setattr(modulo, "get_google_calendar_access_token_for_user", lambda db, uid: "tok")
    monkeypatch.setattr(modulo, "obtener_reunion_google_por_id", lambda tok, eid: mundo.reunion)
    monkeypatch.setattr(modulo, "listar_reuniones_google", lambda tok, **_k: [mundo.reunion])
    tok = create_access_token(
        user_id=str(mundo.user_id), email=YO, organization_id=str(mundo.org_id), role="user"
    )
    yield TestClient(app, headers={"Authorization": f"Bearer {tok}"}, raise_server_exceptions=False)
    app.dependency_overrides.pop(get_db_if_configured, None)


def pedir(api, **cuerpo):
    return api.post("/calendario/generar-dossiers-google", json={"event_id": "ev-1", **cuerpo})


def trabajos(m) -> list[DossierGenerationJob]:
    with Session(m.engine) as db:
        return list(db.scalars(select(DossierGenerationJob)).all())


def test_sin_elegir_responde_422_con_las_personas_y_no_crea_trabajo(api, mundo):
    r = pedir(api)
    assert r.status_code == 422
    detalle = r.json()["detail"]
    assert detalle["code"] == "CALENDAR_PERSON_REQUIRED"
    assert [p["id"] for p in detalle["personas"]] == list(VARIAS)
    assert trabajos(mundo) == []


def test_una_persona_ajena_a_la_reunion_responde_422_y_no_crea_trabajo(api, mundo):
    r = pedir(api, persona_id="intrusa@acme.example")
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "CALENDAR_PERSON_NOT_FOUND"
    assert trabajos(mundo) == []


def test_ca5_ca6_el_trabajo_genera_solo_la_persona_elegida(api, mundo, monkeypatch):
    r = pedir(api, persona_id="max@acme.example")
    assert r.status_code == 200, r.text
    (job,) = trabajos(mundo)
    assert job.credits_estimated == 1

    vistas: list[dict] = []

    def generar(reunion, **_k):
        from dossier.services.calendar_event_dossiers import parse_calendar_event_for_dossiers

        vistas.append(parse_calendar_event_for_dossiers(reunion))
        return {"saved_dossiers": {}}

    monkeypatch.setattr(servicio, "generate_dossiers_from_calendar_event", generar)
    monkeypatch.setattr(servicio, "persist_calendar_dossiers", lambda db, *, result, **_k: result)
    monkeypatch.setattr(servicio, "get_google_calendar_access_token_for_user", lambda db, uid: "tok")
    monkeypatch.setattr(servicio, "obtener_reunion_google_por_id", lambda tok, eid: mundo.reunion)
    with Session(mundo.engine) as db:
        tomado = servicio.claim_next_queued_job(db)
        servicio.process_dossier_generation_job(db, tomado.id)

    (parsed,) = vistas
    assert [(p["full_name"], p["email"]) for p in parsed["persons"]] == [("Max", "max@acme.example")]
    assert parsed["company_corporate"] == ""


def test_ca5_con_empresa_declarada_se_guarda_un_solo_dossier_y_es_el_de_la_persona(api, mundo, monkeypatch):
    """Generador y guardado reales: la empresa identifica a la persona, pero no tiene dossier propio."""
    mundo.reunion = evento_google(*VARIAS, descripcion="Empresa: Acme SpA")
    r = pedir(api, persona_id="max@acme.example")
    assert r.status_code == 200, r.text
    corporativos: list[dict] = []
    investigadas: list = []

    def corporativo(**k):
        corporativos.append(k)
        return "# Acme SpA\n\nInforme de prueba.", False, None, None

    def persona(*, req, **_k):
        investigadas.append(req)
        return {"llm_analysis_markdown": "# Max\n\nInforme de prueba."}, False, None

    monkeypatch.setattr(eventos, "resolve_corporate_brief", lambda q: (q, "dual"))
    monkeypatch.setattr(eventos, "_corporate_md_from_cache_or_langgraph", corporativo)
    monkeypatch.setattr(eventos, "_person_research_from_cache_or_pipeline", persona)
    monkeypatch.setattr(servicio, "get_google_calendar_access_token_for_user", lambda db, uid: "tok")
    monkeypatch.setattr(servicio, "obtener_reunion_google_por_id", lambda tok, eid: mundo.reunion)
    with Session(mundo.engine) as db:
        tomado = servicio.claim_next_queued_job(db)
        servicio.process_dossier_generation_job(db, tomado.id)

    with Session(mundo.engine) as db:
        assert db.scalars(select(DossierGenerationJob)).one().status == "completed"
        (dossier,) = db.scalars(select(Dossier)).all()
        assert dossier.subject_name == "Max"
        assert dossier.dossier_data["calendar_folder_role"] != "corporate"
    assert corporativos == []
    (job,) = trabajos(mundo)
    assert job.credits_estimated == 1
    assert [(i.full_name, i.company) for i in investigadas] == [("Max", "Acme SpA")]


def test_con_una_sola_persona_no_hace_falta_elegir(api, mundo):
    mundo.reunion = evento_google("ana@acme.example", descripcion="Contacto: Ana Prueba")
    assert pedir(api).status_code == 200
    assert len(trabajos(mundo)) == 1


def test_el_lote_omite_las_reuniones_con_varias_personas(api, mundo):
    r = api.post("/calendario/generar-dossiers-google", json={"top": 5})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "CALENDAR_PERSON_REQUIRED"
    assert trabajos(mundo) == []


def test_el_get_heredado_tampoco_genera_varias_personas(api, mundo):
    r = api.get("/calendario/generar-dossiers-google", params={"event_id": "ev-1"})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "CALENDAR_PERSON_REQUIRED"
