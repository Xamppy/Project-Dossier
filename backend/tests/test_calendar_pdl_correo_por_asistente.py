"""BUG-2026-10-19-02 · Calendario consultaba PDL con el correo de otro asistente.

En una reunión con varios asistentes, al que no declaraba correo propio se le
asignaba el primer correo corporativo del evento (el de otro asistente) y PDL
se consultaba con ``{"email": "ana@example.com"}`` para Beto.

Sin base de datos ni red: el cliente de PDL es un doble que registra los
parámetros de cada llamada y a qué asistente se estaba investigando. El resto
del pipeline de persona (estrategias de enrich, búsqueda SQL) es el real.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

import pytest

from dossier.graphs.corporate_dossier_graph import CorporateDossierResult
from dossier.services import calendar_event_dossiers as cal
from dossier.services import pdl_research, person_research_service

CORREO_ANA = "ana@example.com"
CORREO_BETO = "beto@ejemplo-ficticio.com"


def _reunion(descripcion: str, participantes: str = "") -> dict[str, Any]:
    return {
        "tema": "Kick-off con Empresa de Prueba SA",
        "descripcion": descripcion,
        "participantes": participantes,
        "inicio": "2026-10-20T10:00:00Z",
    }


@pytest.fixture
def pdl(monkeypatch):
    """PDL simulado que registra (asistente investigado, tipo, parámetros) de cada llamada."""
    estado: dict[str, Any] = {"actual": None, "llamadas": []}

    class PdlQueRegistra:
        def __init__(self, *_a, **_k):
            pass

        def person_enrich(self, params):
            estado["llamadas"].append((estado["actual"], "enrich", dict(params)))
            return None

        def person_search(self, **kwargs):
            estado["llamadas"].append((estado["actual"], "search", dict(kwargs)))
            return {"data": [], "total": 0}

    investigar_real = cal.run_person_research

    def investigar(req, **kwargs):
        estado["actual"] = req.full_name
        try:
            return investigar_real(req, **kwargs)
        finally:
            estado["actual"] = None

    monkeypatch.setattr(pdl_research, "PdlClient", PdlQueRegistra)
    monkeypatch.setattr(cal, "run_person_research", investigar)
    monkeypatch.setattr(person_research_service, "deepseek_api_key", lambda: "")
    monkeypatch.setattr(cal, "redis_person_cache_available", lambda: False)
    monkeypatch.setattr(cal, "redis_corporate_cache_available", lambda: False)
    monkeypatch.setattr(
        cal,
        "run_corporate_dossier_langgraph_detailed",
        lambda **_: CorporateDossierResult(markdown="# Dossier corporativo\n\nResumen.", agents_failed=[], agents_succeeded=[]),
    )
    monkeypatch.setattr(cal, "resolve_corporate_brief", lambda q: (q, "dual"))
    monkeypatch.setenv("PERSON_RESEARCH_PROVIDER", "pdl")
    monkeypatch.setenv("DEEPSEEK_DISABLE_PERSON_WEB", "1")
    return estado


def _generar(reunion):
    return cal.generate_dossiers_from_calendar_event(reunion, organization_id=uuid.uuid4(), organization_plan="pro")


def _llamadas_de(pdl, nombre):
    return [(tipo, params) for quien, tipo, params in pdl["llamadas"] if quien == nombre]


def _correos_en_enrich(pdl, nombre):
    return {params["email"] for tipo, params in _llamadas_de(pdl, nombre) if tipo == "enrich" and "email" in params}


def test_cada_asistente_se_consulta_en_pdl_con_su_propio_correo(pdl):
    reunion = _reunion(
        "Empresa: Empresa de Prueba SA\n"
        f"Contacto 1: Ana Prueba\nCargo 1: Directora general\nEmail 1: {CORREO_ANA}\n"
        f"Contacto 2: Beto Ficticio\nCargo 2: Gerente\nEmail 2: {CORREO_BETO}"
    )

    _generar(reunion)

    assert _correos_en_enrich(pdl, "Ana Prueba") == {CORREO_ANA}
    assert _correos_en_enrich(pdl, "Beto Ficticio") == {CORREO_BETO}


def test_asistente_sin_correo_no_hereda_el_de_otro_asistente(pdl):
    """El caso de la demo de S5.4: Ana declara correo, Beto no."""
    reunion = _reunion(
        "Empresa: Empresa de Prueba SA\n"
        f"Contacto 1: Ana Prueba\nCargo 1: Directora general\nEmail 1: {CORREO_ANA}\n"
        "Contacto 2: Beto Ficticio\nCargo 2: Gerente",
        participantes=CORREO_ANA,
    )

    item = _generar(reunion)

    llamadas_beto = _llamadas_de(pdl, "Beto Ficticio")
    assert llamadas_beto, "Beto se investiga en PDL por nombre y empresa"
    assert CORREO_ANA not in json.dumps(llamadas_beto).lower()
    assert any("beto" in json.dumps(params).lower() for _, params in llamadas_beto)
    assert _correos_en_enrich(pdl, "Ana Prueba") == {CORREO_ANA}
    beto = next(p for p in item["dossier_personas"] if p["full_name"] == "Beto Ficticio")
    assert beto["email"] is None


def test_con_varios_asistentes_un_correo_de_participantes_no_se_asigna_a_nadie(pdl):
    """Un correo suelto en participantes no dice de quién es: no se usa para ninguno."""
    reunion = _reunion(
        "Empresa: Empresa de Prueba SA\n"
        "Contacto 1: Ana Prueba\nCargo 1: Directora general\n"
        "Contacto 2: Beto Ficticio\nCargo 2: Gerente",
        participantes=CORREO_ANA,
    )

    _generar(reunion)

    assert _correos_en_enrich(pdl, "Beto Ficticio") == set()
    assert CORREO_ANA not in json.dumps(_llamadas_de(pdl, "Beto Ficticio")).lower()


def test_un_solo_asistente_sigue_usando_el_correo_corporativo_del_evento(pdl):
    """Comportamiento previo que se conserva: con un único contacto el correo es suyo."""
    reunion = _reunion(
        "Empresa: Empresa de Prueba SA\nContacto: Ana Prueba\nCargo: Directora general",
        participantes=CORREO_ANA,
    )

    _generar(reunion)

    assert _correos_en_enrich(pdl, "Ana Prueba") == {CORREO_ANA}
