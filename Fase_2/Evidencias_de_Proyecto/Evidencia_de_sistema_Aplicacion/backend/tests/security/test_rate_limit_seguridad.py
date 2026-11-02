"""S5.8 · Lo que el límite de tasa NO debe permitir (pruebas de seguridad).

Hallazgo de origen: docs/security/README.md, "Limitación de tasa: ausente".
"""
from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from dossier.api.app import app
from dossier.api.auth_routes import get_db_if_configured
from dossier.security import rate_limit as rl


def _sin_db():
    yield None


def _cliente() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def test_falsear_x_forwarded_for_no_evade_el_limite(monkeypatch):
    """La IP sale de la conexión (uvicorn --proxy-headers la corrige detrás de Caddy), no de la cabecera."""
    monkeypatch.setenv("AUTH_RATE_LIMIT", "2/60")
    app.dependency_overrides[get_db_if_configured] = _sin_db
    try:
        c = _cliente()
        estados = [
            c.post("/auth/refresh", headers={"X-Forwarded-For": f"10.0.0.{i}"}).status_code for i in range(5)
        ]
    finally:
        app.dependency_overrides.pop(get_db_if_configured, None)

    assert estados[2:] == [429, 429, 429]


def test_un_token_inventado_no_da_cupo_propio_en_generacion(monkeypatch):
    """Sin token válido la clave es la IP: inventar tokens no multiplica el cupo."""
    monkeypatch.setenv("GENERATION_RATE_LIMIT", "2/60")
    app.dependency_overrides[get_db_if_configured] = _sin_db
    try:
        c = _cliente()
        estados = [
            c.post(
                "/dossiers/corporate/generate", json={}, headers={"Authorization": f"Bearer falso-{uuid.uuid4()}"}
            ).status_code
            for _ in range(4)
        ]
    finally:
        app.dependency_overrides.pop(get_db_if_configured, None)

    assert estados[2:] == [429, 429]


def test_el_bloqueo_por_correo_no_revela_si_la_cuenta_existe():
    """La clave del correo es un hash: el 429 es igual exista o no la cuenta."""
    lim = rl.SlidingWindowLimiter(lambda: rl.Limit(1, 300))
    lim.hit(rl.email_key("no-existe@example.com"))
    assert lim.check(rl.email_key("no-existe@example.com")) is not None
    assert lim.check(rl.email_key("tampoco@example.com")) is None


def test_el_429_no_incluye_datos_del_usuario(monkeypatch):
    monkeypatch.setenv("AUTH_RATE_LIMIT", "1/60")
    app.dependency_overrides[get_db_if_configured] = _sin_db
    try:
        c = _cliente()
        c.post("/auth/login", json={"email": "ana@example.com", "password": "x"})
        r = c.post("/auth/login", json={"email": "ana@example.com", "password": "x"})
    finally:
        app.dependency_overrides.pop(get_db_if_configured, None)

    assert r.status_code == 429
    assert "ana@example.com" not in r.text
