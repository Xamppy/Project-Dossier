"""S3.8 · Política CORS: lo que NO debe permitirse (pruebas de seguridad).

Hallazgo de origen: docs/security/README.md, "CORS con métodos abiertos".
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from dossier.api.cors_config import build_cors_settings

ORIGEN_DASHBOARD = "http://localhost:3000"


def _cliente(env: dict[str, str] | None = None) -> TestClient:
    app = FastAPI()
    app.add_middleware(CORSMiddleware, **build_cors_settings(env or {}).middleware_kwargs())

    @app.get("/recurso")
    def leer():
        return {"ok": True}

    return TestClient(app)


def _preflight(client: TestClient, origen: str, metodo: str = "GET", cabeceras: str = ""):
    headers = {"Origin": origen, "Access-Control-Request-Method": metodo}
    if cabeceras:
        headers["Access-Control-Request-Headers"] = cabeceras
    return client.options("/recurso", headers=headers)


def test_origen_desconocido_es_rechazado_en_preflight():
    r = _preflight(_cliente(), "https://atacante.example")
    assert r.status_code == 400
    assert "access-control-allow-origin" not in r.headers


def test_origen_desconocido_no_recibe_permiso_en_peticion_simple():
    r = _cliente().get("/recurso", headers={"Origin": "https://atacante.example"})
    assert "access-control-allow-origin" not in r.headers


def test_cualquier_sitio_vercel_es_rechazado_por_omision():
    """Antes, cualquier *.vercel.app (también el de un tercero) quedaba permitido."""
    r = _preflight(_cliente(), "https://atacante.vercel.app")
    assert r.status_code == 400


def test_regex_de_vercel_no_acepta_dominios_que_solo_lo_contienen():
    cliente = _cliente({"CORS_ALLOW_VERCEL_APP_REGEX": "1"})
    for origen in ("https://x.vercel.app.atacante.example", "http://x.vercel.app"):
        assert _preflight(cliente, origen).status_code == 400, origen


@pytest.mark.parametrize("metodo", ["TRACE", "CONNECT", "PROPFIND"])
def test_metodo_fuera_de_la_lista_es_rechazado(metodo):
    r = _preflight(_cliente(), ORIGEN_DASHBOARD, metodo)
    assert r.status_code == 400


def test_cabecera_fuera_de_la_lista_es_rechazada():
    r = _preflight(_cliente(), ORIGEN_DASHBOARD, "GET", "authorization,x-cabecera-inventada")
    assert r.status_code == 400


def test_respuestas_no_habilitan_credenciales():
    """Sin cookies entre sitios: el dashboard autentica con `Authorization: Bearer`."""
    r = _preflight(_cliente(), ORIGEN_DASHBOARD, "GET", "authorization")
    assert r.status_code == 200
    assert "access-control-allow-credentials" not in r.headers


def test_origen_null_es_rechazado():
    """`Origin: null` lo envían iframes con sandbox y archivos locales."""
    assert _preflight(_cliente(), "null").status_code == 400
