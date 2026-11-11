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
# GDELT limita a una consulta cada 5 s por IP: ante 429 se reintenta una vez
# --------------------------------------------------------------------------


def test_gdelt_429_espera_y_reintenta_una_vez(monkeypatch, respuesta_fija):
    respuestas = [respuesta_fija({}, status=429), respuesta_fija({"articles": [{"url": "u", "title": "t"}]})]
    esperas: list[float] = []
    monkeypatch.setattr(client.requests, "get", lambda *a, **k: respuestas.pop(0))
    monkeypatch.setattr(client, "_esperar", esperas.append)

    assert search_gdelt_articles("Acme") == [{"url": "u", "title": "t"}]
    assert esperas == [client.GDELT_ESPERA_LIMITE_SEG]


def test_gdelt_429_dos_veces_es_un_limite_del_proveedor(monkeypatch, respuesta_fija):
    llamadas = []

    def fake_get(*a, **k):
        llamadas.append(1)
        return respuesta_fija({}, status=429)

    monkeypatch.setattr(client.requests, "get", fake_get)
    monkeypatch.setattr(client, "_esperar", lambda s: None)
    with pytest.raises(client.LimiteProveedorNoticias):
        search_gdelt_articles("Acme")
    assert len(llamadas) == 2


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
