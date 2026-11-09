"""S3.4: procedencia completa de cada mención de prensa.

Criterio del plan: ninguna mención se persiste sin sus cuatro campos de procedencia
(título, medio, URL y fecha de publicación) y su fecha de consulta. Las menciones se
guardan en ``dossier_media_mentions`` (S4.5), que hasta ahora nadie escribía.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from dossier.db.models import Dossier, DossierMediaMention
from dossier.services.press_mentions_writer import escribir_menciones_prensa

CONSULTA = "2026-11-09T12:00:07+00:00"


def _mencion(**cambios) -> dict:
    base = {
        "headline": "Acme Prueba abre una oficina en Lyon",
        "publisher": "Diario de Prueba",
        "published_date": "2026-11-01T10:00:00Z",
        "summary": "La empresa amplía su presencia.",
        "url": "https://example.test/acme-lyon",
        "source": {
            "source_type": "news_api",
            "source_name": "news_api",
            "url": None,
            "retrieved_at": CONSULTA,
            "record_id": None,
        },
    }
    base.update(cambios)
    return base


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


def _filas(db) -> list[DossierMediaMention]:
    return [o for o in db.added if isinstance(o, DossierMediaMention)]


def test_guarda_la_mencion_con_su_procedencia_completa():
    db = _FakeSession()
    dossier_id = uuid.uuid4()

    guardadas = escribir_menciones_prensa(db, dossier_id=dossier_id, menciones=[_mencion()], consulta="Acme Prueba")

    assert guardadas == 1
    [fila] = _filas(db)
    assert fila.dossier_id == dossier_id
    assert fila.title == "Acme Prueba abre una oficina en Lyon"
    assert fila.source_name == "Diario de Prueba"
    assert fila.url == "https://example.test/acme-lyon"
    assert fila.published_at == datetime(2026, 11, 1, 10, 0, tzinfo=UTC)
    assert fila.source_type == "news_api"
    assert fila.source_citation["retrieved_at"] == CONSULTA
    assert fila.query_context == "Acme Prueba"


def test_entiende_la_fecha_compacta_de_gdelt():
    db = _FakeSession()

    escribir_menciones_prensa(
        db, dossier_id=uuid.uuid4(), menciones=[_mencion(published_date="20261101T100000Z")], consulta="Acme"
    )

    assert _filas(db)[0].published_at == datetime(2026, 11, 1, 10, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    "incompleta",
    [
        _mencion(published_date=None),
        _mencion(published_date="fecha rara"),
        _mencion(headline="  "),
        _mencion(url=""),
        _mencion(publisher="Desconocido"),  # el agente usa ese valor cuando el proveedor no trae medio
        _mencion(source={"source_type": "news_api", "source_name": "news_api"}),  # sin fecha de consulta
    ],
)
def test_no_guarda_una_mencion_sin_sus_campos_de_procedencia(incompleta):
    db = _FakeSession()

    guardadas = escribir_menciones_prensa(
        db, dossier_id=uuid.uuid4(), menciones=[_mencion(), incompleta], consulta="Acme"
    )

    assert guardadas == 1
    assert len(_filas(db)) == 1


def test_sin_menciones_no_escribe_nada():
    db = _FakeSession()

    assert escribir_menciones_prensa(db, dossier_id=uuid.uuid4(), menciones=None, consulta="Acme") == 0
    assert db.added == []


def test_el_calendario_guarda_las_menciones_del_dossier_corporativo():
    from dossier.services.calendar_event_dossiers import persist_calendar_dossiers

    db = _FakeSession()
    result = {
        "reunion": {},
        "parse": {"tema": "Reunión con Acme Prueba", "company_corporate": "Acme Prueba"},
        "dossier_corporativo": "# Dossier corporativo\n\nResumen.",
        "dossier_personas": [],
        "errors": [],
        "corporate_cache_hit": False,
        "corporate_agents_failed": [],
        "corporate_telemetria": {
            "agents_failed": [],
            "agents_succeeded": ["agent_news", "synthesize_llm"],
            "agents_skipped": [],
            "fuentes_consultadas": [],
            "menciones_prensa": [_mencion()],
        },
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
    [fila] = _filas(db)
    assert fila.dossier_id == corp.id
    assert fila.query_context == "Acme Prueba"


def test_la_generacion_manual_guarda_las_menciones(monkeypatch):
    import dossier.llm.text_generate as llm
    import dossier.services.corporate_registry_context as ctx
    from dossier.api import dossier_routes as rutas
    from dossier.eu_registry.agent import ResultadoAgenteEuropeo
    from dossier.news.agent import ResultadoRecoleccionPrensa
    from dossier.schemas.dossier_executive_payload import PressMention
    from dossier.schemas.dossier_generation import CreateCorporateDossierRequest

    monkeypatch.setattr(ctx, "build_uk_corporate_context_markdown", lambda p: "## UK\n")
    monkeypatch.setattr(ctx, "build_us_corporate_context_markdown", lambda p: "## USA\n")
    monkeypatch.setattr("dossier.eu_registry.agent.run_eu_registry_agent", lambda n, **_: ResultadoAgenteEuropeo())
    monkeypatch.setattr(
        "dossier.news.agent.collect_press_mentions",
        lambda c, **_: ResultadoRecoleccionPrensa(mentions=[PressMention.model_validate(_mencion())]),
    )
    monkeypatch.setattr(llm, "generate_text_with_llm", lambda user, system_instruction=None: "# Dossier\n\nResumen.")
    monkeypatch.setenv("DOSSIER_CHARGE_CREDITS", "0")
    for nombre, valor in {
        "redis_corporate_cache_available": lambda: False,
        "get_corporate_cached_markdown": lambda key: None,
        "set_corporate_cached_markdown": lambda key, md: None,
        "run_with_corporate_cache_lock": lambda key, fn: fn(),
        "assert_corporate_dossier_allowed": lambda org: None,
        "assert_depth_allowed": lambda org, depth: None,
        "format_dossier_context_for_prompt": lambda org: "",
        "effective_output_language": lambda user, lang: "es",
    }.items():
        monkeypatch.setattr(rutas, nombre, valor)
    ctx_auth = SimpleNamespace(
        user=SimpleNamespace(id=uuid.uuid4()), org=SimpleNamespace(id=uuid.uuid4(), credits_balance=10, plan="pro")
    )
    db = _FakeSession()

    rutas.generate_corporate_dossier(CreateCorporateDossierRequest(subject_query="Acme Prueba"), ctx_auth, db)

    dossier = next(o for o in db.added if isinstance(o, Dossier))
    [fila] = _filas(db)
    assert fila.dossier_id == dossier.id
    assert fila.title == "Acme Prueba abre una oficina en Lyon"
