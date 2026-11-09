"""S5.8 · Límite de tasa en autenticación y generación de dossiers (integración HTTP).

Las pruebas por IP y por usuario no necesitan Postgres: el límite se evalúa antes que
el endpoint. Las de inicio de sesión por correo sí (fixture ``pg_vacia``).
"""
from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from alembic import command
from dossier.api.app import app
from dossier.api.auth_routes import get_db_if_configured
from dossier.security import hash_password
from dossier.security.jwt_tokens import create_access_token

CLAVE = "secreta-123"


def _sin_db():
    yield None


@pytest.fixture
def sin_db() -> Iterator[TestClient]:
    app.dependency_overrides[get_db_if_configured] = _sin_db
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.pop(get_db_if_configured, None)


def _token(usuario: uuid.UUID | None = None) -> str:
    return create_access_token(
        user_id=str(usuario or uuid.uuid4()), email="a@b.cl", organization_id=str(uuid.uuid4()), role="admin"
    )


# --------------------------------------------------------------------------
# Autenticación por IP
# --------------------------------------------------------------------------


def test_autenticacion_responde_429_al_superar_el_limite_por_ip(sin_db, monkeypatch):
    monkeypatch.setenv("AUTH_RATE_LIMIT", "3/60")

    estados = [sin_db.post("/auth/refresh").status_code for _ in range(4)]

    assert estados == [401, 401, 401, 429]


def test_el_429_trae_retry_after_y_un_codigo_estable(sin_db, monkeypatch):
    monkeypatch.setenv("AUTH_RATE_LIMIT", "1/60")
    sin_db.post("/auth/refresh")

    r = sin_db.post("/auth/refresh")

    assert r.status_code == 429
    assert r.headers["retry-after"] == "60"
    assert r.json()["detail"]["code"] == "rate_limited"
    assert r.json()["detail"]["retry_after"] == 60


@pytest.mark.parametrize(
    ("metodo", "ruta"),
    [
        ("post", "/auth/login"),
        ("post", "/auth/register"),
        ("post", "/auth/refresh"),
        ("post", "/auth/forgot-password"),
        ("get", "/auth/google/login"),
    ],
)
def test_todas_las_rutas_de_autenticacion_comparten_el_limite(sin_db, monkeypatch, metodo, ruta):
    monkeypatch.setenv("AUTH_RATE_LIMIT", "1/60")
    sin_db.post("/auth/refresh")  # consume el único cupo de la IP

    r = getattr(sin_db, metodo)(ruta, json={}) if metodo == "post" else sin_db.get(ruta)

    assert r.status_code == 429


def test_rutas_que_no_son_de_autenticacion_no_consumen_el_cupo(sin_db, monkeypatch):
    monkeypatch.setenv("AUTH_RATE_LIMIT", "1/60")
    for _ in range(5):
        sin_db.get("/health")

    assert sin_db.post("/auth/refresh").status_code == 401


def test_con_limite_desactivado_no_hay_429(sin_db, monkeypatch):
    monkeypatch.setenv("AUTH_RATE_LIMIT", "off")
    assert all(sin_db.post("/auth/refresh").status_code == 401 for _ in range(30))


# --------------------------------------------------------------------------
# Generación por usuario
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ruta",
    [
        "/dossiers/corporate/generate",
        "/dossiers/person/research",
        "/calendario/generar-dossiers",
        "/calendario/generar-dossiers-outlook",
        "/calendario/generar-dossiers-google",
    ],
)
def test_generacion_responde_429_por_usuario(sin_db, monkeypatch, ruta):
    monkeypatch.setenv("GENERATION_RATE_LIMIT", "2/60")
    cabeceras = {"Authorization": f"Bearer {_token()}"}

    estados = [sin_db.post(ruta, json={}, headers=cabeceras).status_code for _ in range(3)]

    assert 429 not in estados[:2]
    assert estados[2] == 429


def test_el_limite_de_generacion_es_por_usuario(sin_db, monkeypatch):
    monkeypatch.setenv("GENERATION_RATE_LIMIT", "1/60")
    ana, beto = _token(uuid.uuid4()), _token(uuid.uuid4())

    sin_db.post("/dossiers/corporate/generate", json={}, headers={"Authorization": f"Bearer {ana}"})
    r_ana = sin_db.post("/dossiers/corporate/generate", json={}, headers={"Authorization": f"Bearer {ana}"})
    r_beto = sin_db.post("/dossiers/corporate/generate", json={}, headers={"Authorization": f"Bearer {beto}"})

    assert r_ana.status_code == 429
    assert r_beto.status_code != 429


def test_las_lecturas_no_consumen_el_cupo_de_generacion(sin_db, monkeypatch):
    monkeypatch.setenv("GENERATION_RATE_LIMIT", "1/60")
    cabeceras = {"Authorization": f"Bearer {_token()}"}
    for _ in range(5):
        sin_db.get("/dossiers", headers=cabeceras)

    assert sin_db.post("/dossiers/corporate/generate", json={}, headers=cabeceras).status_code != 429


# --------------------------------------------------------------------------
# Inicios de sesión fallidos por correo (Postgres)
# --------------------------------------------------------------------------


@pytest.fixture
def con_usuario(pg_vacia, alembic_cfg) -> Iterator[TestClient]:
    command.upgrade(alembic_cfg, "head")
    with pg_vacia.begin() as c:
        org = c.execute(text("INSERT INTO organizations (name, slug) VALUES ('A', 'a') RETURNING id")).scalar_one()
        user = c.execute(
            text("INSERT INTO users (email, password_hash) VALUES ('ana@example.com', :h) RETURNING id"),
            {"h": hash_password(CLAVE)},
        ).scalar_one()
        c.execute(
            text("INSERT INTO org_memberships (organization_id, user_id, role, is_primary_org) VALUES (:o, :u, 'admin', TRUE)"),
            {"o": org, "u": user},
        )

    def _db():
        with Session(pg_vacia) as s:
            yield s

    app.dependency_overrides[get_db_if_configured] = _db
    try:
        yield TestClient(app, base_url="https://testserver")
    finally:
        app.dependency_overrides.pop(get_db_if_configured, None)


def _login(c: TestClient, clave: str, correo: str = "ana@example.com"):
    return c.post("/auth/login", json={"email": correo, "password": clave})


def test_tras_varios_fallos_el_correo_queda_bloqueado_aun_con_la_clave_correcta(con_usuario, monkeypatch):
    monkeypatch.setenv("LOGIN_FAILURE_RATE_LIMIT", "3/300")

    fallos = [_login(con_usuario, "mala").status_code for _ in range(3)]
    r = _login(con_usuario, CLAVE)

    assert fallos == [401, 401, 401]
    assert r.status_code == 429


def test_un_inicio_correcto_limpia_los_fallos(con_usuario, monkeypatch):
    monkeypatch.setenv("LOGIN_FAILURE_RATE_LIMIT", "3/300")
    _login(con_usuario, "mala")
    _login(con_usuario, "mala")

    assert _login(con_usuario, CLAVE).status_code == 200
    assert [_login(con_usuario, "mala").status_code for _ in range(2)] == [401, 401]


def test_los_fallos_de_un_correo_no_bloquean_a_otro(con_usuario, monkeypatch):
    monkeypatch.setenv("LOGIN_FAILURE_RATE_LIMIT", "1/300")
    _login(con_usuario, "mala", correo="otra@example.com")

    assert _login(con_usuario, CLAVE).status_code == 200
