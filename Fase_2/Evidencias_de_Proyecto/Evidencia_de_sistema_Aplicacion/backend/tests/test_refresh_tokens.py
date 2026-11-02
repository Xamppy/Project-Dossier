"""S3.9 · Sesión con token de acceso corto y token de renovación (pruebas unitarias).

Cubren las funciones puras: vigencias, formato y hash del token de renovación y
los atributos de la cookie. El flujo contra Postgres está en
``tests/integration/test_refresh_tokens_flujo.py``.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import jwt
import pytest

from dossier.api import refresh_cookie as rc
from dossier.security import refresh_tokens as rt
from dossier.security.jwt_tokens import create_access_token

# --------------------------------------------------------------------------
# Token de acceso: 15 minutos por omisión
# --------------------------------------------------------------------------


def _vigencia(token: str) -> timedelta:
    claims = jwt.decode(token, options={"verify_signature": False})
    return datetime.fromtimestamp(claims["exp"], UTC) - datetime.fromtimestamp(claims["iat"], UTC)


def test_token_de_acceso_dura_15_minutos_por_omision(monkeypatch):
    monkeypatch.delenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", raising=False)
    assert _vigencia(create_access_token(user_id="u-1", email="a@b.cl")) == timedelta(minutes=15)


def test_vigencia_del_token_de_acceso_es_configurable(monkeypatch):
    monkeypatch.setenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "5")
    assert _vigencia(create_access_token(user_id="u-1", email="a@b.cl")) == timedelta(minutes=5)


# --------------------------------------------------------------------------
# Vigencia del token de renovación
# --------------------------------------------------------------------------


def test_renovacion_dura_30_dias_por_omision(monkeypatch):
    monkeypatch.delenv("REFRESH_TOKEN_EXPIRE_DAYS", raising=False)
    assert rt.refresh_token_days() == 30


@pytest.mark.parametrize(("valor", "esperado"), [("7", 7), ("1", 1), ("90", 90)])
def test_renovacion_respeta_la_variable(monkeypatch, valor, esperado):
    monkeypatch.setenv("REFRESH_TOKEN_EXPIRE_DAYS", valor)
    assert rt.refresh_token_days() == esperado


@pytest.mark.parametrize(("valor", "esperado"), [("0", 1), ("-3", 1), ("365", 90), ("abc", 30), ("", 30)])
def test_renovacion_acota_valores_fuera_de_rango(monkeypatch, valor, esperado):
    monkeypatch.setenv("REFRESH_TOKEN_EXPIRE_DAYS", valor)
    assert rt.refresh_token_days() == esperado


def test_sesion_sin_recordar_dura_menos_que_la_recordada(monkeypatch):
    monkeypatch.delenv("REFRESH_TOKEN_EXPIRE_DAYS", raising=False)
    ahora = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)
    corta = rt.expiry_for(persistent=False, now=ahora)
    larga = rt.expiry_for(persistent=True, now=ahora)
    assert corta - ahora == timedelta(hours=rt.SESSION_ONLY_HOURS)
    assert larga - ahora == timedelta(days=30)


# --------------------------------------------------------------------------
# Formato y hash
# --------------------------------------------------------------------------


@pytest.mark.parametrize("persistente", [True, False])
def test_el_token_crudo_declara_si_la_sesion_es_recordada(persistente):
    crudo = rt.new_raw_token(persistent=persistente)
    assert rt.is_persistent(crudo) is persistente
    assert len(crudo) >= 60


def test_dos_tokens_nunca_se_repiten():
    assert len({rt.new_raw_token(persistent=True) for _ in range(200)}) == 200


def test_el_hash_es_estable_y_no_contiene_el_token():
    crudo = rt.new_raw_token(persistent=True)
    h = rt.hash_refresh_token(crudo)
    assert h == rt.hash_refresh_token(crudo)
    assert len(h) == 64
    assert crudo not in h


@pytest.mark.parametrize("crudo", ["", "x", "q.abc", "p.", "p.con espacios", "p." + "a" * 600])
def test_formato_invalido_se_reconoce(crudo):
    assert rt.looks_valid(crudo) is False


def test_formato_valido_se_reconoce():
    assert rt.looks_valid(rt.new_raw_token(persistent=False)) is True


# --------------------------------------------------------------------------
# Cookie
# --------------------------------------------------------------------------


def _request(root_path: str = "") -> SimpleNamespace:
    return SimpleNamespace(scope={"root_path": root_path}, cookies={})


@pytest.mark.parametrize(("root", "esperado"), [("", "/auth"), ("/api", "/api/auth"), ("/api/", "/api/auth")])
def test_la_cookie_solo_viaja_a_las_rutas_de_autenticacion(root, esperado):
    """Detrás de Caddy la API vive bajo /api: la ruta de la cookie lo incluye."""
    assert rc.cookie_path(_request(root)) == esperado


def test_cookie_estricta_y_segura_por_omision(monkeypatch):
    monkeypatch.delenv("AUTH_REFRESH_COOKIE_SAMESITE", raising=False)
    monkeypatch.delenv("AUTH_REFRESH_COOKIE_SECURE", raising=False)
    assert rc.cookie_samesite() == "strict"
    assert rc.cookie_secure() is True


@pytest.mark.parametrize(("valor", "esperado"), [("lax", "lax"), ("LAX", "lax"), ("none", "strict"), ("x", "strict")])
def test_samesite_solo_acepta_lax_o_strict(monkeypatch, valor, esperado):
    """`none` exigiría enviar la cookie a cualquier sitio: no se permite."""
    monkeypatch.setenv("AUTH_REFRESH_COOKIE_SAMESITE", valor)
    assert rc.cookie_samesite() == esperado


@pytest.mark.parametrize(("valor", "esperado"), [("0", False), ("false", False), ("1", True), ("cualquiera", True)])
def test_secure_solo_se_apaga_explicitamente(monkeypatch, valor, esperado):
    monkeypatch.setenv("AUTH_REFRESH_COOKIE_SECURE", valor)
    assert rc.cookie_secure() is esperado
