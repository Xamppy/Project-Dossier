"""S6.7 · Aislamiento entre organizaciones bajo carga (contra Postgres).

Con peticiones en paralelo de varias organizaciones, ninguna respuesta puede mezclar
datos de otra. Detecta estado compartido entre peticiones: una caché o una variable
global que guarde la organización «actual».

Requiere ``TEST_DATABASE_URL`` (fixture ``pg_vacia``).
"""
from __future__ import annotations

import json
import random
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from alembic import command
from dossier.api.app import app
from dossier.api.auth_routes import get_db_if_configured
from dossier.security.jwt_tokens import create_access_token

ORGANIZACIONES = 6
DOSSIERS_POR_ORG = 4
HILOS = 24
PETICIONES_POR_HILO = 15


def test_peticiones_en_paralelo_de_varias_organizaciones_no_se_mezclan(pg_vacia, alembic_cfg):
    command.upgrade(alembic_cfg, "head")
    orgs: list[dict] = []
    with pg_vacia.begin() as c:
        for i in range(ORGANIZACIONES):
            org = c.execute(
                text("INSERT INTO organizations (name, slug) VALUES (:n, :n) RETURNING id"), {"n": f"org{i}"}
            ).scalar_one()
            user = c.execute(
                text("INSERT INTO users (email) VALUES (:e) RETURNING id"), {"e": f"admin{i}@example.com"}
            ).scalar_one()
            c.execute(
                text(
                    "INSERT INTO org_memberships (organization_id, user_id, role, is_primary_org) "
                    "VALUES (:o, :u, 'admin', TRUE)"
                ),
                {"o": org, "u": user},
            )
            dossiers = [
                str(
                    c.execute(
                        text(
                            "INSERT INTO dossiers (organization_id, requested_by_user_id, status, subject_name, "
                            "dossier_data) VALUES (:o, :u, 'complete', :s, CAST(:d AS JSONB)) RETURNING id"
                        ),
                        {"o": org, "u": user, "s": f"sujeto-{i}-{j}", "d": json.dumps({"markdown": "x"})},
                    ).scalar_one()
                )
                for j in range(DOSSIERS_POR_ORG)
            ]
            token = create_access_token(
                user_id=str(user), email=f"admin{i}@example.com", organization_id=str(org), role="admin"
            )
            orgs.append({"org": str(org), "token": token, "dossiers": set(dossiers)})

    todos = set().union(*(o["dossiers"] for o in orgs))

    def _db():
        with Session(pg_vacia) as s:
            yield s

    def trabajo(semilla: int) -> list[str]:
        azar = random.Random(semilla)
        errores: list[str] = []
        cliente = TestClient(app, raise_server_exceptions=False)
        for _ in range(PETICIONES_POR_HILO):
            yo = azar.choice(orgs)
            cabecera = {"Authorization": f"Bearer {yo['token']}"}
            if azar.random() < 0.5:
                r = cliente.get("/dossiers?limit=100", headers=cabecera)
                vistos = {d["id"] for d in r.json().get("items", [])} if r.status_code == 200 else set()
                if r.status_code != 200 or vistos != yo["dossiers"] or r.json().get("organization_id") != yo["org"]:
                    errores.append(f"listado de {yo['org']}: {r.status_code}, ajenos={vistos - yo['dossiers']}")
            else:
                objetivo = azar.choice(sorted(todos))
                r = cliente.get(f"/dossiers/{objetivo}", headers=cabecera)
                esperado = 200 if objetivo in yo["dossiers"] else 404
                if r.status_code != esperado:
                    errores.append(f"{yo['org']} pidió {objetivo}: {r.status_code}, esperaba {esperado}")
                elif esperado == 200 and r.json()["organization_id"] != yo["org"]:
                    errores.append(f"{yo['org']} recibió un dossier de {r.json()['organization_id']}")
        return errores

    app.dependency_overrides[get_db_if_configured] = _db
    try:
        with ThreadPoolExecutor(max_workers=HILOS) as pool:
            resultados = list(pool.map(trabajo, range(HILOS)))
    finally:
        app.dependency_overrides.pop(get_db_if_configured, None)

    errores = [e for lista in resultados for e in lista]
    assert errores == [], f"{len(errores)} respuestas mezclaron organizaciones:\n" + "\n".join(errores[:10])
