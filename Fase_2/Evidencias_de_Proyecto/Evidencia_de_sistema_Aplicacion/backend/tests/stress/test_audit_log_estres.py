"""S4.10 · Registro de auditoría bajo concurrencia y degradación (pruebas de estrés).

Requieren ``TEST_DATABASE_URL`` (fixture ``pg_vacia``), salvo la de degradación.
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from alembic import command
from dossier.api.app import app
from dossier.api.auth_routes import get_db_if_configured
from dossier.security.jwt_tokens import create_access_token


def test_concurrencia_cien_lecturas_simultaneas_dejan_cien_registros(pg_vacia, alembic_cfg):
    command.upgrade(alembic_cfg, "head")
    with pg_vacia.begin() as c:
        org = c.execute(text("INSERT INTO organizations (name, slug) VALUES ('A', 'a') RETURNING id")).scalar_one()
        user = c.execute(text("INSERT INTO users (email) VALUES ('ana@example.com') RETURNING id")).scalar_one()
        c.execute(
            text("INSERT INTO org_memberships (organization_id, user_id, role, is_primary_org) VALUES (:o, :u, 'admin', TRUE)"),
            {"o": org, "u": user},
        )
        dossier = c.execute(
            text(
                "INSERT INTO dossiers (organization_id, requested_by_user_id, status, dossier_data) "
                "VALUES (:o, :u, 'complete', CAST(:d AS JSONB)) RETURNING id"
            ),
            {"o": org, "u": user, "d": json.dumps({"markdown": "# x"})},
        ).scalar_one()

    def _db():
        with Session(pg_vacia) as s:
            yield s

    token = create_access_token(user_id=str(user), email="ana@example.com", organization_id=str(org), role="admin")
    app.dependency_overrides[get_db_if_configured] = _db
    try:
        cliente = TestClient(app, headers={"Authorization": f"Bearer {token}"})
        with ThreadPoolExecutor(max_workers=20) as pool:
            estados = list(pool.map(lambda _: cliente.get(f"/dossiers/{dossier}").status_code, range(100)))
    finally:
        app.dependency_overrides.pop(get_db_if_configured, None)

    assert estados == [200] * 100
    with pg_vacia.connect() as c:
        total = c.execute(text("SELECT COUNT(*) FROM audit_logs WHERE resource_id = :d"), {"d": dossier}).scalar_one()
        firmas = c.execute(text("SELECT COUNT(DISTINCT log_hash) FROM audit_logs")).scalar_one()
    assert total == 100
    assert firmas == 100  # cada registro con su propia firma (instante distinto)


def test_degradacion_si_la_auditoria_falla_la_respuesta_no_cambia():
    """Una base caída para el registro no debe tumbar la lectura que ya se respondió."""

    class SesionRota:
        def add(self, *_):
            raise RuntimeError("base de auditoría caída")

        def rollback(self):
            pass

        def close(self):
            pass

    def _db():
        yield SesionRota()

    app.dependency_overrides[get_db_if_configured] = _db
    try:
        r = TestClient(app).get("/dossiers")  # sin token: 401, igual que sin auditoría
    finally:
        app.dependency_overrides.pop(get_db_if_configured, None)

    assert r.status_code == 401
