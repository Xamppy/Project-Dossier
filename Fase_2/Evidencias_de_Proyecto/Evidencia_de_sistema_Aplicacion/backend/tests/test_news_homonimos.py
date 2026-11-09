"""S3.3: filtro de homónimos de prensa (ADR 0004, criterio CA-B3.2).

Una mención solo entra al dossier si nombra al sujeto (todas sus palabras significativas,
como palabras completas) y, cuando hay contexto, al menos un término de ese contexto.
Ante la duda se descarta: un dossier sin noticias es preferible a uno con imputaciones falsas.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from dossier.graphs import corporate_dossier_graph as grafo
from dossier.news.agent import ResultadoRecoleccionPrensa, filtrar_homonimos
from dossier.schemas.dossier_executive_payload import PressMention, SourceCitation, SourceType

AHORA = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)


def _mencion(titular: str, resumen: str = "Resumen sin datos.", fuente: SourceType = SourceType.news_api) -> PressMention:
    return PressMention(
        headline=titular,
        publisher="Diario de Prueba",
        published_date="2026-11-01T10:00:00Z",
        summary=resumen,
        url=f"https://example.test/{abs(hash(titular))}",
        source=SourceCitation(source_type=fuente, source_name=fuente.value, retrieved_at=AHORA),
    )


def _titulares(menciones: list[PressMention]) -> list[str]:
    return [m.headline for m in menciones]


def test_conserva_la_mencion_que_nombra_a_la_empresa():
    menciones = [_mencion("Lumière Logistique abre un centro en Lyon")]

    conservadas, descartadas = filtrar_homonimos(menciones, "Lumière Logistique")

    assert _titulares(conservadas) == ["Lumière Logistique abre un centro en Lyon"]
    assert descartadas == 0


def test_descarta_la_mencion_que_no_nombra_a_la_empresa():
    menciones = [
        _mencion("Lumière Logistique abre un centro en Lyon"),
        _mencion("La logística europea crece en otoño"),
    ]

    conservadas, descartadas = filtrar_homonimos(menciones, "Lumière Logistique")

    assert _titulares(conservadas) == ["Lumière Logistique abre un centro en Lyon"]
    assert descartadas == 1


def test_ignora_la_forma_juridica_del_nombre_buscado():
    menciones = [_mencion("Lumière Logistique anuncia resultados")]

    conservadas, _ = filtrar_homonimos(menciones, "Lumière Logistique SAS")

    assert len(conservadas) == 1


def test_no_confunde_palabras_que_solo_contienen_el_nombre():
    menciones = [_mencion("Novartis compra una biotecnológica"), _mencion("Nova Prueba firma un contrato")]

    conservadas, descartadas = filtrar_homonimos(menciones, "Nova Prueba")

    assert _titulares(conservadas) == ["Nova Prueba firma un contrato"]
    assert descartadas == 1


def test_no_distingue_mayusculas_ni_tildes():
    menciones = [_mencion("LUMIERE LOGISTIQUE sube en bolsa")]

    conservadas, _ = filtrar_homonimos(menciones, "Lumière Logistique")

    assert len(conservadas) == 1


def test_nombre_comun_sin_contexto_relacionado_se_descarta():
    """CA-B3.2: el artículo nombra a la persona pero no a su organización, cargo ni sector."""
    menciones = [
        _mencion("Juan Pérez gana la maratón de la ciudad"),
        _mencion("Juan Pérez, gerente de Empresa Ficticia, presenta su plan"),
    ]

    conservadas, descartadas = filtrar_homonimos(
        menciones, "Juan Pérez", contexto=["Empresa Ficticia", "gerente"]
    )

    assert _titulares(conservadas) == ["Juan Pérez, gerente de Empresa Ficticia, presenta su plan"]
    assert descartadas == 1


def test_el_contexto_tambien_se_busca_en_el_resumen():
    menciones = [_mencion("Juan Pérez asume nuevo cargo", resumen="El ejecutivo deja Empresa Ficticia.")]

    conservadas, _ = filtrar_homonimos(menciones, "Juan Pérez", contexto=["Empresa Ficticia"])

    assert len(conservadas) == 1


def test_en_gdelt_no_cuenta_el_resumen_armado_con_el_dominio():
    """GDELT no trae resumen: el agente arma uno con el dominio, que no prueba nada."""
    menciones = [
        _mencion(
            "Resultados trimestrales del sector",
            resumen="Mencion de prensa en lumiere-logistique.example: Resultados trimestrales del sector",
            fuente=SourceType.gdelt_news,
        )
    ]

    conservadas, descartadas = filtrar_homonimos(menciones, "Lumière Logistique")

    assert conservadas == []
    assert descartadas == 1


@pytest.mark.parametrize("sujeto", ["", "SAS", "  "])
def test_sin_palabras_significativas_no_se_puede_decidir_y_se_descarta_todo(sujeto):
    conservadas, descartadas = filtrar_homonimos([_mencion("Cualquier titular")], sujeto)

    assert conservadas == []
    assert descartadas == 1


def test_el_nodo_de_prensa_solo_pasa_al_informe_las_menciones_del_sujeto(monkeypatch):
    monkeypatch.setattr(
        "dossier.news.agent.collect_press_mentions",
        lambda consulta, **_: ResultadoRecoleccionPrensa(
            mentions=[_mencion("Acme Prueba cierra una ronda"), _mencion("Otra empresa cualquiera crece")]
        ),
    )

    salida = grafo._node_agent_news({"jurisdiction_scope": "dual", "empresa_objetivo": "Acme Prueba"})

    assert "Acme Prueba cierra una ronda" in salida["news_context"]
    assert "Otra empresa cualquiera crece" not in salida["news_context"]
    assert _titulares(salida["menciones_prensa"]) == ["Acme Prueba cierra una ronda"]


def test_si_todas_son_homonimas_el_nodo_informa_que_no_hay_menciones(monkeypatch):
    monkeypatch.setattr(
        "dossier.news.agent.collect_press_mentions",
        lambda consulta, **_: ResultadoRecoleccionPrensa(mentions=[_mencion("Otra empresa cualquiera crece")]),
    )

    salida = grafo._node_agent_news({"jurisdiction_scope": "dual", "empresa_objetivo": "Acme Prueba"})

    assert "Sin menciones de prensa recientes" in salida["news_context"]
    assert salida["menciones_prensa"] == []
    assert salida["agents_succeeded"] == ["agent_news"]


# --- Nombres oficiales del registro (revisión del PR #49) ---------------------------------
# La empresa objetivo suele ser el título de Companies House o de la SEC, con puntos,
# sufijos de estado y palabras genéricas que la prensa omite. Nombres ficticios.


@pytest.mark.parametrize(
    ("titulo_registro", "titular"),
    [
        ("BX P.L.C.", "BX shares jump after results"),
        ("Ficticia Platforms, Inc.", "Ficticia fined by EU regulators"),
        ("FICTICIA COM INC", "Ficticia opens a new warehouse"),
        ("PRUEBA HOLDINGS PLC", "Prueba posts record profit"),
        ("NORTE SUR & COMPANY/MN", "Norte Sur settles lawsuit"),
        ("PRUEBA HOLDING N.V.", "Prueba wins a chip order"),
        ("Ficticia Aktiengesellschaft", "Ficticia cuts jobs"),
        ("CISCO PRUEBA SYSTEMS, INC.", "Cisco Prueba reports earnings"),
        ("Acme Prueba Group S.A.", "Acme Prueba compra una rival"),
    ],
)
def test_conserva_la_noticia_aunque_el_titular_omita_lo_generico_del_nombre(titulo_registro, titular):
    conservadas, descartadas = filtrar_homonimos([_mencion(titular)], titulo_registro)

    assert _titulares(conservadas) == [titular]
    assert descartadas == 0


def test_lo_distintivo_del_nombre_sigue_siendo_obligatorio():
    menciones = [_mencion("Platforms see record growth"), _mencion("Holdings fall on Wall Street")]

    conservadas, descartadas = filtrar_homonimos(menciones, "Ficticia Platforms Holdings, Inc.")

    assert conservadas == []
    assert descartadas == 2


def test_el_nodo_entrega_solo_las_menciones_que_llegan_al_informe(monkeypatch):
    muchas = [_mencion(f"Acme Prueba noticia {i}") for i in range(grafo.MAX_MENCIONES_PROMPT + 5)]
    monkeypatch.setattr(
        "dossier.news.agent.collect_press_mentions",
        lambda consulta, **_: ResultadoRecoleccionPrensa(mentions=muchas),
    )

    salida = grafo._node_agent_news({"jurisdiction_scope": "dual", "empresa_objetivo": "Acme Prueba"})

    assert len(salida["menciones_prensa"]) == grafo.MAX_MENCIONES_PROMPT
