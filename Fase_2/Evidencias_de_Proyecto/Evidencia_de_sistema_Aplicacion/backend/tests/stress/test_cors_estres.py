"""S3.8 · Política CORS bajo volumen y concurrencia (pruebas de estrés)."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from dossier.api.cors_config import build_cors_settings, parse_cors_origins


def test_volumen_mil_origenes_se_leen_completos_y_rapido():
    crudo = ",".join(f"https://cliente{i}.example.cl/" for i in range(1000))
    inicio = time.perf_counter()
    origenes = parse_cors_origins(crudo)
    assert time.perf_counter() - inicio < 0.5
    assert len(origenes) == 1000
    assert origenes[-1] == "https://cliente999.example.cl"


def test_concurrencia_preflights_mezclados_dan_siempre_la_misma_decision():
    """200 preflights simultáneos, mitad permitidos y mitad no: ninguno se cruza."""
    app = FastAPI()
    app.add_middleware(CORSMiddleware, **build_cors_settings({}).middleware_kwargs())

    @app.get("/recurso")
    def leer():
        return {"ok": True}

    client = TestClient(app)

    def preflight(i: int) -> tuple[bool, int, str | None]:
        permitido = i % 2 == 0
        origen = "http://localhost:3000" if permitido else f"https://atacante{i}.example"
        r = client.options(
            "/recurso",
            headers={"Origin": origen, "Access-Control-Request-Method": "GET"},
        )
        return permitido, r.status_code, r.headers.get("access-control-allow-origin")

    with ThreadPoolExecutor(max_workers=20) as pool:
        resultados = list(pool.map(preflight, range(200)))

    for permitido, status, allow_origin in resultados:
        if permitido:
            assert status == 200
            assert allow_origin == "http://localhost:3000"
        else:
            assert status == 400
            assert allow_origin is None
