"""UX-ADMIN-01 · Solo el admin de plataforma lee y cambia los límites por plan (CA9).

Requiere ``TEST_DATABASE_URL`` (fixture ``pg_vacia``).
"""
from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from alembic import command
from dossier.api.app import app
from dossier.api.auth_routes import get_db_if_configured
from tests.integration.test_limite_dossiers_simultaneos import cliente, org, usuario

RUTA = "/admin/plan-settings"


@pytest.fixture
def mundo(pg_vacia, alembic_cfg) -> Iterator[SimpleNamespace]:
    command.upgrade(alembic_cfg, "head")
    m = SimpleNamespace(engine=pg_vacia)
    with pg_vacia.begin() as c:
        m.org = org(c, "Operaciones", "enterprise")
        m.plataforma = usuario(c, "ops@alloxentric.com", m.org, "admin")
        c.execute(text("UPDATE users SET is_platform_admin = true WHERE id = :u"), {"u": m.plataforma})
        m.admin_org = usuario(c, "jefe@cliente.com", m.org, "admin")
        m.comun = usuario(c, "user@cliente.com", m.org, "user")

    def _db():
        with Session(pg_vacia) as s:
            yield s

    app.dependency_overrides[get_db_if_configured] = _db
    yield m
    app.dependency_overrides.clear()


def _limite(engine, plan: str) -> int:
    with engine.connect() as c:
        return c.execute(
            text("SELECT max_concurrent_dossiers FROM plan_settings WHERE plan = :p"), {"p": plan}
        ).scalar_one()


def test_el_admin_de_plataforma_lee_los_tres_planes(mundo):
    resp = cliente(mundo.plataforma, mundo.org, "admin").get(RUTA)
    assert resp.status_code == 200
    planes = resp.json()["plans"]
    assert [(p["plan"], p["max_concurrent_dossiers"]) for p in planes] == [
        ("free", 1),
        ("pro", 3),
        ("enterprise", 10),
    ]
    assert all(p["updated_by_email"] is None for p in planes)


def test_el_admin_de_plataforma_cambia_un_limite_y_queda_auditado(mundo):
    c = cliente(mundo.plataforma, mundo.org, "admin")
    resp = c.patch(f"{RUTA}/pro", json={"max_concurrent_dossiers": 5})
    assert resp.status_code == 200
    assert resp.json()["max_concurrent_dossiers"] == 5
    assert resp.json()["updated_by_email"] == "ops@alloxentric.com"
    assert _limite(mundo.engine, "pro") == 5

    with mundo.engine.connect() as cx:
        fila = cx.execute(
            text(
                "SELECT user_id, request_data, success FROM audit_logs "
                "WHERE action = 'ADMIN plan_settings' ORDER BY created_at DESC LIMIT 1"
            )
        ).one()
    assert fila.user_id == mundo.plataforma
    assert fila.success is True
    assert fila.request_data == {"plan": "pro", "max_concurrent_dossiers": {"antes": 3, "despues": 5}}


def test_sin_sesion_401(mundo):
    sin = TestClient(app, raise_server_exceptions=False)
    assert sin.get(RUTA).status_code == 401
    assert sin.patch(f"{RUTA}/free", json={"max_concurrent_dossiers": 50}).status_code == 401
    assert _limite(mundo.engine, "free") == 1


@pytest.mark.parametrize("quien", ["admin_org", "comun"])
def test_quien_no_es_admin_de_plataforma_recibe_403(mundo, quien):
    c = cliente(getattr(mundo, quien), mundo.org, "admin" if quien == "admin_org" else "user")
    assert c.get(RUTA).status_code == 403
    assert c.patch(f"{RUTA}/free", json={"max_concurrent_dossiers": 50}).status_code == 403
    assert _limite(mundo.engine, "free") == 1


@pytest.mark.parametrize("cuerpo", [{"max_concurrent_dossiers": 0}, {"max_concurrent_dossiers": 101},
                                    {"max_concurrent_dossiers": -1}, {"max_concurrent_dossiers": "x"},
                                    {"max_concurrent_dossiers": 2.5}, {}])
def test_valores_fuera_de_rango_422(mundo, cuerpo):
    resp = cliente(mundo.plataforma, mundo.org, "admin").patch(f"{RUTA}/free", json=cuerpo)
    assert resp.status_code == 422
    assert _limite(mundo.engine, "free") == 1


@pytest.mark.parametrize("plan", ["gold", "FREE ", "pro;drop"])
def test_plan_desconocido_404(mundo, plan):
    resp = cliente(mundo.plataforma, mundo.org, "admin").patch(f"{RUTA}/{plan}", json={"max_concurrent_dossiers": 2})
    assert resp.status_code == 404
    with mundo.engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM plan_settings")).scalar_one() == 3


def test_si_falta_la_fila_el_admin_la_crea(mundo):
    with mundo.engine.begin() as c:
        c.execute(text("DELETE FROM plan_settings WHERE plan = 'enterprise'"))
    c = cliente(mundo.plataforma, mundo.org, "admin")
    assert [p["max_concurrent_dossiers"] for p in c.get(RUTA).json()["plans"]] == [1, 3, 10]
    assert c.patch(f"{RUTA}/enterprise", json={"max_concurrent_dossiers": 12}).status_code == 200
    assert _limite(mundo.engine, "enterprise") == 12
