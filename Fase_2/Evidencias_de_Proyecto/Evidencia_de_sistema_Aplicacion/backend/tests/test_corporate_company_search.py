"""Búsqueda de la empresa en el listado de la SEC antes de generar un dossier de calendario.

Informe final 2.6: «Lumière Logistique Démo SAS» terminaba como Canadian Pacific Kansas City,
porque la palabra suelta «SAS» aparece dentro de «Kansas». El dossier quedaba como «solo EE. UU.»
y se saltaba el registro europeo. Sin red: el listado de la SEC es un doble.
"""
from __future__ import annotations

import pytest

from dossier.services import calendar_event_dossiers as cal
from dossier.services import corporate_company_search as busqueda

FILAS = (
    {"cik_str": 16875, "ticker": "CP", "title": "CANADIAN PACIFIC KANSAS CITY LTD/CN"},
    {"cik_str": 1318605, "ticker": "TSLA", "title": "Tesla, Inc."},
    {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
    {"cik_str": 1000001, "ticker": "GMBX", "title": "GAMBIX HOLDINGS CORP"},
)


@pytest.fixture(autouse=True)
def listado_sec(monkeypatch):
    monkeypatch.setattr(busqueda, "_load_sec_company_rows", lambda: FILAS)


@pytest.mark.parametrize(
    "empresa",
    [
        "Lumière Logistique Démo SAS",
        "Andes Minería Ficticia SpA",
        "Bruma Consultores Ficticios Ltda",
        "Pacífico Datos Demo SA",
        "Werkzeug Beispiel GmbH",
        "Sas",
    ],
)
def test_una_forma_juridica_o_un_trozo_de_palabra_no_eligen_otra_empresa(empresa):
    assert busqueda.find_sec_matches(empresa, limit=5, estricto=True) == []


@pytest.mark.parametrize(
    ("consulta", "ticker"),
    [
        ("Tesla", "TSLA"),
        ("Tesla, Inc.", "TSLA"),
        ("tsla", "TSLA"),
        ("Reunión con Apple", "AAPL"),
        ("Demo de producto con Tesla", "TSLA"),
    ],
)
def test_las_empresas_de_la_sec_se_siguen_encontrando(consulta, ticker):
    hits = busqueda.find_sec_matches(consulta, limit=5, estricto=True)

    assert hits and hits[0]["ticker"] == ticker


def test_una_empresa_francesa_del_calendario_consulta_tambien_europa(monkeypatch):
    monkeypatch.setattr(cal, "find_companies_house_matches", lambda q, limit=5: ([], []))

    brief, alcance = cal.resolve_corporate_brief("Lumière Logistique Démo SAS")

    assert alcance == "dual"
    assert brief == "Lumière Logistique Démo SAS"


@pytest.mark.parametrize(("consulta", "ticker"), [("Tesl", "TSLA"), ("appl", "AAPL"), ("Kansas", "CP")])
def test_el_buscador_de_empresas_sigue_aceptando_parte_del_nombre(consulta, ticker):
    """Sin ``estricto`` el usuario elige de la lista: un trozo del nombre basta, como antes."""
    hits = busqueda.find_sec_matches(consulta, limit=5)

    assert hits and hits[0]["ticker"] == ticker


def test_el_agente_de_estados_unidos_no_toma_otra_empresa_por_la_forma_juridica():
    from dossier.services import corporate_registry_context as contexto

    cik, ticker, _ = contexto._resolve_sec_cik("Lumière Logistique Démo SAS")

    assert (cik, ticker) == (None, None)
