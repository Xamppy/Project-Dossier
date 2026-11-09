"""S2.6: pruebas de contraste entre jurisdicciones sobre casos fijos.

Criterio del plan: un conjunto de pruebas que cubre una empresa por jurisdicción más los
casos de empresa no encontrada y de datos incompletos. Cada caso parte de la respuesta
cruda del proveedor (Companies House, SEC EDGAR, Recherche d'entreprises y
Handelsregister/OffeneRegister) y comprueba que las cuatro llegan al mismo contrato
(``CorporateRecordCitation``): jurisdicción, identificador, razón social y una cita con
proveedor, URL pública y fecha de consulta (CA-B1.2).

Datos ficticios: ninguna de estas empresas existe.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from dossier.companies_house.converters import perfil_a_registro_corporativo
from dossier.eu_registry import agent as agente_europeo
from dossier.eu_registry.mapper import mapear_registro_aleman, mapear_registro_frances
from dossier.graphs import corporate_dossier_graph as grafo
from dossier.schemas.corporate_registry import JurisdiccionRegistro
from dossier.schemas.dossier_executive_payload import CorporateRecordCitation, SourceType
from dossier.sec_edgar.converters import submissions_a_registro_corporativo

CONSULTA = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)

# --- Respuestas crudas fijas, una por jurisdicción ---------------------------------------

UK_PERFIL = {
    "company_number": "00000001",
    "company_name": "ACME PRUEBA LIMITED",
    "company_status": "active",
    "type": "ltd",
    "date_of_creation": "2001-02-03",
    "registered_office_address": {"address_line_1": "1 Calle Ficticia", "locality": "London", "country": "England"},
    "sic_codes": ["62020"],
    "links": {"self": "/company/00000001"},
}

US_SUBMISSIONS = {
    "cik": "0000000001",
    "name": "ACME PRUEBA INC",
    "sic": "7372",
    "filings": {
        "recent": {
            "form": ["10-K"],
            "filingDate": ["2026-02-01"],
            "accessionNumber": ["0000000001-26-000001"],
            "primaryDocument": ["acme-10k.htm"],
        }
    },
}

FR_RECHERCHE = {
    "siren": "900000001",
    "nom_complet": "ACME PRUEBA SAS",
    "etat_administratif": "A",
    "nature_juridique": "5710",
    "date_creation": "2010-05-06",
    "activite_principale": "62.01Z",
    "siege": {"adresse": "1 Rue Fictive", "libelle_commune": "LYON", "code_postal": "69001"},
    "dirigeants": [{"nom": "Persona Ficticia", "qualite": "Président de SAS"}],
}

DE_OFFENEREGISTER = {
    "company_number": "K1101R_HRB000001",
    "name": "Acme Prueba GmbH",
    "current_status": "currently registered",
    "company_type": "Gesellschaft mit beschränkter Haftung",
    "registered_address_in_full": "Fiktivstraße 1, 10115 Berlin",
    "opencorporates_url": "https://opencorporates.com/companies/de/K1101R_HRB000001",
}


def _cita_eu(jurisdiccion: JurisdiccionRegistro, fila: dict) -> CorporateRecordCitation:
    """Mismo camino que el agente: mapeo y cita de origen (``_consultar_pais``)."""
    fuente = agente_europeo._FUENTES[jurisdiccion]
    return agente_europeo._consultar_pais(
        agente_europeo._FuenteEuropea(buscar=lambda n, limite: [fila], mapear=fuente.mapear, nombre_fuente=fuente.nombre_fuente),
        "Acme Prueba",
        5,
    )[0][0]


def _citas_por_jurisdiccion() -> dict[str, CorporateRecordCitation]:
    return {
        "uk": perfil_a_registro_corporativo(UK_PERFIL, consultado_en=CONSULTA),
        "us": submissions_a_registro_corporativo(US_SUBMISSIONS, "1", consultado_en=CONSULTA),
        "fr": _cita_eu(JurisdiccionRegistro.fr, FR_RECHERCHE),
        "de": _cita_eu(JurisdiccionRegistro.de, DE_OFFENEREGISTER),
    }


# --- Una empresa por jurisdicción: el mismo contrato -------------------------------------


@pytest.mark.parametrize(
    ("jurisdiccion", "identificador", "razon_social", "tipo_fuente"),
    [
        ("uk", "00000001", "ACME PRUEBA LIMITED", SourceType.companies_house),
        ("us", "0000000001", "ACME PRUEBA INC", SourceType.sec_edgar),
        ("fr", "900000001", "ACME PRUEBA SAS", SourceType.eu_registry),
        ("de", "K1101R_HRB000001", "Acme Prueba GmbH", SourceType.eu_registry),
    ],
)
def test_cada_jurisdiccion_llega_al_mismo_contrato(jurisdiccion, identificador, razon_social, tipo_fuente):
    cita = _citas_por_jurisdiccion()[jurisdiccion]

    assert cita.record.jurisdiccion.value == jurisdiccion
    assert cita.record.identificador_registro == identificador
    assert cita.record.razon_social == razon_social
    assert cita.source.source_type == tipo_fuente
    assert cita.source.record_id == identificador
    assert cita.source.retrieved_at is not None
    # CA-B1.2: cada dato estructurado cita una URL pública verificable.
    assert cita.source.url and cita.source.url.startswith("https://")


def test_francia_cita_la_ficha_publica_del_anuario_de_empresas():
    """Hallazgo del contraste: el registro francés era el único sin URL pública."""
    cita = _citas_por_jurisdiccion()["fr"]

    assert cita.source.url == "https://annuaire-entreprises.data.gouv.fr/entreprise/900000001"
    assert cita.record.url_fuente == cita.source.url


def test_los_cuatro_identificadores_no_se_confunden_entre_jurisdicciones():
    citas = _citas_por_jurisdiccion()

    claves = {(c.record.jurisdiccion.value, c.record.identificador_registro) for c in citas.values()}

    assert len(claves) == 4


@pytest.mark.parametrize("jurisdiccion", ["uk", "fr", "de"])
def test_jurisdicciones_con_estado_y_domicilio_los_informan(jurisdiccion):
    """SEC EDGAR no entrega estado ni domicilio (tabla de S1.9); las otras tres sí."""
    registro = _citas_por_jurisdiccion()[jurisdiccion].record

    assert registro.estado
    assert registro.domicilio is not None


# --- Empresa no encontrada (CA-B2.3) -----------------------------------------------------


def test_empresa_no_encontrada_en_europa_no_lanza_y_queda_como_consultada_sin_hallazgos(monkeypatch):
    monkeypatch.setattr(agente_europeo, "search_france_companies", lambda q, limite=5: [])
    monkeypatch.setattr(agente_europeo, "search_germany_companies", lambda q, limite=5: [])

    salida = grafo._node_agent_corporate_eu({"jurisdiction_scope": "dual", "empresa_objetivo": "Inexistente Prueba"})

    assert salida["agents_succeeded"] == ["agent_corporate_eu"]
    assert "Sin coincidencias" in salida["eu_corporate_context"]
    assert {f["jurisdiccion"]: f["resultado"] for f in salida["fuentes_consultadas"]} == {
        "fr": "sin_resultados",
        "de": "sin_resultados",
    }


def test_homonimo_europeo_con_otra_razon_social_no_entra_al_informe(monkeypatch):
    otra = {**FR_RECHERCHE, "siren": "900000002", "nom_complet": "BETA FICTICIA SAS"}
    monkeypatch.setattr(agente_europeo, "search_france_companies", lambda q, limite=5: [otra])
    monkeypatch.setattr(agente_europeo, "search_germany_companies", lambda q, limite=5: [])

    salida = grafo._node_agent_corporate_eu({"jurisdiction_scope": "dual", "empresa_objetivo": "Acme Prueba"})

    assert "BETA FICTICIA" not in salida["eu_corporate_context"]
    assert {f["jurisdiccion"]: f["resultado"] for f in salida["fuentes_consultadas"]}["fr"] == "sin_resultados"


# --- Datos incompletos ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("convertir", "jurisdiccion"),
    [
        (lambda: perfil_a_registro_corporativo({"company_number": "00000002", "company_name": "ACME"}), "uk"),
        (lambda: submissions_a_registro_corporativo({"cik": "2", "name": "ACME"}, "2"), "us"),
        (lambda: mapear_registro_frances({"siren": "900000003", "nom_complet": "ACME"}), "fr"),
        (lambda: mapear_registro_aleman({"company_number": "HRB2", "name": "ACME"}), "de"),
    ],
)
def test_datos_incompletos_se_aceptan_sin_inventar_campos(convertir, jurisdiccion):
    resultado = convertir()
    registro = getattr(resultado, "record", resultado)

    assert registro.jurisdiccion.value == jurisdiccion
    assert registro.razon_social == "ACME"
    assert registro.fecha_constitucion is None
    assert registro.directivos == []


def test_registro_frances_incompleto_entra_al_informe_sin_domicilio_ni_directivos(monkeypatch):
    monkeypatch.setattr(
        agente_europeo, "search_france_companies", lambda q, limite=5: [{"siren": "900000004", "nom_complet": "ACME PRUEBA"}]
    )
    monkeypatch.setattr(agente_europeo, "search_germany_companies", lambda q, limite=5: [])

    contexto = grafo._node_agent_corporate_eu({"jurisdiction_scope": "dual", "empresa_objetivo": "Acme Prueba"})[
        "eu_corporate_context"
    ]

    assert "ACME PRUEBA" in contexto and "900000004" in contexto
    assert "Domicilio" not in contexto and "Directivos" not in contexto
