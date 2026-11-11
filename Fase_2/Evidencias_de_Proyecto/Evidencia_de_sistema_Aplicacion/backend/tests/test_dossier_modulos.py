"""S5.5/S3.5/S3.6 · ``modules`` del detalle del dossier (unitarias, sin base de datos).

Ver specs/proposals/S5.5-dossier-por-modulos.md. Integración y aislamiento en
tests/integration/test_dossier_modulos_integracion.py y
tests/security/test_dossier_modulos_seguridad.py.
"""
from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from dossier.services.corporate_dossier_telemetry import columnas_telemetria, telemetria_de
from dossier.services.dossier_modules import (
    MAX_MENCIONES,
    modulos_del_dossier,
    url_segura,
)

AHORA = datetime(2026, 11, 11, 12, 0, tzinfo=UTC).isoformat()


def registro(razon: str = "Acme France SAS", **extra) -> dict:
    return {
        "record": {
            "jurisdiccion": "fr",
            "fuente": "recherche-entreprises",
            "identificador_registro": "123456789",
            "razon_social": razon,
            "estado": "active",
            "url_fuente": "https://annuaire-entreprises.data.gouv.fr/entreprise/123456789",
            "datos_brutos": {"secreto": "x" * 50},
            **extra,
        },
        "source": {
            "source_type": "eu_registry",
            "source_name": "recherche-entreprises",
            "retrieved_at": AHORA,
            "record_id": "123456789",
            "url": "https://recherche-entreprises.api.gouv.fr/search?q=acme",
        },
    }


def mencion(titular: str = "Acme abre oficina", url: str = "https://diario.example/nota") -> dict:
    return {
        "headline": titular,
        "publisher": "Diario",
        "published_date": "2026-11-01",
        "summary": "Resumen.",
        "url": url,
        "source": {"source_type": "gdelt_news", "source_name": "GDELT DOC 2.0", "retrieved_at": AHORA},
    }


def fila(titulo: str = "Titular de fila", **extra) -> SimpleNamespace:
    base = {
        "title": titulo,
        "url": "https://medio.example/a",
        "source_name": "Medio",
        "published_at": datetime(2026, 10, 30, 8, 0, tzinfo=UTC),
        "summary": "Resumen de fila.",
        "source_citation": {"source_type": "news_api", "source_name": "NewsAPI", "retrieved_at": AHORA},
    }
    base.update(extra)
    return SimpleNamespace(**base)


@pytest.mark.parametrize(
    ("url", "esperado"),
    [
        ("https://a.example/x", "https://a.example/x"),
        ("http://a.example", "http://a.example"),
        ("  https://a.example/y  ", "https://a.example/y"),
        ("javascript:alert(1)", None),
        ("JAVASCRIPT:alert(1)", None),
        ("data:text/html,hola", None),
        ("//a.example", None),
        ("ftp://a.example", None),
        ("https://", None),
        ("", None),
        (None, None),
        (123, None),
    ],
)
def test_url_segura(url, esperado):
    assert url_segura(url) == esperado


def test_sin_datos_devuelve_listas_vacias():
    assert modulos_del_dossier(None, None, []) == {"corporate_records": [], "press_mentions": []}
    assert modulos_del_dossier({"format": "markdown", "body": "# x"}, None, []) == {
        "corporate_records": [],
        "press_mentions": [],
    }


def test_registros_desde_modulos_sin_datos_brutos():
    data = {"modulos": {"registros_europeos": [registro()]}}
    salida = modulos_del_dossier(data, None, [])["corporate_records"]
    assert len(salida) == 1
    assert salida[0]["record"]["razon_social"] == "Acme France SAS"
    assert "datos_brutos" not in salida[0]["record"]
    assert salida[0]["source"]["source_type"] == "eu_registry"


def test_registros_del_contrato_tienen_prioridad():
    payload = {"corporate_records": [registro("Del contrato")]}
    data = {"modulos": {"registros_europeos": [registro("De modulos")]}}
    salida = modulos_del_dossier(data, payload, [])["corporate_records"]
    assert [r["record"]["razon_social"] for r in salida] == ["Del contrato"]


def test_contrato_sin_registros_cae_a_modulos():
    data = {"modulos": {"registros_europeos": [registro("De modulos")]}}
    salida = modulos_del_dossier(data, {"corporate_records": []}, [])["corporate_records"]
    assert [r["record"]["razon_social"] for r in salida] == ["De modulos"]


def test_registro_invalido_se_descarta_sin_fallar():
    data = {
        "modulos": {
            "registros_europeos": [
                {"record": {"razon_social": "Sin jurisdicción"}},
                "texto",
                None,
                registro("Válido"),
            ]
        }
    }
    salida = modulos_del_dossier(data, None, [])["corporate_records"]
    assert [r["record"]["razon_social"] for r in salida] == ["Válido"]


@pytest.mark.parametrize("modulos", ["x", 1, ["a"], {"registros_europeos": "no-lista"}])
def test_modulos_con_forma_inesperada_no_fallan(modulos):
    assert modulos_del_dossier({"modulos": modulos}, None, [])["corporate_records"] == []


def test_urls_peligrosas_del_registro_se_anulan():
    malo = registro(url_fuente="javascript:alert(1)", presentaciones=[{"url": "javascript:x", "tipo": "acta"}])
    malo["source"]["url"] = "data:text/html,x"
    salida = modulos_del_dossier({"modulos": {"registros_europeos": [malo]}}, None, [])["corporate_records"][0]
    assert salida["record"]["url_fuente"] is None
    assert salida["record"]["presentaciones"][0]["url"] is None
    assert salida["source"]["url"] is None


def test_menciones_del_contrato_tienen_prioridad_sobre_las_filas():
    salida = modulos_del_dossier({}, {"press_mentions": [mencion()]}, [fila()])["press_mentions"]
    assert [m["headline"] for m in salida] == ["Acme abre oficina"]
    assert salida[0]["source"]["source_type"] == "gdelt_news"


def test_menciones_desde_filas():
    salida = modulos_del_dossier({}, None, [fila()])["press_mentions"]
    assert salida == [
        {
            "headline": "Titular de fila",
            "publisher": "Medio",
            "published_date": "2026-10-30",
            "summary": "Resumen de fila.",
            "url": "https://medio.example/a",
            "source": {
                "source_type": "news_api",
                "source_name": "NewsAPI",
                "url": None,
                "retrieved_at": "2026-11-11T12:00:00Z",
                "record_id": None,
            },
        }
    ]


def test_fila_con_cita_invalida_queda_sin_fuente_y_sin_titular_se_descarta():
    salida = modulos_del_dossier(
        {},
        None,
        [fila(source_citation={"basura": 1}, published_at=None, source_name=None, summary=None), fila(title="  ")],
    )["press_mentions"]
    assert len(salida) == 1
    assert salida[0]["source"] is None
    assert salida[0]["publisher"] == ""
    assert salida[0]["published_date"] is None
    assert salida[0]["summary"] == ""


def test_url_peligrosa_de_una_mencion_se_anula_pero_la_mencion_queda():
    salida = modulos_del_dossier({}, {"press_mentions": [mencion(url="javascript:alert(1)")]}, [])["press_mentions"]
    assert salida[0]["url"] is None
    salida = modulos_del_dossier({}, None, [fila(url="vbscript:x")])["press_mentions"]
    assert salida[0]["url"] is None


def test_menciones_con_tope():
    filas = [fila(f"T{i}") for i in range(MAX_MENCIONES + 30)]
    assert len(modulos_del_dossier({}, None, filas)["press_mentions"]) == MAX_MENCIONES


# --- Telemetría del grafo corporativo (CA1) -----------------------------------


def _cita_obj():
    from dossier.schemas.dossier_executive_payload import CorporateRecordCitation

    return CorporateRecordCitation(**registro())


def test_la_telemetria_lleva_los_registros_europeos_sin_datos_brutos():
    generado = SimpleNamespace(registros_europeos=[_cita_obj()])
    tele = telemetria_de(generado)
    assert tele["registros_europeos"][0]["record"]["razon_social"] == "Acme France SAS"
    assert "datos_brutos" not in tele["registros_europeos"][0]["record"]


def test_columnas_de_telemetria_guardan_los_modulos_en_dossier_data():
    tele = telemetria_de(SimpleNamespace(registros_europeos=[_cita_obj()]))
    datos = columnas_telemetria(tele, es_error=False)["dossier_data"]
    assert datos["modulos"]["registros_europeos"][0]["record"]["identificador_registro"] == "123456789"


def test_sin_telemetria_no_se_inventan_modulos():
    assert "modulos" not in columnas_telemetria(None, es_error=False)["dossier_data"]


def test_telemetria_antigua_sin_registros_no_falla():
    tele = telemetria_de(SimpleNamespace())
    assert tele["registros_europeos"] == []
    datos = columnas_telemetria({"agents_failed": []}, es_error=False)["dossier_data"]
    assert datos["modulos"] == {"registros_europeos": []}
