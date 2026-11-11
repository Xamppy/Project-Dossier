"""S5.5/S3.5/S3.6 · ``modules`` en ``GET /dossiers/{id}`` contra Postgres.

Requiere ``TEST_DATABASE_URL`` (fixture ``pg_vacia``). El aislamiento está en
tests/security/test_dossier_modulos_seguridad.py.
"""
from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from alembic import command
from dossier.api.app import app
from dossier.api.auth_routes import get_db_if_configured
from dossier.security.jwt_tokens import create_access_token
from dossier.services.dossier_modules import MAX_MENCIONES
from tests.test_dossier_modulos import mencion, registro


def org(c, nombre: str):
    return c.execute(
        text("INSERT INTO organizations (name, slug) VALUES (:n, :s) RETURNING id"),
        {"n": nombre, "s": nombre.lower()},
    ).scalar_one()


def usuario(c, email: str, org_id, role: str = "admin"):
    uid = c.execute(text("INSERT INTO users (email) VALUES (:e) RETURNING id"), {"e": email}).scalar_one()
    c.execute(
        text(
            "INSERT INTO org_memberships (organization_id, user_id, role, is_primary_org) "
            "VALUES (:o, :u, :r, true)"
        ),
        {"o": org_id, "u": uid, "r": role},
    )
    return uid


def dossier(c, org_id, user_id, data: dict):
    return c.execute(
        text(
            "INSERT INTO dossiers (organization_id, requested_by_user_id, status, subject_name, dossier_data) "
            "VALUES (:o, :u, 'complete', 'Acme', CAST(:d AS JSONB)) RETURNING id"
        ),
        {"o": org_id, "u": user_id, "d": json.dumps(data)},
    ).scalar_one()


def prensa(c, dossier_id, titulo: str, cuando: datetime | None = None, url: str = "https://medio.example/a"):
    c.execute(
        text(
            "INSERT INTO dossier_media_mentions (dossier_id, title, url, published_at, source_name, summary, "
            "source_type, source_citation) VALUES (:d, :t, :u, :p, 'Medio', 'Resumen', 'gdelt_news', "
            "CAST(:c AS JSONB))"
        ),
        {
            "d": dossier_id,
            "t": titulo,
            "u": url,
            "p": cuando,
            "c": json.dumps(
                {"source_type": "gdelt_news", "source_name": "GDELT DOC 2.0", "retrieved_at": "2026-11-11T12:00:00Z"}
            ),
        },
    )


def cliente(user_id, org_id, role: str = "admin") -> TestClient:
    tok = create_access_token(user_id=str(user_id), email="x@example.com", organization_id=str(org_id), role=role)
    return TestClient(app, headers={"Authorization": f"Bearer {tok}"}, raise_server_exceptions=False)


@pytest.fixture
def base(pg_vacia, alembic_cfg) -> Iterator[SimpleNamespace]:
    command.upgrade(alembic_cfg, "head")
    m = SimpleNamespace(engine=pg_vacia)
    with pg_vacia.begin() as c:
        m.org = org(c, "Propia")
        m.admin = usuario(c, "admin@propia.com", m.org)

    def _db():
        with Session(pg_vacia) as s:
            yield s

    app.dependency_overrides[get_db_if_configured] = _db
    yield m
    app.dependency_overrides.clear()


def _modules(base, dossier_id) -> dict:
    resp = cliente(base.admin, base.org).get(f"/dossiers/{dossier_id}")
    assert resp.status_code == 200
    return resp.json()["modules"]


def test_ca2_dossier_de_empresa_con_registros_y_prensa(base):
    with base.engine.begin() as c:
        d = dossier(
            c, base.org, base.admin,
            {"format": "markdown", "body": "# Acme", "modulos": {"registros_europeos": [registro()]}},
        )
        prensa(c, d, "Antigua", datetime(2026, 9, 1, tzinfo=UTC))
        prensa(c, d, "Reciente", datetime(2026, 11, 1, tzinfo=UTC))
        prensa(c, d, "Sin fecha", None)

    modules = _modules(base, d)
    assert [r["record"]["razon_social"] for r in modules["corporate_records"]] == ["Acme France SAS"]
    assert "datos_brutos" not in modules["corporate_records"][0]["record"]
    # Más recientes primero; las que no tienen fecha, al final.
    assert [m["headline"] for m in modules["press_mentions"]] == ["Reciente", "Antigua", "Sin fecha"]
    assert modules["press_mentions"][0]["source"]["source_name"] == "GDELT DOC 2.0"


def test_ca2_dossier_estructurado_usa_su_contrato(base):
    from tests.integration.test_dossier_detail_content_kind import _payload_minimo

    payload = {**_payload_minimo(), "corporate_records": [registro("Del contrato")], "press_mentions": [mencion()]}
    with base.engine.begin() as c:
        d = dossier(c, base.org, base.admin, {"format": "markdown", "body": "# x", "executive_payload": payload})
        prensa(c, d, "De la tabla")

    modules = _modules(base, d)
    assert [r["record"]["razon_social"] for r in modules["corporate_records"]] == ["Del contrato"]
    assert [m["headline"] for m in modules["press_mentions"]] == ["Acme abre oficina"]


def test_ca2_historico_sin_datos_devuelve_listas_vacias(base):
    with base.engine.begin() as c:
        d = dossier(c, base.org, base.admin, {"format": "markdown", "body": "# Histórico"})
    assert _modules(base, d) == {"corporate_records": [], "press_mentions": []}


def test_ca3_datos_corruptos_no_rompen_el_detalle(base):
    with base.engine.begin() as c:
        d = dossier(
            c, base.org, base.admin,
            {"body": "# x", "modulos": {"registros_europeos": [{"record": "basura"}, registro("Válido")]}},
        )
        prensa(c, d, "Con enlace peligroso", url="javascript:alert(1)")
    modules = _modules(base, d)
    assert [r["record"]["razon_social"] for r in modules["corporate_records"]] == ["Válido"]
    assert modules["press_mentions"][0]["url"] is None


def test_la_prensa_tiene_tope(base):
    inicio = datetime(2026, 1, 1, tzinfo=UTC)
    with base.engine.begin() as c:
        d = dossier(c, base.org, base.admin, {"body": "# x"})
        for i in range(MAX_MENCIONES + 20):
            prensa(c, d, f"T{i}", inicio + timedelta(days=i))
    menciones = _modules(base, d)["press_mentions"]
    assert len(menciones) == MAX_MENCIONES
    assert menciones[0]["headline"] == f"T{MAX_MENCIONES + 19}"
