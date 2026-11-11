"""S5.5 · ``modules`` solo trae datos del dossier pedido (CA4), contra Postgres.

- La prensa de otro dossier, de la misma u otra organización, no aparece.
- Un dossier de otra organización sigue dando 404 (no se filtra nada por ``modules``).
- Un viewer sin el dossier compartido no lo ve.

Requiere ``TEST_DATABASE_URL`` (fixture ``pg_vacia``).
"""
from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace

import pytest
from sqlalchemy.orm import Session

from alembic import command
from dossier.api.app import app
from dossier.api.auth_routes import get_db_if_configured
from tests.integration.test_dossier_modulos_integracion import cliente, dossier, org, prensa, usuario
from tests.test_dossier_modulos import registro


@pytest.fixture
def mundo(pg_vacia, alembic_cfg) -> Iterator[SimpleNamespace]:
    command.upgrade(alembic_cfg, "head")
    m = SimpleNamespace()
    with pg_vacia.begin() as c:
        m.org_a, m.org_b = org(c, "A"), org(c, "B")
        m.a_admin = usuario(c, "admin@a.com", m.org_a)
        m.a_viewer = usuario(c, "viewer@a.com", m.org_a, "viewer")
        m.b_admin = usuario(c, "admin@b.com", m.org_b)
        m.d_a = dossier(c, m.org_a, m.a_admin, {"body": "# A"})
        m.d_a2 = dossier(c, m.org_a, m.a_admin, {"body": "# A2"})
        m.d_b = dossier(
            c, m.org_b, m.b_admin, {"body": "# B", "modulos": {"registros_europeos": [registro("Secreto B")]}}
        )
        prensa(c, m.d_a, "Prensa de A")
        prensa(c, m.d_a2, "Prensa de otro dossier de A")
        prensa(c, m.d_b, "Prensa secreta de B")

    def _db():
        with Session(pg_vacia) as s:
            yield s

    app.dependency_overrides[get_db_if_configured] = _db
    yield m
    app.dependency_overrides.clear()


def test_solo_la_prensa_del_dossier_pedido(mundo):
    resp = cliente(mundo.a_admin, mundo.org_a).get(f"/dossiers/{mundo.d_a}")
    assert resp.status_code == 200
    assert [p["headline"] for p in resp.json()["modules"]["press_mentions"]] == ["Prensa de A"]
    assert "secreta" not in resp.text
    assert "Secreto B" not in resp.text


def test_dossier_de_otra_organizacion_404_sin_modulos(mundo):
    resp = cliente(mundo.a_admin, mundo.org_a).get(f"/dossiers/{mundo.d_b}")
    assert resp.status_code == 404
    assert "Secreto B" not in resp.text
    assert "secreta" not in resp.text


def test_viewer_sin_compartir_no_ve_los_modulos(mundo):
    resp = cliente(mundo.a_viewer, mundo.org_a, "viewer").get(f"/dossiers/{mundo.d_a}")
    assert resp.status_code == 404
    assert "Prensa de A" not in resp.text
