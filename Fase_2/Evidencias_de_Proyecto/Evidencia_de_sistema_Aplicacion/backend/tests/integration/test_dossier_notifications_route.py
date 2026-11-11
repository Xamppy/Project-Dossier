"""S5.2 · Integración de ``GET /dossier-notifications/stream`` contra Postgres.

Requiere ``TEST_DATABASE_URL`` (fixture ``pg_vacia``). El acceso y el aislamiento
están en tests/security/test_dossier_notifications_seguridad.py.
"""
from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from alembic import command
from dossier.api.app import app
from dossier.api.auth_routes import get_db_if_configured
from dossier.security.jwt_tokens import create_access_token

RUTA = "/dossier-notifications/stream"


def _org(c, nombre: str):
    return c.execute(
        text("INSERT INTO organizations (name, slug) VALUES (:n, :s) RETURNING id"),
        {"n": nombre, "s": nombre.lower()},
    ).scalar_one()


def _usuario(c, email: str):
    return c.execute(text("INSERT INTO users (email) VALUES (:e) RETURNING id"), {"e": email}).scalar_one()


def _miembro(c, org, user, role: str) -> None:
    c.execute(
        text(
            "INSERT INTO org_memberships (organization_id, user_id, role, is_primary_org) "
            "VALUES (:o, :u, :r, true)"
        ),
        {"o": org, "u": user, "r": role},
    )


def insertar_dossier(engine, org, user, sujeto: str):
    with engine.begin() as c:
        return c.execute(
            text(
                "INSERT INTO dossiers (organization_id, requested_by_user_id, status, subject_name, "
                "dossier_data) VALUES (:o, :u, 'complete', :s, CAST(:d AS JSONB)) RETURNING id"
            ),
            {"o": org, "u": user, "s": sujeto, "d": json.dumps({"markdown": f"# {sujeto}"})},
        ).scalar_one()


def token(user, org, role: str) -> str:
    return create_access_token(user_id=str(user), email="x@example.com", organization_id=str(org), role=role)


def cliente(tok: str | None = None) -> TestClient:
    headers = {"Authorization": f"Bearer {tok}"} if tok else {}
    return TestClient(app, headers=headers, raise_server_exceptions=False)


def eventos(resp) -> Iterator[dict]:
    """Datos de cada evento ``dossiers`` según llegan."""
    for linea in resp.iter_lines():
        if linea.startswith("data: "):
            yield json.loads(linea.removeprefix("data: "))


@pytest.fixture
def base(pg_vacia, alembic_cfg) -> Iterator[SimpleNamespace]:
    command.upgrade(alembic_cfg, "head")
    m = SimpleNamespace(engine=pg_vacia)
    with pg_vacia.begin() as c:
        m.org = _org(c, "Propia")
        m.admin = _usuario(c, "admin@propia.com")
        _miembro(c, m.org, m.admin, "admin")
    m.d1 = insertar_dossier(pg_vacia, m.org, m.admin, "Primero")

    def _db():
        with Session(pg_vacia) as s:
            yield s

    app.dependency_overrides[get_db_if_configured] = _db
    yield m
    app.dependency_overrides.clear()


def test_ca1_primer_evento_igual_a_get_dossiers(base, monkeypatch):
    monkeypatch.setenv("DOSSIER_NOTIFICATIONS_MAX_SECONDS", "0")
    c = cliente(token(base.admin, base.org, "admin"))
    esperado = c.get("/dossiers?limit=25").json()
    with c.stream("GET", RUTA) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        assert resp.headers["cache-control"] == "no-cache"
        recibidos = list(eventos(resp))
    assert recibidos == [esperado]
    assert recibidos[0]["items"][0]["subject_name"] == "Primero"


def despues(segundos: float, accion) -> threading.Thread:
    """Ejecuta ``accion`` en otro hilo con el stream ya abierto.

    El TestClient de Starlette entrega el cuerpo cuando la respuesta termina, no en vivo:
    los cambios en la base tienen que ocurrir mientras el servidor sigue generando.
    """

    def correr() -> None:
        time.sleep(segundos)
        accion()

    hilo = threading.Thread(target=correr)
    hilo.start()
    return hilo


def test_ca2_un_dossier_nuevo_llega_sin_que_el_cliente_pregunte(base, monkeypatch):
    monkeypatch.setenv("DOSSIER_NOTIFICATIONS_CHECK_SECONDS", "1")
    monkeypatch.setenv("DOSSIER_NOTIFICATIONS_MAX_SECONDS", "4")
    c = cliente(token(base.admin, base.org, "admin"))
    hilo = despues(1.5, lambda: insertar_dossier(base.engine, base.org, base.admin, "Segundo"))
    with c.stream("GET", RUTA) as resp:
        recibidos = list(eventos(resp))
    hilo.join()
    assert [[i["subject_name"] for i in r["items"]] for r in recibidos] == [
        ["Primero"],
        ["Segundo", "Primero"],
    ]


def test_ca2_sin_cambios_no_hay_eventos_nuevos(base, monkeypatch):
    monkeypatch.setenv("DOSSIER_NOTIFICATIONS_CHECK_SECONDS", "1")
    monkeypatch.setenv("DOSSIER_NOTIFICATIONS_MAX_SECONDS", "3")
    c = cliente(token(base.admin, base.org, "admin"))
    with c.stream("GET", RUTA) as resp:
        recibidos = list(eventos(resp))
    assert len(recibidos) == 1


def test_el_stream_no_retiene_una_conexion_de_la_base(base, monkeypatch):
    """Entre comprobaciones la sesión no queda «idle in transaction»."""
    monkeypatch.setenv("DOSSIER_NOTIFICATIONS_CHECK_SECONDS", "1")
    monkeypatch.setenv("DOSSIER_NOTIFICATIONS_MAX_SECONDS", "4")
    c = cliente(token(base.admin, base.org, "admin"))
    abiertas: list[int] = []

    def mirar() -> None:
        time.sleep(1.5)
        with base.engine.connect() as conn:
            abiertas.append(
                conn.execute(
                    text(
                        "SELECT count(*) FROM pg_stat_activity "
                        "WHERE datname = current_database() AND state = 'idle in transaction'"
                    )
                ).scalar_one()
            )

    hilo = threading.Thread(target=mirar)
    with c.stream("GET", RUTA) as resp:
        hilo.start()
        list(eventos(resp))
    hilo.join()
    assert abiertas == [0]
