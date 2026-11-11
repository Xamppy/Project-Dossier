"""UX-ADMIN-03 · Créditos al mes de cada plan, configurables por el admin de plataforma.

Antes eran fijos en el código (Free 10, Pro 500, Enterprise 50.000). Ahora viven en
``plan_settings.monthly_credits`` y se aplican al registrarse (plan Free) y al cambiar de plan.
El saldo de las organizaciones que ya existen no cambia. Requiere ``TEST_DATABASE_URL``.
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
CLAVE = "Clave-segura-123!"


@pytest.fixture
def mundo(pg_vacia, alembic_cfg, monkeypatch) -> Iterator[SimpleNamespace]:
    command.upgrade(alembic_cfg, "head")
    monkeypatch.delenv("ORG_SIGNUP_CREDITS", raising=False)
    monkeypatch.delenv("ORG_SIGNUP_CREDITS_MONTHLY_LIMIT", raising=False)
    m = SimpleNamespace(engine=pg_vacia, alembic_cfg=alembic_cfg)
    with pg_vacia.begin() as c:
        m.org = org(c, "Operaciones", "free")
        m.plataforma = usuario(c, "ops@alloxentric.com", m.org, "admin")
        c.execute(text("UPDATE users SET is_platform_admin = true WHERE id = :u"), {"u": m.plataforma})
        m.cliente_org = org(c, "Cliente", "free")
        m.admin_cliente = usuario(c, "jefe@cliente.com", m.cliente_org, "admin")

    def _db():
        with Session(pg_vacia) as s:
            yield s

    app.dependency_overrides[get_db_if_configured] = _db
    yield m
    app.dependency_overrides.clear()


def _admin(m) -> TestClient:
    return cliente(m.plataforma, m.org, "admin")


def _saldo(engine, org_id) -> tuple[int, int]:
    with engine.connect() as c:
        fila = c.execute(
            text("SELECT credits_balance, credits_monthly_limit FROM organizations WHERE id = :o"), {"o": org_id}
        ).one()
    return fila.credits_balance, fila.credits_monthly_limit


# --- Panel ---------------------------------------------------------------------------------


def test_los_planes_traen_sus_creditos_al_mes_iniciales(mundo):
    planes = _admin(mundo).get(RUTA).json()["plans"]
    assert [(p["plan"], p["monthly_credits"]) for p in planes] == [
        ("free", 10),
        ("pro", 500),
        ("enterprise", 50_000),
    ]


def test_cambiar_solo_los_creditos_persiste_y_queda_auditado(mundo):
    resp = _admin(mundo).patch(f"{RUTA}/pro", json={"monthly_credits": 800})
    assert resp.status_code == 200, resp.text
    assert (resp.json()["monthly_credits"], resp.json()["max_concurrent_dossiers"]) == (800, 3)
    with mundo.engine.connect() as c:
        auditoria = c.execute(
            text("SELECT request_data FROM audit_logs WHERE action = 'ADMIN plan_settings' ORDER BY created_at DESC")
        ).scalars().first()
    assert auditoria == {"plan": "pro", "monthly_credits": {"antes": 500, "despues": 800}}


def test_cambiar_ambos_valores_a_la_vez(mundo):
    resp = _admin(mundo).patch(f"{RUTA}/free", json={"monthly_credits": 25, "max_concurrent_dossiers": 2})
    assert resp.status_code == 200
    assert (resp.json()["monthly_credits"], resp.json()["max_concurrent_dossiers"]) == (25, 2)


@pytest.mark.parametrize(
    "cuerpo",
    [
        {},
        {"monthly_credits": -1},
        {"monthly_credits": 1_000_001},
        {"monthly_credits": "50"},
        {"monthly_credits": 2.5},
        {"monthly_credits": None},
        {"max_concurrent_dossiers": None},
        {"monthly_credits": 10, "precio": 5},
    ],
)
def test_rechaza_valores_invalidos(mundo, cuerpo):
    assert _admin(mundo).patch(f"{RUTA}/pro", json=cuerpo).status_code == 422


def test_solo_el_admin_de_plataforma_cambia_los_creditos(mundo):
    resp = cliente(mundo.admin_cliente, mundo.cliente_org, "admin").patch(f"{RUTA}/pro", json={"monthly_credits": 1})
    assert resp.status_code == 403


# --- Dónde se aplica -----------------------------------------------------------------------


def test_cambiar_de_plan_entrega_los_creditos_configurados(mundo):
    _admin(mundo).patch(f"{RUTA}/pro", json={"monthly_credits": 800})
    jefe = cliente(mundo.admin_cliente, mundo.cliente_org, "admin")
    resp = jefe.patch("/auth/organization/plan", json={"plan": "pro"})
    assert resp.status_code == 200, resp.text
    assert _saldo(mundo.engine, mundo.cliente_org) == (800, 800)


def test_cambiar_la_configuracion_no_toca_el_saldo_de_quien_ya_existe(mundo):
    antes = _saldo(mundo.engine, mundo.cliente_org)
    _admin(mundo).patch(f"{RUTA}/free", json={"monthly_credits": 99})
    assert _saldo(mundo.engine, mundo.cliente_org) == antes


def test_el_registro_usa_los_creditos_del_plan_free(mundo):
    _admin(mundo).patch(f"{RUTA}/free", json={"monthly_credits": 25})
    resp = TestClient(app).post(
        "/auth/register",
        json={"email": "nuevo@example.com", "password": CLAVE, "full_name": "Nuevo", "workspace_kind": "personal"},
    )
    assert resp.status_code == 200, resp.text
    with mundo.engine.connect() as c:
        org_nueva = c.execute(
            text(
                "SELECT o.id FROM organizations o JOIN org_memberships m ON m.organization_id = o.id "
                "JOIN users u ON u.id = m.user_id WHERE u.email = 'nuevo@example.com'"
            )
        ).scalar_one()
    assert _saldo(mundo.engine, org_nueva) == (25, 25)


def test_la_variable_de_entorno_sigue_mandando_si_esta_definida(mundo, monkeypatch):
    monkeypatch.setenv("ORG_SIGNUP_CREDITS", "7")
    _admin(mundo).patch(f"{RUTA}/free", json={"monthly_credits": 25})
    resp = TestClient(app).post(
        "/auth/register",
        json={"email": "otro@example.com", "password": CLAVE, "full_name": "Otro", "workspace_kind": "personal"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["user"]["credits_balance"] == 7


def test_las_tarjetas_de_planes_leen_los_creditos_configurados(mundo):
    _admin(mundo).patch(f"{RUTA}/pro", json={"monthly_credits": 800})
    resp = cliente(mundo.admin_cliente, mundo.cliente_org, "admin").get("/billing/plans")
    assert resp.status_code == 200
    assert resp.json() == {
        "plans": [
            {"plan": "free", "monthly_credits": 10},
            {"plan": "pro", "monthly_credits": 800},
            {"plan": "enterprise", "monthly_credits": 50_000},
        ]
    }


def test_la_migracion_se_puede_deshacer_y_rehacer(mundo):
    command.downgrade(mundo.alembic_cfg, "d4f6a8c2e0b3")
    with mundo.engine.connect() as c:
        columnas = c.execute(
            text("SELECT column_name FROM information_schema.columns WHERE table_name = 'plan_settings'")
        ).scalars().all()
    assert "monthly_credits" not in columnas
    command.upgrade(mundo.alembic_cfg, "head")
    assert [p["monthly_credits"] for p in _admin(mundo).get(RUTA).json()["plans"]] == [10, 500, 50_000]
