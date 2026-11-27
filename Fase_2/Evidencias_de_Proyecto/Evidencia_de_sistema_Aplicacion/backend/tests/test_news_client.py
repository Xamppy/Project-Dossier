"""Tests - S3.1: cliente HTTP del proveedor de noticias (GDELT, NewsAPI).

Solo el cliente HTTP (fetch + parseo del JSON crudo). Deduplicar, filtrar
homonimos (S3.3) y registrar procedencia (S3.4) es responsabilidad de S3.2.
"""
from __future__ import annotations

import pytest

import dossier.news.client as client
from dossier.news.client import (
    ProveedorNoticiasError,
    search_gdelt_articles,
    search_newsapi_articles,
)


def test_busca_en_gdelt_devuelve_articles(monkeypatch, respuesta_fija):
    payload = {
        "articles": [
            {"url": "https://ejemplo.com/nota", "title": "Nota", "seendate": "20260910"}
        ]
    }

    def fake_get(url, params=None, timeout=None):
        assert url == client.GDELT_SEARCH_URL
        assert params["query"] == '"Ana Perez" AND "Acme"'
        assert params["timespan"] == "30d"
        return respuesta_fija(payload)

    monkeypatch.setattr(client.requests, "get", fake_get)
    assert search_gdelt_articles('"Ana Perez" AND "Acme"') == payload["articles"]


def test_busca_en_gdelt_query_vacia_no_llama_a_la_red(monkeypatch):
    def fake_get(*args, **kwargs):
        raise AssertionError("no deberia llamar a la red con query vacia")

    monkeypatch.setattr(client.requests, "get", fake_get)
    assert search_gdelt_articles("   ") == []


def test_busca_en_gdelt_error_http_se_traduce(monkeypatch, respuesta_fija):
    def fake_get(*args, **kwargs):
        return respuesta_fija({"error": "boom"}, status=500)

    monkeypatch.setattr(client.requests, "get", fake_get)
    with pytest.raises(ProveedorNoticiasError):
        search_gdelt_articles("Ana Perez")


def test_busca_en_gdelt_forma_inesperada_es_error(monkeypatch, respuesta_fija):
    def fake_get(*args, **kwargs):
        return respuesta_fija(["no", "es", "un", "objeto"])

    monkeypatch.setattr(client.requests, "get", fake_get)
    with pytest.raises(ProveedorNoticiasError):
        search_gdelt_articles("Ana Perez")


def test_busca_en_newsapi_devuelve_articles(monkeypatch, respuesta_fija):
    monkeypatch.setenv("NEWS_API_KEY", "clave-de-prueba")
    payload = {"status": "ok", "articles": [{"title": "Nota", "url": "https://ejemplo.com"}]}

    def fake_get(url, params=None, headers=None, timeout=None):
        assert url == client.NEWSAPI_SEARCH_URL
        assert params["q"] == "Ana Perez"
        assert "apiKey" not in params
        assert headers["X-Api-Key"] == "clave-de-prueba"
        return respuesta_fija(payload)

    monkeypatch.setattr(client.requests, "get", fake_get)
    assert search_newsapi_articles("Ana Perez") == payload["articles"]


def test_busca_en_newsapi_sin_clave_configurada_es_error(monkeypatch):
    monkeypatch.delenv("NEWS_API_KEY", raising=False)

    def fake_get(*args, **kwargs):
        raise AssertionError("no deberia llamar a la red sin NEWS_API_KEY")

    monkeypatch.setattr(client.requests, "get", fake_get)
    with pytest.raises(ProveedorNoticiasError):
        search_newsapi_articles("Ana Perez")


def test_busca_en_newsapi_query_vacia_no_llama_a_la_red(monkeypatch):
    monkeypatch.setenv("NEWS_API_KEY", "clave-de-prueba")

    def fake_get(*args, **kwargs):
        raise AssertionError("no deberia llamar a la red con query vacia")

    monkeypatch.setattr(client.requests, "get", fake_get)
    assert search_newsapi_articles("") == []


def test_busca_en_newsapi_error_http_se_traduce(monkeypatch, respuesta_fija):
    monkeypatch.setenv("NEWS_API_KEY", "clave-de-prueba")

    def fake_get(*args, **kwargs):
        return respuesta_fija({"error": "boom"}, status=401)

    monkeypatch.setattr(client.requests, "get", fake_get)
    with pytest.raises(ProveedorNoticiasError):
        search_newsapi_articles("Ana Perez")


def test_busca_en_newsapi_forma_inesperada_es_error(monkeypatch, respuesta_fija):
    monkeypatch.setenv("NEWS_API_KEY", "clave-de-prueba")

    def fake_get(*args, **kwargs):
        return respuesta_fija(["no", "es", "un", "objeto"])

    monkeypatch.setattr(client.requests, "get", fake_get)
    with pytest.raises(ProveedorNoticiasError):
        search_newsapi_articles("Ana Perez")


# --------------------------------------------------------------------------
# GDELT limita a una consulta cada 5 s por IP: un 429 no se reintenta
# --------------------------------------------------------------------------


def test_gdelt_429_es_un_limite_sin_esperar_ni_reintentar(monkeypatch, respuesta_fija):
    """CHORE-2026-11-27-01: esperar 5,5 s y reintentar no cabe en el plazo de la prensa (8 s)."""
    llamadas = []

    def fake_get(*a, **k):
        llamadas.append(1)
        return respuesta_fija({}, status=429)

    monkeypatch.setattr(client.requests, "get", fake_get)
    with pytest.raises(client.LimiteProveedorNoticias):
        search_gdelt_articles("Acme")
    assert len(llamadas) == 1


def test_newsapi_429_es_un_limite_del_proveedor_sin_reintento(monkeypatch, respuesta_fija):
    llamadas = []

    def fake_get(*a, **k):
        llamadas.append(1)
        return respuesta_fija({}, status=429)

    monkeypatch.setenv("NEWS_API_KEY", "clave")
    monkeypatch.setattr(client.requests, "get", fake_get)
    with pytest.raises(client.LimiteProveedorNoticias):
        search_newsapi_articles("Acme")
    assert len(llamadas) == 1


# --------------------------------------------------------------------------
# CHORE-2026-11-27-01: GDELT saturado (7 s para conectar, 12-25 s de TLS)
# --------------------------------------------------------------------------


def test_gdelt_separa_el_timeout_de_conexion_y_de_lectura(monkeypatch, respuesta_fija):
    recibidos = []

    def fake_get(url, params=None, timeout=None):
        recibidos.append(timeout)
        return respuesta_fija({"articles": []})

    monkeypatch.setattr(client.requests, "get", fake_get)
    search_gdelt_articles("Acme")

    conexion, lectura = recibidos[0]
    assert conexion <= 3
    assert lectura <= 6


def test_gdelt_no_consulta_de_nuevo_antes_del_intervalo_por_ip(monkeypatch, respuesta_fija):
    """Una segunda consulta antes de 5 s provocaría el 429: se omite sin tocar la red."""
    ahora = [1000.0]
    llamadas = []

    def fake_get(*a, **k):
        llamadas.append(1)
        return respuesta_fija({"articles": []})

    monkeypatch.setattr(client.requests, "get", fake_get)
    monkeypatch.setattr(client, "_reloj", lambda: ahora[0])

    search_gdelt_articles("Acme")
    ahora[0] += client.GDELT_INTERVALO_SEG - 0.5
    with pytest.raises(client.LimiteProveedorNoticias):
        search_gdelt_articles("Acme")
    assert len(llamadas) == 1

    ahora[0] += 1.0
    search_gdelt_articles("Acme")
    assert len(llamadas) == 2


def test_gdelt_un_fallo_de_red_tambien_ocupa_el_turno(monkeypatch, respuesta_fija):
    """El intervalo cuenta desde que se pidió, haya respondido GDELT o no."""
    ahora = [1000.0]

    def caido(*a, **k):
        raise client.requests.ConnectTimeout("sin respuesta")

    monkeypatch.setattr(client.requests, "get", caido)
    monkeypatch.setattr(client, "_reloj", lambda: ahora[0])

    with pytest.raises(ProveedorNoticiasError):
        search_gdelt_articles("Acme")
    ahora[0] += 1.0
    with pytest.raises(client.LimiteProveedorNoticias):
        search_gdelt_articles("Acme")
