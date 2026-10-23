"""S3.8 · Política CORS: lectura de la configuración (pruebas unitarias).

La política se arma con `build_cors_settings(env)`, una función pura que recibe las
variables de entorno como diccionario. Así se prueba sin recargar la aplicación.
"""
from __future__ import annotations

import pytest

from dossier.api.cors_config import (
    ALLOWED_HEADERS,
    ALLOWED_METHODS,
    DEFAULT_VERCEL_ORIGIN_REGEX,
    build_cors_settings,
    parse_cors_origins,
)

# --------------------------------------------------------------------------
# parse_cors_origins: se conserva el comportamiento que ya tenía app.py
# --------------------------------------------------------------------------


def test_parse_separa_por_coma_y_quita_espacios():
    assert parse_cors_origins(" https://a.cl , https://b.cl ") == ["https://a.cl", "https://b.cl"]


def test_parse_quita_barra_final_comillas_y_bom():
    crudo = "﻿“https://a.cl/”, 'https://b.cl/'"
    assert parse_cors_origins(crudo) == ["https://a.cl", "https://b.cl"]


@pytest.mark.parametrize("crudo", ["", "   ", ",", " , , "])
def test_parse_vacio_no_deja_origenes(crudo):
    assert parse_cors_origins(crudo) == []


# --------------------------------------------------------------------------
# Métodos y cabeceras: lista explícita, nunca comodín
# --------------------------------------------------------------------------


def test_metodos_son_una_lista_explicita_sin_comodin():
    assert "*" not in ALLOWED_METHODS
    assert set(ALLOWED_METHODS) == {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"}


def test_metodos_no_incluyen_trace_ni_connect():
    assert "TRACE" not in ALLOWED_METHODS
    assert "CONNECT" not in ALLOWED_METHODS


def test_cabeceras_son_una_lista_explicita_sin_comodin():
    assert "*" not in ALLOWED_HEADERS
    # Las que usa el dashboard: JWT, JSON y la reanudación del canal SSE.
    for cabecera in ("Authorization", "Content-Type", "Last-Event-ID"):
        assert cabecera in ALLOWED_HEADERS


# --------------------------------------------------------------------------
# build_cors_settings
# --------------------------------------------------------------------------


def test_sin_variables_usa_localhost_y_sin_regex_de_vercel():
    s = build_cors_settings({})
    assert "http://localhost:3000" in s.origins
    assert "http://127.0.0.1:3009" in s.origins
    assert s.origin_regex is None


def test_cors_origins_reemplaza_los_origenes_por_omision():
    s = build_cors_settings({"CORS_ORIGINS": "https://dossier.example.cl"})
    assert s.origins == ["https://dossier.example.cl"]


def test_cors_origins_vacio_no_permite_ningun_origen():
    s = build_cors_settings({"CORS_ORIGINS": ""})
    assert s.origins == []


@pytest.mark.parametrize("valor", ["1", "true", "TRUE", "yes", "on"])
def test_regex_de_vercel_solo_si_se_activa_explicitamente(valor):
    s = build_cors_settings({"CORS_ALLOW_VERCEL_APP_REGEX": valor})
    assert s.origin_regex == DEFAULT_VERCEL_ORIGIN_REGEX


@pytest.mark.parametrize("valor", ["0", "false", "no", "", "cualquier-cosa"])
def test_regex_de_vercel_apagada_con_otros_valores(valor):
    s = build_cors_settings({"CORS_ALLOW_VERCEL_APP_REGEX": valor})
    assert s.origin_regex is None


def test_regex_personalizada_valida_se_respeta():
    regex = r"https://dossier-[a-z0-9-]+\.vercel\.app"
    s = build_cors_settings(
        {"CORS_ALLOW_VERCEL_APP_REGEX": "1", "CORS_VERCEL_ORIGIN_REGEX": regex}
    )
    assert s.origin_regex == regex


def test_regex_personalizada_invalida_cae_al_patron_por_omision():
    s = build_cors_settings(
        {"CORS_ALLOW_VERCEL_APP_REGEX": "1", "CORS_VERCEL_ORIGIN_REGEX": "https://[sin-cerrar"}
    )
    assert s.origin_regex == DEFAULT_VERCEL_ORIGIN_REGEX


def test_regex_personalizada_se_ignora_si_la_bandera_esta_apagada():
    s = build_cors_settings({"CORS_VERCEL_ORIGIN_REGEX": r"https://x\.vercel\.app"})
    assert s.origin_regex is None


def test_kwargs_del_middleware_sin_credenciales_ni_comodines():
    kwargs = build_cors_settings({}).middleware_kwargs()
    assert kwargs["allow_credentials"] is False
    assert list(kwargs["allow_methods"]) == list(ALLOWED_METHODS)
    assert list(kwargs["allow_headers"]) == list(ALLOWED_HEADERS)
    assert "*" not in kwargs["allow_origins"]
