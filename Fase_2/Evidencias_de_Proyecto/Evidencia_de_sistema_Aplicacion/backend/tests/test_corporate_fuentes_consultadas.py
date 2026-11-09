"""S2.4 y S2.5: tolerancia a fallos del agente europeo y fuentes consultadas por jurisdicción.

- S2.4 (CA-B2.4): si el agente europeo falla (error HTTP o timeout de 10 s), el dossier se
  emite igual y el fallo queda registrado en ``agents_failed`` de la fila guardada.
- S2.5: cada dossier corporativo declara qué registro consultó y cuándo, por jurisdicción
  (``data_sources_used`` y ``dossier_data["fuentes_consultadas"]``).

Antes, las dos rutas que guardan el dossier corporativo (calendario y generación manual)
escribían listas fijas (``["companies_house", "sec_edgar", "sec_company_facts", "gemini"]``)
y la ruta manual descartaba los agentes fallidos del grafo.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from dossier.db.models import Dossier
from dossier.eu_registry.agent import ResultadoAgenteEuropeo
from dossier.graphs.corporate_dossier_graph import run_corporate_dossier_langgraph_detailed
from dossier.news.agent import FalloProveedor, ResultadoRecoleccionPrensa
from dossier.schemas.corporate_registry import JurisdiccionRegistro, RegistroCorporativo
from dossier.schemas.dossier_executive_payload import (
    CorporateRecordCitation,
    PressMention,
    SourceCitation,
    SourceType,
)
from dossier.services.corporate_dossier_telemetry import columnas_telemetria, telemetria_de

CONSULTA_FR = datetime(2026, 11, 9, 12, 0, 5, tzinfo=UTC)
CONSULTA_PRENSA = datetime(2026, 11, 9, 12, 0, 7, tzinfo=UTC)


def _cita_fr(razon: str = "Acme Prueba SAS") -> CorporateRecordCitation:
    return CorporateRecordCitation(
        record=RegistroCorporativo(
            jurisdiccion=JurisdiccionRegistro.fr,
            fuente="recherche-entreprises",
            identificador_registro="900000001",
            razon_social=razon,
            estado="active",
        ),
        source=SourceCitation(
            source_type=SourceType.eu_registry,
            source_name="Recherche d'entreprises (data.gouv.fr)",
            retrieved_at=CONSULTA_FR,
            record_id="900000001",
        ),
    )


def _mencion(titular: str = "Acme Prueba abre una oficina", fuente: SourceType = SourceType.gdelt_news) -> PressMention:
    return PressMention(
        headline=titular,
        publisher="Diario de Prueba",
        published_date="20261101T100000Z",
        summary="Resumen.",
        url="https://example.test/acme",
        source=SourceCitation(source_type=fuente, source_name=fuente.value, retrieved_at=CONSULTA_PRENSA),
    )


@pytest.fixture
def agentes(monkeypatch):
    """Todos los agentes responden; cada prueba sustituye el que necesita romper."""
    import dossier.llm.text_generate as llm
    import dossier.services.corporate_registry_context as ctx

    def instalar(*, eu=None, news=None):
        monkeypatch.setattr(ctx, "build_uk_corporate_context_markdown", lambda p: "## UK\n\nregistro UK\n")
        monkeypatch.setattr(ctx, "build_us_corporate_context_markdown", lambda p: "## USA\n\nregistro US\n")
        monkeypatch.setattr(
            "dossier.eu_registry.agent.run_eu_registry_agent",
            eu or (lambda nombre, **_: ResultadoAgenteEuropeo(citas=[_cita_fr()])),
        )
        monkeypatch.setattr(
            "dossier.news.agent.collect_press_mentions",
            news or (lambda consulta, **_: ResultadoRecoleccionPrensa(mentions=[_mencion()])),
        )
        monkeypatch.setattr(
            llm, "generate_text_with_llm", lambda user, system_instruction=None: "# Dossier corporativo\n\nResumen."
        )

    instalar()
    return instalar


def _correr(scope: str = "dual"):
    return run_corporate_dossier_langgraph_detailed(
        tema_reunion="Reunión con Acme Prueba",
        participantes="Acme Prueba",
        jurisdiction_scope=scope,
        empresa_objetivo="Acme Prueba",
    )


def _por_fuente(resultado) -> dict[str, dict]:
    return {f["fuente"]: f for f in resultado.fuentes_consultadas}


# --- S2.4: el fallo del agente europeo no impide el dossier ----------------------------


def test_si_el_agente_europeo_lanza_el_dossier_se_emite_y_el_fallo_queda_registrado(agentes):
    def eu_caido(nombre, **_):
        raise TimeoutError("Recherche d'entreprises no respondió en 10 s")

    agentes(eu=eu_caido)

    resultado = _correr()

    assert resultado.markdown == "# Dossier corporativo\n\nResumen."
    assert resultado.agents_failed == ["agent_corporate_eu"]
    fuentes = _por_fuente(resultado)
    assert fuentes["eu_registry_fr"]["resultado"] == "error"
    assert fuentes["eu_registry_de"]["resultado"] == "error"


def test_el_cliente_europeo_corta_a_los_10_segundos(monkeypatch):
    """CA-B2.4 fija el plazo en 10 s (antes eran 20)."""
    from dossier.eu_registry import client

    plazos: list[float] = []

    class _Respuesta:
        def raise_for_status(self):
            pass

        def json(self):
            return {"results": []}

    def get(url, params=None, timeout=None):
        plazos.append(timeout)
        return _Respuesta()

    monkeypatch.setattr(client.requests, "get", get)

    client.search_france_companies("Acme Prueba")

    assert plazos == [10]


# --- S2.5: qué registro se consultó y cuándo ---------------------------------------------


def test_con_alcance_dual_declara_cada_registro_con_su_jurisdiccion_y_fecha(agentes):
    resultado = _correr()

    fuentes = _por_fuente(resultado)
    assert fuentes["companies_house"]["jurisdiccion"] == "uk"
    assert fuentes["sec_edgar"]["jurisdiccion"] == "us"
    assert fuentes["eu_registry_fr"] == {
        "fuente": "eu_registry_fr",
        "nombre": "Recherche d'entreprises (data.gouv.fr)",
        "jurisdiccion": "fr",
        "resultado": "consultada",
        "consultado_en": CONSULTA_FR.isoformat(),
    }
    # Alemania se consultó pero no devolvió la empresa.
    assert fuentes["eu_registry_de"]["resultado"] == "sin_resultados"
    assert fuentes["gdelt_news"]["resultado"] == "consultada"
    assert fuentes["gdelt_news"]["consultado_en"] == CONSULTA_PRENSA.isoformat()
    assert fuentes["news_api"]["resultado"] == "sin_resultados"
    assert fuentes["deepseek"]["resultado"] == "consultada"
    for f in resultado.fuentes_consultadas:
        datetime.fromisoformat(f["consultado_en"])  # siempre con fecha de consulta


def test_fallo_de_un_solo_pais_marca_ese_pais_y_conserva_el_otro(agentes):
    agentes(eu=lambda nombre, **_: ResultadoAgenteEuropeo(citas=[_cita_fr()], errores={"de": "HTTP 502"}))

    resultado = _correr()

    fuentes = _por_fuente(resultado)
    assert fuentes["eu_registry_fr"]["resultado"] == "consultada"
    assert fuentes["eu_registry_de"]["resultado"] == "error"
    assert "agent_corporate_eu" in resultado.agents_succeeded


def test_proveedor_de_prensa_caido_queda_como_error(agentes):
    agentes(
        news=lambda consulta, **_: ResultadoRecoleccionPrensa(
            mentions=[_mencion()], failed_providers=[FalloProveedor(provider="news_api", error="429")]
        )
    )

    fuentes = _por_fuente(_correr())

    assert fuentes["news_api"]["resultado"] == "error"
    assert fuentes["gdelt_news"]["resultado"] == "consultada"


def test_con_alcance_solo_reino_unido_no_declara_registros_no_consultados(agentes):
    fuentes = _por_fuente(_correr(scope="uk_only"))

    assert "companies_house" in fuentes
    assert "sec_edgar" not in fuentes
    assert "eu_registry_fr" not in fuentes and "eu_registry_de" not in fuentes


# --- Columnas de la fila ``dossiers`` ------------------------------------------------------


def test_columnas_salen_de_la_telemetria_real_y_no_de_una_lista_fija(agentes):
    agentes(eu=lambda nombre, **_: ResultadoAgenteEuropeo(citas=[_cita_fr()], errores={"de": "HTTP 502"}))
    telemetria = telemetria_de(_correr())

    columnas = columnas_telemetria(telemetria, es_error=False)

    assert columnas["agents_failed"] == []
    assert set(columnas["agents_activated"]) == {
        "agent_corporate_uk",
        "agent_corporate_usa",
        "agent_corporate_eu",
        "agent_news",
        "synthesize_llm",
    }
    # Solo lo que respondió; el país caído queda en fuentes_consultadas con resultado error.
    assert columnas["data_sources_used"] == [
        "companies_house",
        "sec_edgar",
        "eu_registry_fr",
        "gdelt_news",
        "news_api",
        "deepseek",
    ]
    assert "gemini" not in columnas["data_sources_used"]
    assert columnas["dossier_data"]["fuentes_consultadas"] == telemetria["fuentes_consultadas"]


def test_telemetria_es_serializable_a_json(agentes):
    import json

    json.dumps(telemetria_de(_correr()))


def test_sin_telemetria_por_cache_no_inventa_fuentes():
    columnas = columnas_telemetria(None, es_error=False)

    assert columnas == {"agents_activated": [], "agents_failed": [], "data_sources_used": [], "dossier_data": {}}


def test_sin_telemetria_con_error_conserva_el_criterio_anterior():
    assert columnas_telemetria(None, es_error=True)["agents_failed"] == ["synthesize_llm"]


# --- Persistencia en las dos rutas ---------------------------------------------------------


class _FakeSession:
    def __init__(self):
        self.added: list[object] = []

    def get(self, model, pk):
        return None

    def add(self, obj):
        self.added.append(obj)

    def refresh(self, obj):
        pass

    def commit(self):
        pass

    def flush(self):
        pass


def test_calendario_guarda_agentes_y_fuentes_de_la_telemetria(agentes):
    from dossier.services.calendar_event_dossiers import persist_calendar_dossiers

    def eu_caido(nombre, **_):
        raise RuntimeError("HTTP 500")

    agentes(eu=eu_caido)
    telemetria = telemetria_de(_correr())
    db = _FakeSession()
    result = {
        "reunion": {},
        "parse": {"tema": "Reunión con Acme Prueba", "company_corporate": "Acme Prueba"},
        "dossier_corporativo": "# Dossier corporativo\n\nResumen.",
        "dossier_personas": [],
        "errors": [],
        "corporate_cache_hit": False,
        "corporate_agents_failed": telemetria["agents_failed"],
        "corporate_telemetria": telemetria,
        "output_language": "es",
    }

    persist_calendar_dossiers(
        db,
        user_id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        result=result,
        calendar_provider="google",
        generation_duration_ms=10,
    )

    corp = next(o for o in db.added if isinstance(o, Dossier) and o.module_corporate)
    assert corp.status == "complete"
    assert corp.agents_failed == ["agent_corporate_eu"]
    assert "eu_registry_fr" not in corp.data_sources_used
    assert {f["fuente"]: f["resultado"] for f in corp.dossier_data["fuentes_consultadas"]}["eu_registry_fr"] == "error"


def test_generacion_manual_guarda_el_fallo_europeo_y_las_fuentes(agentes, monkeypatch):
    """La ruta manual llamaba al grafo sin telemetría: ahora guarda la real."""
    from dossier.api import dossier_routes as rutas
    from dossier.schemas.dossier_generation import CreateCorporateDossierRequest

    def eu_caido(nombre, **_):
        raise RuntimeError("HTTP 500")

    agentes(eu=eu_caido)
    monkeypatch.setenv("DOSSIER_CHARGE_CREDITS", "0")
    monkeypatch.setattr(rutas, "redis_corporate_cache_available", lambda: False)
    monkeypatch.setattr(rutas, "get_corporate_cached_markdown", lambda key: None)
    monkeypatch.setattr(rutas, "set_corporate_cached_markdown", lambda key, md: None)
    monkeypatch.setattr(rutas, "run_with_corporate_cache_lock", lambda key, fn: fn())
    monkeypatch.setattr(rutas, "assert_corporate_dossier_allowed", lambda org: None)
    monkeypatch.setattr(rutas, "assert_depth_allowed", lambda org, depth: None)
    monkeypatch.setattr(rutas, "format_dossier_context_for_prompt", lambda org: "")
    monkeypatch.setattr(rutas, "effective_output_language", lambda user, lang: "es")
    org = SimpleNamespace(id=uuid.uuid4(), credits_balance=10, plan="pro")
    ctx = SimpleNamespace(user=SimpleNamespace(id=uuid.uuid4()), org=org)
    db = _FakeSession()

    rutas.generate_corporate_dossier(CreateCorporateDossierRequest(subject_query="Acme Prueba"), ctx, db)

    dossier = next(o for o in db.added if isinstance(o, Dossier))
    assert dossier.status == "complete"
    assert dossier.agents_failed == ["agent_corporate_eu"]
    assert "agent_corporate_eu" in dossier.agents_activated
    assert "gemini" not in dossier.data_sources_used
    assert "fuentes_consultadas" in dossier.dossier_data
