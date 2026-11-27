"""Tests - CHORE-2026-11-27-01: la prensa no puede frenar el dossier cuando GDELT está saturado.

Medido el 2026-11-27: GDELT tardaba 7 s en aceptar la conexión y 12-25 s en el TLS, y la
etapa de prensa se quedaba en el tope de 25 s en 7 de 9 dossiers de persona, casi siempre
sin resultados. Aquí se prueba el plazo total de la prensa y la pausa de una fuente que
falla seguido; el cliente HTTP (timeouts, espaciado de GDELT) está en test_news_client.py.
"""
from __future__ import annotations

import time

import pytest

import dossier.news.agent as agente
import dossier.news.client as cliente
from dossier.news.agent import collect_press_mentions
from dossier.news.client import LimiteProveedorNoticias, ProveedorNoticiasError


@pytest.fixture(autouse=True)
def _newsapi_con_clave(monkeypatch):
    monkeypatch.setenv("NEWS_API_KEY", "clave-de-prueba")


@pytest.fixture
def reloj(monkeypatch):
    """Reloj del agente controlado por la prueba (la pausa dura minutos)."""
    ahora = [5000.0]
    monkeypatch.setattr(agente, "_reloj", lambda: ahora[0])
    return ahora


def _nota():
    return [{"url": "https://medio.ejemplo.com/nota", "title": "Nota", "domain": "medio.ejemplo.com"}]


def _contar(llamadas: list[int], respuesta):
    def buscar(q, *, limite=10):
        llamadas.append(1)
        return respuesta(q, limite=limite)

    return buscar


def _caido(q, *, limite=10):
    raise ProveedorNoticiasError("Error al consultar GDELT: ConnectTimeout")


def _vacio(q, *, limite=10):
    return []


def _estado(resultado, clave):
    return next(f for f in resultado.fuentes if f.clave == clave)


# --------------------------------------------------------------------------
# Plazo total
# --------------------------------------------------------------------------


def test_el_tope_por_defecto_de_la_prensa_es_de_pocos_segundos():
    assert agente.TIEMPO_ESPERA_PROVEEDOR_SEG <= 8


def test_el_plazo_es_uno_para_todas_las_fuentes_no_uno_por_fuente(monkeypatch):
    def lenta(q, *, limite=10):
        time.sleep(0.6)
        return []

    monkeypatch.setattr(cliente, "search_gdelt_articles", lenta)
    monkeypatch.setattr(cliente, "search_newsapi_articles", lenta)

    inicio = time.perf_counter()
    resultado = collect_press_mentions("Ana Perez", timeout_seg=0.2)
    transcurrido = time.perf_counter() - inicio

    assert transcurrido < 0.35, f"esperó {transcurrido:.2f}s: el plazo se sumó por fuente"
    assert {f.provider for f in resultado.failed_providers} == {"gdelt_news", "news_api"}


# --------------------------------------------------------------------------
# Pausa de una fuente que falla seguido
# --------------------------------------------------------------------------


def test_tras_dos_fallos_seguidos_la_fuente_se_omite_sin_consultarla(monkeypatch, reloj):
    llamadas: list[int] = []
    monkeypatch.setattr(cliente, "search_gdelt_articles", _contar(llamadas, _caido))
    monkeypatch.setattr(cliente, "search_newsapi_articles", _vacio)

    collect_press_mentions("Ana Perez")
    collect_press_mentions("Ana Perez")
    resultado = collect_press_mentions("Ana Perez")

    assert len(llamadas) == 2
    gdelt = _estado(resultado, "gdelt_news")
    assert gdelt.estado == "error"
    assert gdelt.motivo == "provider_error"
    assert [f.provider for f in resultado.failed_providers] == ["gdelt_news"]
    assert _estado(resultado, "news_api").estado == "sin_resultados"


def test_la_pausa_vence_y_la_fuente_se_vuelve_a_consultar(monkeypatch, reloj):
    llamadas: list[int] = []
    monkeypatch.setattr(cliente, "search_gdelt_articles", _contar(llamadas, _caido))
    monkeypatch.setattr(cliente, "search_newsapi_articles", _vacio)

    collect_press_mentions("Ana Perez")
    collect_press_mentions("Ana Perez")
    reloj[0] += agente.PAUSA_FUENTE_SEG + 1
    collect_press_mentions("Ana Perez")

    assert len(llamadas) == 3


def test_una_respuesta_buena_reinicia_la_cuenta_de_fallos(monkeypatch, reloj):
    respuestas = [_caido, lambda q, *, limite=10: _nota(), _caido, _caido]
    llamadas: list[int] = []

    def buscar(q, *, limite=10):
        llamadas.append(1)
        return respuestas.pop(0)(q, limite=limite)

    monkeypatch.setattr(cliente, "search_gdelt_articles", buscar)
    monkeypatch.setattr(cliente, "search_newsapi_articles", _vacio)

    for _ in range(4):
        collect_press_mentions("Ana Perez")

    assert len(llamadas) == 4, "fallo, éxito, fallo: aún no son dos fallos seguidos"


def test_agotar_el_plazo_cuenta_como_fallo(monkeypatch, reloj):
    llamadas: list[int] = []

    def colgada(q, *, limite=10):
        llamadas.append(1)
        time.sleep(0.3)
        return []

    monkeypatch.setattr(cliente, "search_gdelt_articles", colgada)
    monkeypatch.setattr(cliente, "search_newsapi_articles", _vacio)

    collect_press_mentions("Ana Perez", timeout_seg=0.05)
    collect_press_mentions("Ana Perez", timeout_seg=0.05)
    resultado = collect_press_mentions("Ana Perez", timeout_seg=0.05)

    assert len(llamadas) == 2
    assert _estado(resultado, "gdelt_news").motivo == "provider_timeout"


def test_un_limite_del_proveedor_no_cuenta_como_fallo(monkeypatch, reloj):
    """El 429 (o el turno que el cliente omite por el intervalo de GDELT) no es una caída."""
    llamadas: list[int] = []

    def limitada(q, *, limite=10):
        llamadas.append(1)
        raise LimiteProveedorNoticias("GDELT: consulta reciente")

    monkeypatch.setattr(cliente, "search_gdelt_articles", limitada)
    monkeypatch.setattr(cliente, "search_newsapi_articles", _vacio)

    for _ in range(3):
        resultado = collect_press_mentions("Ana Perez")

    assert len(llamadas) == 3
    assert _estado(resultado, "gdelt_news").motivo == "provider_rate_limit"


def test_la_pausa_de_una_fuente_no_afecta_a_las_demas(monkeypatch, reloj):
    monkeypatch.setattr(cliente, "search_gdelt_articles", _caido)
    llamadas_newsapi: list[int] = []
    monkeypatch.setattr(
        cliente,
        "search_newsapi_articles",
        _contar(llamadas_newsapi, lambda q, *, limite=10: [{"url": "https://otro.ejemplo.com/n", "title": "Nota"}]),
    )

    for _ in range(3):
        resultado = collect_press_mentions("Ana Perez")

    assert len(llamadas_newsapi) == 3
    assert len(resultado.mentions) == 1
