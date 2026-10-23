"""S3.8 · Política CORS aplicada en HTTP (pruebas de integración).

Dos niveles:
1. La aplicación real registra el middleware con la política de `cors_config`.
2. Una app mínima con esa misma política responde bien a las peticiones del dashboard.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from dossier.api.cors_config import ALLOWED_HEADERS, ALLOWED_METHODS, build_cors_settings

ORIGEN_DASHBOARD = "http://localhost:3000"


def _app_con_politica(env: dict[str, str]) -> FastAPI:
    app = FastAPI()
    app.add_middleware(CORSMiddleware, **build_cors_settings(env).middleware_kwargs())

    @app.get("/recurso")
    def leer():
        return {"ok": True}

    @app.patch("/recurso")
    def editar():
        return {"ok": True}

    return app


def _preflight(client: TestClient, metodo: str, cabeceras: str = "authorization,content-type"):
    return client.options(
        "/recurso",
        headers={
            "Origin": ORIGEN_DASHBOARD,
            "Access-Control-Request-Method": metodo,
            "Access-Control-Request-Headers": cabeceras,
        },
    )


def _kwargs_cors_de_la_app_real() -> dict:
    from dossier.api.app import app

    for mw in app.user_middleware:
        if mw.cls is CORSMiddleware:
            return dict(mw.kwargs)
    raise AssertionError("La aplicación no registra CORSMiddleware")


def test_app_real_usa_metodos_y_cabeceras_explicitos():
    kwargs = _kwargs_cors_de_la_app_real()
    assert list(kwargs["allow_methods"]) == list(ALLOWED_METHODS)
    assert list(kwargs["allow_headers"]) == list(ALLOWED_HEADERS)


def test_app_real_no_envia_credenciales():
    assert _kwargs_cors_de_la_app_real()["allow_credentials"] is False


def test_preflight_del_dashboard_es_aceptado_para_cada_metodo():
    client = TestClient(_app_con_politica({}))
    for metodo in ("GET", "POST", "PUT", "PATCH", "DELETE"):
        r = _preflight(client, metodo)
        assert r.status_code == 200, metodo
        assert r.headers["access-control-allow-origin"] == ORIGEN_DASHBOARD
        assert "*" not in r.headers["access-control-allow-methods"]


def test_preflight_acepta_la_cabecera_del_canal_sse():
    client = TestClient(_app_con_politica({}))
    r = _preflight(client, "GET", "authorization,last-event-id")
    assert r.status_code == 200


def test_peticion_simple_del_dashboard_recibe_su_origen():
    client = TestClient(_app_con_politica({}))
    r = client.get("/recurso", headers={"Origin": ORIGEN_DASHBOARD})
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == ORIGEN_DASHBOARD
    assert "access-control-allow-credentials" not in r.headers


def test_origen_configurado_por_variable_es_aceptado():
    client = TestClient(_app_con_politica({"CORS_ORIGINS": "https://dossier.example.cl"}))
    r = client.get("/recurso", headers={"Origin": "https://dossier.example.cl"})
    assert r.headers["access-control-allow-origin"] == "https://dossier.example.cl"
