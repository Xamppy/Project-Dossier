"""Aviso de un dossier de persona sin perfiles: «no hay coincidencia» no es «PDL falló».

El detalle del dossier muestra un aviso cuando PDL no aporta perfiles. Cada causa
lleva su propio texto público, estable y sin detalle del proveedor.
"""
from __future__ import annotations

import pytest

from dossier.schemas.person_research import PersonResearchRequest
from dossier.services import pdl_research
from dossier.services.pdl_client import PdlApiError
from dossier.services.pdl_research import (
    PDL_FAILURE_WARNINGS,
    WARN_NO_PERSON_ENRICHMENT,
    fetch_pdl_profiles,
)

SECRETO = '{"error": {"type": "payment_required", "message": "detalle-interno-91c2"}}'


def _lanza(status: int):
    def _f(*_a, **_k):
        raise PdlApiError(status, SECRETO)

    return _f


def _sin_match(*_a, **_k):
    return None


def _search_vacio(*_a, **_k):
    return {"data": [], "total": 0}


def _buscar(monkeypatch, *, enrich=_sin_match, search=_search_vacio):
    class PdlFalso:
        def person_enrich(self, params):
            return enrich(params)

        def person_search(self, *, sql=None, query=None, size=5):
            return search(sql)

    monkeypatch.setattr(pdl_research, "PdlClient", PdlFalso)
    return fetch_pdl_profiles(
        PersonResearchRequest(
            full_name="Ana Prueba", company="Empresa de Prueba SA", email="ana@empresa.example"
        )
    )


@pytest.mark.parametrize("search", [_search_vacio, _lanza(404)])
def test_sin_coincidencias_avisa_que_no_hay_informacion(monkeypatch, search):
    perfiles, _, avisos = _buscar(monkeypatch, search=search)
    assert perfiles == []
    assert avisos == [WARN_NO_PERSON_ENRICHMENT]


def test_400_por_pocos_datos_no_es_una_falla_de_pdl(monkeypatch):
    _, _, avisos = _buscar(monkeypatch, enrich=_lanza(400), search=_lanza(404))
    assert avisos == [WARN_NO_PERSON_ENRICHMENT]


@pytest.mark.parametrize(
    ("status", "motivo"),
    [
        (401, "upstream_auth_failed"),
        (403, "upstream_auth_failed"),
        (402, "provider_quota"),
        (429, "provider_rate_limit"),
        (504, "provider_timeout"),
        (500, "provider_error"),
    ],
)
def test_si_pdl_falla_el_aviso_dice_el_motivo_real_una_sola_vez(monkeypatch, status, motivo):
    _, _, avisos = _buscar(monkeypatch, enrich=_lanza(status), search=_lanza(status))
    assert avisos == [PDL_FAILURE_WARNINGS[motivo]]


def test_creditos_agotados_en_enrich_con_search_sin_resultados_no_dice_que_no_hay_informacion(monkeypatch):
    # PDL responde 404 en search cuando no hay filas: eso no borra el 402 de enrich.
    _, _, avisos = _buscar(monkeypatch, enrich=_lanza(402), search=_lanza(404))
    assert avisos == [PDL_FAILURE_WARNINGS["provider_quota"]]


def test_una_falla_solo_en_search_tambien_se_informa(monkeypatch):
    _, _, avisos = _buscar(monkeypatch, search=_lanza(500))
    assert avisos == [PDL_FAILURE_WARNINGS["provider_error"]]


def test_sin_clave_configurada_avisa_sin_nombrar_la_variable(monkeypatch):
    def sin_clave():
        raise ValueError("Falta PDL_API_KEY en el entorno (.env).")

    monkeypatch.setattr(pdl_research, "PdlClient", sin_clave)
    perfiles, _, avisos = fetch_pdl_profiles(PersonResearchRequest(full_name="Ana Prueba"))
    assert perfiles == []
    assert avisos == [PDL_FAILURE_WARNINGS["configuration_missing"]]


def test_con_perfiles_de_enrich_una_falla_de_search_no_dice_que_no_hay_informacion(monkeypatch):
    persona = {"id": "pdl-1", "full_name": "Ana Prueba"}
    perfiles, _, avisos = _buscar(
        monkeypatch, enrich=lambda _p: {"likelihood": 9, "data": persona}, search=_lanza(402)
    )
    assert len(perfiles) == 1
    assert WARN_NO_PERSON_ENRICHMENT not in avisos
    assert len(avisos) == len(set(avisos))


def test_los_textos_son_publicos_y_distintos():
    from dossier.services.calendar_event_dossiers import _is_technical_warning

    textos = list(PDL_FAILURE_WARNINGS.values())
    assert len(set(textos)) == len(textos)
    for texto in textos:
        assert not _is_technical_warning(texto)
        assert "PDL" not in texto
        assert "detalle-interno" not in texto
