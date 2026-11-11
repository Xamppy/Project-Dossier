"""Informe beta · Empresas por la cola de trabajos, con avance real por agente (Postgres).

Defecto del informe del 2026-10-06: «la barra de progreso no avanza de forma fluida y parece
detenida». La pantalla Empresas hacía una sola petición larga sin avance. Ahora
``POST /dossiers/corporate/generate`` con ``async_mode`` encola un trabajo ``corporate_manual``
que el worker procesa con el mismo grafo, informando el avance de cada agente. Requiere
``TEST_DATABASE_URL``.
"""
# ruff: noqa: F811 (el fixture «mundo» se importa de las pruebas de S7.3)
from __future__ import annotations

import pytest
from sqlalchemy import text

from tests.integration.test_s7_3_creditos_aislamiento import (  # noqa: F401
    SALDO_INICIAL,
    cliente,
    dossiers,
    movimientos,
    mundo,
    procesar,
    saldo,
)

RUTA = "/dossiers/corporate/generate"


def encolar(m, consulta: str = "Acme Corp", depth: str = "basic", user=None, org=None):
    resp = cliente(user or m.a_admin, org or m.org_a).post(
        RUTA, json={"subject_query": consulta, "depth": depth, "async_mode": True}
    )
    return resp


def test_encola_y_responde_enseguida_con_el_trabajo(mundo):
    resp = encolar(mundo)
    assert resp.status_code == 200
    datos = resp.json()
    assert datos["async"] is True
    assert datos["status"] == "queued"
    assert datos["credits_estimated"] == 1
    mundo.jobs.append(datos["job_id"])
    # Todavía no hay dossier ni cobro: lo hace el worker.
    assert dossiers(mundo, mundo.org_a) == []
    assert saldo(mundo, mundo.org_a) == SALDO_INICIAL


def test_el_worker_genera_con_avance_por_agente_y_cobra_una_vez(mundo):
    job_id = encolar(mundo).json()["job_id"]
    mundo.jobs.append(job_id)
    job = procesar(mundo, job_id)

    assert job["status"] == "completed"
    (scope,) = job["progress"]["scopes"]
    assert scope["kind"] == "corporate"
    estados = {a["agent_name"]: a["status"] for a in scope["agents"]}
    assert estados["synthesize_llm"] == "completed"
    assert all(s in ("completed", "skipped") for s in estados.values())
    assert scope["origin"] == "generated"

    (d,) = dossiers(mundo, mundo.org_a)
    assert d.status == "complete"
    assert scope["dossier"] == {"id": str(d.id), "status": "complete"}
    assert job["result"]["id"] == str(d.id)
    assert job["credits_consumed"] == d.credits_consumed == 1
    assert len(movimientos(mundo, mundo.org_a)) == 1
    assert saldo(mundo, mundo.org_a) == SALDO_INICIAL - 1


def test_el_avance_llega_por_el_canal_en_vivo(mundo):
    from dossier.services import dossier_progress_events as bus

    job_id = encolar(mundo).json()["job_id"]
    mundo.jobs.append(job_id)
    procesar(mundo, job_id)
    from uuid import UUID

    eventos = [e for _, e, _ in bus.events_since(UUID(job_id), 0)]
    assert "agent_progress" in eventos
    assert eventos[-1] == "job_completed"


def test_un_pedido_repetido_mientras_esta_activo_devuelve_el_mismo_trabajo(mundo):
    primero = encolar(mundo).json()["job_id"]
    segundo = encolar(mundo).json()["job_id"]
    mundo.jobs.append(primero)
    assert primero == segundo
    otro = encolar(mundo, consulta="Globex Ltd").json()["job_id"]
    mundo.jobs.append(otro)
    assert otro != primero


def test_cuenta_para_el_tope_de_dossiers_a_la_vez(mundo):
    with mundo.engine.begin() as c:
        c.execute(text("UPDATE plan_settings SET max_concurrent_dossiers = 1 WHERE plan = 'pro'"))
    mundo.jobs.append(encolar(mundo).json()["job_id"])
    resp = encolar(mundo, consulta="Globex Ltd")
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "CONCURRENT_DOSSIER_LIMIT"


def test_sin_creditos_no_encola(mundo):
    with mundo.engine.begin() as c:
        c.execute(text("UPDATE organizations SET credits_balance = 0 WHERE id = :o"), {"o": mundo.org_a})
    resp = encolar(mundo)
    assert resp.status_code == 402
    with mundo.engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM dossier_generation_jobs")).scalar_one() == 0


def test_cancelado_antes_de_empezar_no_genera_ni_cobra(mundo):
    job_id = encolar(mundo).json()["job_id"]
    mundo.jobs.append(job_id)
    assert cliente(mundo.a_admin, mundo.org_a).post(f"/dossier-generation-jobs/{job_id}/cancel").status_code == 200
    job = procesar(mundo, job_id)
    assert job["status"] == "cancelled"
    assert dossiers(mundo, mundo.org_a) == []
    assert saldo(mundo, mundo.org_a) == SALDO_INICIAL


def test_cancelado_mientras_corre_el_grafo_no_guarda_ni_cobra(mundo, monkeypatch):
    import dossier.llm.text_generate as llm

    job_id = encolar(mundo).json()["job_id"]
    mundo.jobs.append(job_id)

    def cancelar_y_responder(user, system_instruction=None):
        with mundo.engine.begin() as c:
            c.execute(text("UPDATE dossier_generation_jobs SET status = 'cancelled' WHERE id = :i"), {"i": job_id})
        return "# Dossier\n\nResumen."

    monkeypatch.setattr(llm, "generate_text_with_llm", cancelar_y_responder)
    job = procesar(mundo, job_id)
    assert job["status"] == "cancelled"
    assert dossiers(mundo, mundo.org_a) == []
    assert movimientos(mundo, mundo.org_a) == []


def test_otra_organizacion_no_ve_el_trabajo(mundo):
    job_id = encolar(mundo).json()["job_id"]
    mundo.jobs.append(job_id)
    b = cliente(mundo.b_admin, mundo.org_b)
    assert b.get(f"/dossier-generation-jobs/{job_id}").status_code == 404
    assert b.get(f"/dossier-generation-jobs/{job_id}/stream").status_code == 404


@pytest.mark.parametrize("async_mode", [False, None])
def test_sin_async_mode_la_ruta_sigue_siendo_sincrona(mundo, async_mode):
    cuerpo = {"subject_query": "Acme Corp", "depth": "basic"}
    if async_mode is not None:
        cuerpo["async_mode"] = async_mode
    resp = cliente(mundo.a_admin, mundo.org_a).post(RUTA, json=cuerpo)
    assert resp.status_code == 200
    assert "job_id" not in resp.json()
    assert resp.json()["status"] == "complete"
    assert len(dossiers(mundo, mundo.org_a)) == 1
