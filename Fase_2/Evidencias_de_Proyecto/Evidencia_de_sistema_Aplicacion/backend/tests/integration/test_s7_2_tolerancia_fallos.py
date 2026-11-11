"""S7.2 · Tolerancia a fallos con cada agente fallando por separado (flujo completo, Postgres).

Criterio del plan: «En todos los casos el dossier se entrega con resultado parcial y el fallo
queda registrado». Flujo de Calendario completo (grafo corporativo y asistentes reales, guardado
real); cada prueba tumba un solo agente o proveedor. Las excepciones llevan una «clave» falsa
para comprobar que el detalle técnico nunca llega al usuario. Requiere ``TEST_DATABASE_URL``.
"""
from __future__ import annotations

import json

import pytest
from sqlalchemy import text

from dossier.services import pdl_research
from tests.integration.test_calendar_job_progress_integracion import PdlFalso as PdlCalendario
from tests.integration.test_s7_3_creditos_aislamiento import encolar_reunion, mundo, procesar  # noqa: F401

SECRETO = "sk-secreta-123"

# Agente del grafo corporativo → fuentes que deben quedar con resultado «error».
AGENTES_DE_DATOS = {
    "agent_corporate_uk": {"companies_house"},
    "agent_corporate_usa": {"sec_edgar"},
    "agent_corporate_eu": {"eu_registry_fr", "eu_registry_de"},
    "agent_news": {"gdelt_news", "news_api"},
}


def _revienta(nombre: str):
    def revienta(*_a, **_k):
        raise ConnectionError(f"{nombre} caído (clave={SECRETO})")

    return revienta


def _caer(monkeypatch, agente: str) -> None:
    import dossier.llm.text_generate as llm
    import dossier.services.corporate_registry_context as ctx

    if agente == "agent_corporate_uk":
        monkeypatch.setattr(ctx, "build_uk_corporate_context_markdown", _revienta(agente))
    elif agente == "agent_corporate_usa":
        monkeypatch.setattr(ctx, "build_us_corporate_context_markdown", _revienta(agente))
    elif agente == "agent_corporate_eu":
        monkeypatch.setattr("dossier.eu_registry.agent.run_eu_registry_agent", _revienta(agente))
    elif agente == "agent_news":
        monkeypatch.setattr("dossier.news.agent.collect_press_mentions", _revienta(agente))
    elif agente == "synthesize_llm":
        monkeypatch.setattr(llm, "generate_text_with_llm", _revienta(agente))
    else:  # pragma: no cover
        raise AssertionError(agente)


def _dossiers(m) -> dict[str, dict]:
    with m.engine.connect() as c:
        filas = c.execute(
            text(
                "SELECT subject_name, status, status_message, agents_failed, credits_consumed, dossier_data "
                "FROM dossiers WHERE organization_id = :o"
            ),
            {"o": m.org_a},
        ).all()
    return {f.subject_name: dict(f._mapping) for f in filas}


def _sin_detalle_tecnico(*cosas) -> None:
    texto = json.dumps(cosas, ensure_ascii=False, default=str)
    assert SECRETO not in texto
    assert "caído (clave" not in texto


def _agente_en_progreso(job: dict, agente: str) -> dict:
    scope = next(s for s in job["progress"]["scopes"] if s["scope_id"].startswith("corporate"))
    return next(a for a in scope["agents"] if a["agent_name"] == agente)


@pytest.fixture
def reunion(mundo, monkeypatch):  # noqa: F811
    """Reunión con Acme Corp, Ana (en PDL) y Beto (sin datos en PDL)."""
    monkeypatch.setattr(pdl_research, "PdlClient", PdlCalendario)
    monkeypatch.setenv("DEEPSEEK_DISABLE_PERSON_WEB", "1")
    return mundo


def _generar(m) -> tuple[dict, dict[str, dict]]:
    job = procesar(m, encolar_reunion(m, m.a_admin, m.org_a))
    return job, _dossiers(m)


# --- Grafo corporativo: un agente de datos caído ----------------------------------------------


@pytest.mark.parametrize("agente", list(AGENTES_DE_DATOS))
def test_un_registro_o_la_prensa_caidos_no_impiden_el_dossier(reunion, monkeypatch, agente):
    _caer(monkeypatch, agente)
    job, dossiers = _generar(reunion)

    assert job["status"] == "completed"
    corp = dossiers["Acme Corp"]
    # Se entrega con lo que trajeron los demás agentes…
    assert corp["status"] == "complete"
    assert corp["dossier_data"]["body"].strip()
    assert corp["credits_consumed"] > 0
    # …y el fallo queda registrado en el dossier, en sus fuentes y en el avance del trabajo.
    assert corp["agents_failed"] == [agente]
    con_error = {f["fuente"] for f in corp["dossier_data"]["fuentes_consultadas"] if f["resultado"] == "error"}
    assert con_error == AGENTES_DE_DATOS[agente]
    assert _agente_en_progreso(job, agente)["status"] == "failed"
    # Los asistentes no se ven afectados.
    assert dossiers["Ana Prueba"]["status"] == "complete"
    _sin_detalle_tecnico(corp, job)


def test_el_detalle_del_error_no_llega_al_prompt_de_la_ia(reunion, monkeypatch):
    import dossier.llm.text_generate as llm

    prompts: list[str] = []

    def guardar(user, system_instruction=None):
        prompts.append(user)
        return "# Dossier\n\nResumen."

    for agente in AGENTES_DE_DATOS:
        _caer(monkeypatch, agente)
    monkeypatch.setattr(llm, "generate_text_with_llm", guardar)
    _generar(reunion)
    assert prompts
    _sin_detalle_tecnico(prompts)


# --- Grafo corporativo: la síntesis con IA caída ---------------------------------------------


def test_sin_sintesis_se_entrega_un_informe_parcial_con_los_datos_reunidos(reunion, monkeypatch):
    _caer(monkeypatch, "synthesize_llm")
    job, dossiers = _generar(reunion)

    assert job["status"] == "completed"
    corp = dossiers["Acme Corp"]
    assert corp["status"] == "partial"
    assert corp["agents_failed"] == ["synthesize_llm"]
    cuerpo = corp["dossier_data"]["body"]
    # Los datos que sí llegaron (los dobles de registro de UK y USA) están en el informe.
    assert "## UK" in cuerpo and "## USA" in cuerpo
    assert corp["status_message"]
    # No hubo análisis con IA: no se cobra.
    assert corp["credits_consumed"] == 0
    fuentes = corp["dossier_data"]["fuentes_consultadas"]
    assert any(f["fuente"] == "deepseek" and f["resultado"] == "error" for f in fuentes)
    assert _agente_en_progreso(job, "synthesize_llm")["status"] == "failed"
    _sin_detalle_tecnico(corp, job)


def test_sin_ningun_dato_ni_sintesis_no_se_inventa_un_dossier_de_empresa(reunion, monkeypatch):
    for agente in [*AGENTES_DE_DATOS, "synthesize_llm"]:
        _caer(monkeypatch, agente)
    job, dossiers = _generar(reunion)

    assert job["status"] == "completed"
    assert "Acme Corp" not in dossiers
    assert dossiers["Ana Prueba"]["status"] == "complete"
    _sin_detalle_tecnico(job)


# --- Asistentes: el proveedor de personas o la IA caídos --------------------------------------


class PdlCaido:
    def person_enrich(self, params):
        raise ConnectionError(f"PDL caído (clave={SECRETO})")

    def person_search(self, **_):
        raise ConnectionError(f"PDL caído (clave={SECRETO})")


def test_proveedor_de_personas_caido(reunion, monkeypatch):
    monkeypatch.setattr(pdl_research, "PdlClient", PdlCaido)
    job, dossiers = _generar(reunion)

    assert job["status"] == "completed"
    assert dossiers["Acme Corp"]["status"] == "complete"
    for nombre in ("Ana Prueba", "Beto Prueba"):
        persona = dossiers[nombre]
        assert persona["status"] == "failed"
        assert persona["status_message"]
        assert persona["agents_failed"] == ["person_research"]
        assert persona["credits_consumed"] == 0
        assert not persona["dossier_data"]["body"]
    _sin_detalle_tecnico(dossiers, job)


def test_ia_de_persona_caida_conserva_el_perfil_como_resultado_parcial(reunion, monkeypatch):
    import dossier.llm.structured_synthesis as ss

    monkeypatch.setattr(ss, "chat_completion", _revienta("DeepSeek"))
    job, dossiers = _generar(reunion)

    assert job["status"] == "completed"
    ana = dossiers["Ana Prueba"]
    assert ana["status"] == "failed"
    assert ana["agents_failed"] == ["deepseek_person_analysis"]
    assert ana["credits_consumed"] == 0
    # El perfil que encontró PDL queda como resultado parcial del trabajo (S5.4).
    scope = next(s for s in job["progress"]["scopes"] if s["label"] == "Ana Prueba")
    etapas = {e["stage_id"]: e["status"] for e in scope["stages"]}
    assert etapas["person.profile_normalization"] == "completed"
    assert etapas["person.profile_synthesis"] == "failed"
    assert scope["partial_results"]
    _sin_detalle_tecnico(ana, job)


# --- Un informe parcial no se cachea ni se cobra (Calendario y pantalla Empresas) --------------


def _registrar_cache(monkeypatch, modulo) -> list[str]:
    guardados: list[str] = []
    monkeypatch.setattr(modulo, "set_corporate_cached_markdown", lambda clave, md: guardados.append(md))
    return guardados


@pytest.mark.parametrize("sintesis_caida", [True, False])
def test_calendario_solo_cachea_el_informe_completo(reunion, monkeypatch, sintesis_caida):
    from dossier.services import calendar_event_dossiers as cal

    guardados = _registrar_cache(monkeypatch, cal)
    if sintesis_caida:
        _caer(monkeypatch, "synthesize_llm")
    _generar(reunion)
    assert len(guardados) == (0 if sintesis_caida else 1)


@pytest.mark.parametrize("sintesis_caida", [True, False])
def test_pantalla_empresas_parcial_sin_cobro_ni_cache(reunion, monkeypatch, sintesis_caida):
    from dossier.api import dossier_routes
    from tests.integration.test_s7_3_creditos_aislamiento import SALDO_INICIAL, cliente, saldo

    guardados = _registrar_cache(monkeypatch, dossier_routes)
    if sintesis_caida:
        _caer(monkeypatch, "synthesize_llm")
    resp = cliente(reunion.a_admin, reunion.org_a).post(
        "/dossiers/corporate/generate", json={"subject_query": "Acme Corp", "depth": "basic"}
    )
    assert resp.status_code == 200, resp.text
    (corp,) = _dossiers(reunion).values()
    if sintesis_caida:
        assert corp["status"] == "partial"
        assert corp["status_message"]
        assert corp["agents_failed"] == ["synthesize_llm"]
        assert corp["credits_consumed"] == 0
        assert saldo(reunion, reunion.org_a) == SALDO_INICIAL
        assert guardados == []
        _sin_detalle_tecnico(corp, resp.json())
    else:
        assert corp["status"] == "complete"
        assert corp["credits_consumed"] == 1
        assert saldo(reunion, reunion.org_a) == SALDO_INICIAL - 1
        assert len(guardados) == 1
