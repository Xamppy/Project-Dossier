"""S7.3 · Descuento de créditos y aislamiento entre organizaciones en el flujo completo.

Criterio del plan: «Los créditos se descuentan una sola vez por dossier; ninguna fuga entre
organizaciones». Flujo completo: pedido por la API, trabajo procesado por el worker real,
pipeline real de Personas y de Calendario, guardado real con el trigger de cobro de Postgres.
Solo los proveedores externos (PDL, registros, prensa, LLM) son dobles. Requiere
``TEST_DATABASE_URL``.
"""
from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from alembic import command
from dossier.api.app import app
from dossier.api.auth_routes import get_db_if_configured
from dossier.db.models import DossierGenerationJob
from dossier.eu_registry.agent import ResultadoAgenteEuropeo
from dossier.news.agent import ResultadoRecoleccionPrensa
from dossier.security.jwt_tokens import create_access_token
from dossier.services import calendar_event_dossiers as cal
from dossier.services import dossier_generation_job_service as servicio
from dossier.services import dossier_progress_events as bus
from dossier.services import pdl_research, person_research_service
from tests.integration.test_calendar_job_progress_integracion import REUNION
from tests.integration.test_calendar_job_progress_integracion import PdlFalso as PdlCalendario
from tests.integration.test_person_job_progress import PdlFalso, _payload_valido

SALDO_INICIAL = 100


# --- Escenario -------------------------------------------------------------------------


def _org(c, nombre: str) -> str:
    return c.execute(
        text(
            "INSERT INTO organizations (name, slug, plan, credits_balance, credits_monthly_limit) "
            "VALUES (:n, :s, 'pro', :c, 500) RETURNING id"
        ),
        {"n": nombre, "s": nombre.lower(), "c": SALDO_INICIAL},
    ).scalar_one()


def _usuario(c, email: str, org_id, role: str, principal: bool = True):
    uid = c.execute(text("INSERT INTO users (email) VALUES (:e) RETURNING id"), {"e": email}).scalar_one()
    _miembro(c, org_id, uid, role, principal)
    return uid


def _miembro(c, org_id, uid, role: str, principal: bool) -> None:
    c.execute(
        text(
            "INSERT INTO org_memberships (organization_id, user_id, role, is_primary_org) "
            "VALUES (:o, :u, :r, :p)"
        ),
        {"o": org_id, "u": uid, "r": role, "p": principal},
    )


def cliente(user_id, org_id, role: str = "admin") -> TestClient:
    tok = create_access_token(user_id=str(user_id), email="x@example.com", organization_id=str(org_id), role=role)
    return TestClient(app, headers={"Authorization": f"Bearer {tok}"}, raise_server_exceptions=False)


@pytest.fixture
def mundo(pg_vacia, alembic_cfg, monkeypatch, llm_falso) -> Iterator[SimpleNamespace]:
    """Dos organizaciones Pro con 100 créditos; ``ambos`` pertenece a las dos."""
    import dossier.llm.text_generate as llm
    import dossier.services.corporate_registry_context as ctx

    monkeypatch.setenv("DOSSIER_CHARGE_CREDITS", "true")
    command.upgrade(alembic_cfg, "head")
    m = SimpleNamespace(engine=pg_vacia, jobs=[])
    with pg_vacia.begin() as c:
        m.org_a, m.org_b = _org(c, "A"), _org(c, "B")
        m.a_admin = _usuario(c, "admin@a.com", m.org_a, "admin")
        m.b_admin = _usuario(c, "admin@b.com", m.org_b, "admin")
        m.ambos = _usuario(c, "ambos@a.com", m.org_a, "user")
        _miembro(c, m.org_b, m.ambos, "user", False)

    # Proveedores externos: dobles. Todo lo demás es real.
    monkeypatch.setattr(pdl_research, "PdlClient", PdlFalso)
    monkeypatch.setattr(person_research_service, "deepseek_api_key", lambda: "clave-de-prueba")
    monkeypatch.setattr(
        person_research_service, "analyze_person_with_google_search", lambda **_: "## Informe\n\nAna Prueba."
    )
    monkeypatch.setattr(
        person_research_service, "analyze_person_profile_bundle", lambda **_: "## Respaldo\n\nAna Prueba."
    )
    monkeypatch.setattr(ctx, "build_uk_corporate_context_markdown", lambda p: "## UK\n\nregistro\n")
    monkeypatch.setattr(ctx, "build_us_corporate_context_markdown", lambda p: "## USA\n\nregistro\n")
    monkeypatch.setattr("dossier.eu_registry.agent.run_eu_registry_agent", lambda e, **_: ResultadoAgenteEuropeo())
    monkeypatch.setattr(
        "dossier.news.agent.collect_press_mentions", lambda e, **_: ResultadoRecoleccionPrensa(mentions=[])
    )
    monkeypatch.setattr(llm, "generate_text_with_llm", lambda user, system_instruction=None: "# Dossier\n\nResumen.")
    monkeypatch.setattr(cal, "resolve_corporate_brief", lambda q: (q, "dual"))
    monkeypatch.delenv("PERSON_RESEARCH_PROVIDER", raising=False)
    m.llm = llm_falso(*[_payload_valido()] * 20)

    def _db():
        with Session(pg_vacia) as s:
            yield s

    app.dependency_overrides[get_db_if_configured] = _db
    yield m
    app.dependency_overrides.clear()
    for job_id in m.jobs:
        bus.forget(job_id)


def saldo(m, org) -> int:
    with m.engine.connect() as c:
        return c.execute(text("SELECT credits_balance FROM organizations WHERE id = :o"), {"o": org}).scalar_one()


def movimientos(m, org) -> list:
    with m.engine.connect() as c:
        return c.execute(
            text(
                "SELECT dossier_id, change_amount, balance_after FROM credit_ledger "
                "WHERE organization_id = :o ORDER BY balance_after DESC"
            ),
            {"o": org},
        ).all()


def dossiers(m, org) -> list:
    with m.engine.connect() as c:
        return c.execute(
            text("SELECT id, subject_name, credits_consumed, status FROM dossiers WHERE organization_id = :o"),
            {"o": org},
        ).all()


def pedir_persona(m, user, org, nombre: str = "Ana Prueba", role: str = "admin") -> str:
    resp = cliente(user, org, role).post(
        "/dossiers/person/research",
        json={"full_name": nombre, "email": "ana@empresa.example", "research_source": "pdl", "async_mode": True},
    )
    assert resp.status_code == 200, resp.text
    job_id = resp.json()["job_id"]
    m.jobs.append(job_id)
    return job_id


def procesar(m, job_id) -> dict:
    with Session(m.engine) as db:
        servicio.process_dossier_generation_job(db, job_id)
    with Session(m.engine) as db:
        return servicio.serialize_job(db.get(DossierGenerationJob, job_id))


def encolar_reunion(m, user, org) -> str:
    with Session(m.engine) as db:
        job = DossierGenerationJob(
            organization_id=org,
            requested_by_user_id=user,
            status="queued",
            job_type="calendar_manual",
            calendar_provider="google",
            reunion_snapshot=dict(REUNION),
            depth_level="standard",
            credits_estimated=5,
        )
        db.add(job)
        db.commit()
        m.jobs.append(job.id)
        return str(job.id)


# --- Créditos: una sola vez por dossier --------------------------------------------------


def test_persona_por_la_api_cobra_una_vez(mundo):
    job = procesar(mundo, pedir_persona(mundo, mundo.a_admin, mundo.org_a))
    assert job["status"] == "completed"

    filas = dossiers(mundo, mundo.org_a)
    assert len(filas) == 1
    costo = filas[0].credits_consumed
    assert costo == 1
    assert job["credits_consumed"] == costo
    assert saldo(mundo, mundo.org_a) == SALDO_INICIAL - costo
    assert movimientos(mundo, mundo.org_a) == [(filas[0].id, -costo, SALDO_INICIAL - costo)]


def test_procesar_el_mismo_trabajo_otra_vez_no_vuelve_a_cobrar(mundo):
    job_id = pedir_persona(mundo, mundo.a_admin, mundo.org_a)
    procesar(mundo, job_id)
    antes = saldo(mundo, mundo.org_a)
    procesar(mundo, job_id)
    procesar(mundo, job_id)
    assert saldo(mundo, mundo.org_a) == antes
    assert len(movimientos(mundo, mundo.org_a)) == 1
    assert len(dossiers(mundo, mundo.org_a)) == 1


def test_un_pedido_repetido_mientras_esta_activo_no_duplica_el_cobro(mundo):
    primero = pedir_persona(mundo, mundo.a_admin, mundo.org_a)
    segundo = pedir_persona(mundo, mundo.a_admin, mundo.org_a)
    assert primero == segundo
    procesar(mundo, primero)
    assert len(movimientos(mundo, mundo.org_a)) == 1
    assert saldo(mundo, mundo.org_a) == SALDO_INICIAL - 1


def test_reunion_del_calendario_cobra_cada_dossier_una_sola_vez(mundo, monkeypatch):
    monkeypatch.setattr(pdl_research, "PdlClient", PdlCalendario)
    monkeypatch.setenv("DEEPSEEK_DISABLE_PERSON_WEB", "1")
    job = procesar(mundo, encolar_reunion(mundo, mundo.a_admin, mundo.org_a))
    assert job["status"] == "completed"

    filas = dossiers(mundo, mundo.org_a)
    movs = movimientos(mundo, mundo.org_a)
    # Empresa y asistentes: Acme (completo), Ana (completo) y Beto, que no está en PDL (fallido).
    cobrados = [f for f in filas if f.status == "complete"]
    fallidos = [f for f in filas if f.status == "failed"]
    assert len(cobrados) >= 2 and len(fallidos) >= 1
    # Un movimiento por dossier cobrado, ni más ni menos; un dossier fallido no se cobra.
    assert sorted(str(d) for d, _, _ in movs) == sorted(str(f.id) for f in cobrados)
    assert all(f.credits_consumed == 0 for f in fallidos)
    total = sum(f.credits_consumed for f in cobrados)
    assert -sum(cambio for _, cambio, _ in movs) == total
    assert saldo(mundo, mundo.org_a) == SALDO_INICIAL - total
    assert job["credits_consumed"] == total
    # El saldo anotado baja de a un dossier (BUG-2026-10-19-08).
    assert [s for _, _, s in movs] == sorted({s for _, _, s in movs}, reverse=True)


def test_una_generacion_que_falla_no_cobra(mundo, monkeypatch):
    def revienta(*_a, **_k):
        raise RuntimeError("proveedor caído")

    monkeypatch.setattr(servicio, "run_person_research_and_persist", revienta)
    job = procesar(mundo, pedir_persona(mundo, mundo.a_admin, mundo.org_a))
    assert job["status"] == "failed"
    assert job["credits_consumed"] == 0
    assert saldo(mundo, mundo.org_a) == SALDO_INICIAL
    assert movimientos(mundo, mundo.org_a) == []


def test_un_trabajo_cancelado_antes_de_empezar_no_cobra(mundo):
    job_id = pedir_persona(mundo, mundo.a_admin, mundo.org_a)
    assert cliente(mundo.a_admin, mundo.org_a).post(f"/dossier-generation-jobs/{job_id}/cancel").status_code == 200
    job = procesar(mundo, job_id)
    assert job["status"] == "cancelled"
    assert saldo(mundo, mundo.org_a) == SALDO_INICIAL
    assert movimientos(mundo, mundo.org_a) == []


def test_quien_esta_en_dos_organizaciones_paga_con_la_organizacion_del_pedido(mundo):
    procesar(mundo, pedir_persona(mundo, mundo.ambos, mundo.org_b, role="user"))
    assert saldo(mundo, mundo.org_b) == SALDO_INICIAL - 1
    assert saldo(mundo, mundo.org_a) == SALDO_INICIAL
    assert movimientos(mundo, mundo.org_a) == []
    assert len(dossiers(mundo, mundo.org_b)) == 1


# --- Aislamiento en el flujo completo ------------------------------------------------------


def test_lo_que_genera_a_no_lo_ve_ni_lo_toca_b(mundo):
    job_id = pedir_persona(mundo, mundo.a_admin, mundo.org_a)
    procesar(mundo, job_id)
    (dossier_a,) = dossiers(mundo, mundo.org_a)
    b = cliente(mundo.b_admin, mundo.org_b)

    # Trabajo: ni por id, ni en la lista, ni por su canal en vivo, ni cancelándolo.
    assert b.get(f"/dossier-generation-jobs/{job_id}").status_code == 404
    assert b.get(f"/dossier-generation-jobs/{job_id}/stream").status_code == 404
    assert b.post(f"/dossier-generation-jobs/{job_id}/cancel").status_code == 404
    assert job_id not in b.get("/dossier-generation-jobs").text
    # Dossier: ni por id, ni en la lista, ni por correo, ni borrándolo.
    assert b.get(f"/dossiers/{dossier_a.id}").status_code == 404
    assert str(dossier_a.id) not in b.get("/dossiers").text
    assert b.post(f"/dossiers/{dossier_a.id}/email").status_code in (404, 503)
    assert b.delete(f"/dossiers/{dossier_a.id}").status_code in (403, 404)
    # Canal de notificaciones de B: sin rastro de A.
    import os

    os.environ["DOSSIER_NOTIFICATIONS_MAX_SECONDS"] = "0"
    try:
        with b.stream("GET", "/dossier-notifications/stream") as resp:
            cuerpo = b"".join(resp.iter_bytes()).decode("utf-8")
    finally:
        os.environ.pop("DOSSIER_NOTIFICATIONS_MAX_SECONDS", None)
    assert str(dossier_a.id) not in cuerpo
    assert "Ana Prueba" not in cuerpo

    # Nada cambió para A ni para B.
    assert len(dossiers(mundo, mundo.org_a)) == 1
    assert saldo(mundo, mundo.org_b) == SALDO_INICIAL
    assert movimientos(mundo, mundo.org_b) == []


def test_el_movimiento_de_creditos_queda_en_la_organizacion_del_dossier(mundo):
    procesar(mundo, pedir_persona(mundo, mundo.a_admin, mundo.org_a))
    procesar(mundo, pedir_persona(mundo, mundo.b_admin, mundo.org_b, nombre="Ana Prueba B"))
    with mundo.engine.connect() as c:
        cruzados = c.execute(
            text(
                "SELECT count(*) FROM credit_ledger l JOIN dossiers d ON d.id = l.dossier_id "
                "WHERE l.organization_id <> d.organization_id"
            )
        ).scalar_one()
    assert cruzados == 0
    assert saldo(mundo, mundo.org_a) == SALDO_INICIAL - 1
    assert saldo(mundo, mundo.org_b) == SALDO_INICIAL - 1
