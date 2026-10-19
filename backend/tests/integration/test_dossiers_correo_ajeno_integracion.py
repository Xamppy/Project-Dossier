"""BUG-2026-10-19-07 · marcado de dossiers con el correo de otro asistente, contra Postgres.

Siembra filas con la forma que dejaba ``persist_calendar_dossiers`` antes de
BUG-2026-10-19-02 y verifica simulación, aplicación e idempotencia (CA10–CA12).
Requiere ``TEST_DATABASE_URL`` (fixture ``pg_vacia``).
"""
from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from alembic import command
from dossier.services.dossiers_correo_ajeno import main, marcar_dossiers_correo_ajeno

COLUMNAS = "id, subject_name, subject_email, dossier_data, updated_at, credits_consumed, status"


def _insertar(conn, org_id, user_id, *, nombre, correo, carpeta, rol="person", indice=None):
    dossier_data = {
        "format": "markdown",
        "body": f"# Informe de {nombre}",
        "pipeline": "person_research" if rol == "person" else "langgraph_corporate",
        "billing": "none",
        "calendar": {"provider": "google", "external_event_id": f"ev-{carpeta}"},
        "calendar_folder": {"id": str(carpeta), "title": "Reunión"},
        "calendar_folder_role": rol,
    }
    if rol == "person":
        dossier_data["person_filters"] = {
            "full_name": nombre,
            "email": correo,
            "contact_index": indice,
        }
    return conn.execute(
        text(
            "INSERT INTO dossiers (organization_id, requested_by_user_id, subject_name, "
            "subject_email, status, trigger_source, dossier_folder_id, dossier_data) "
            "VALUES (:o, :u, :n, :e, 'complete', 'calendar', :f, CAST(:d AS JSONB)) RETURNING id"
        ),
        {
            "o": org_id,
            "u": user_id,
            "n": nombre,
            "e": correo if rol == "person" else None,
            "f": carpeta,
            "d": json.dumps(dossier_data),
        },
    ).scalar_one()


@pytest.fixture
def sembrado(pg_vacia, alembic_cfg):
    command.upgrade(alembic_cfg, "head")
    reunion_afectada = uuid.uuid4()
    reunion_limpia = uuid.uuid4()
    reunion_unica = uuid.uuid4()
    with pg_vacia.begin() as conn:
        org_id = conn.execute(
            text("INSERT INTO organizations (name, slug) VALUES ('Org', 'org-bug07') RETURNING id")
        ).scalar_one()
        user_id = conn.execute(
            text("INSERT INTO users (email) VALUES ('bug07@example.test') RETURNING id")
        ).scalar_one()
        ids = {
            "corporativo": _insertar(
                conn, org_id, user_id, nombre="Acme", correo=None,
                carpeta=reunion_afectada, rol="corporate",
            ),
            "ana": _insertar(
                conn, org_id, user_id, nombre="Ana Pérez", correo="ana.perez@acme.com",
                carpeta=reunion_afectada, indice=1,
            ),
            "beto": _insertar(
                conn, org_id, user_id, nombre="Beto Soto", correo="ana.perez@acme.com",
                carpeta=reunion_afectada, indice=2,
            ),
            "carla": _insertar(
                conn, org_id, user_id, nombre="Carla Ruiz", correo="carla.ruiz@acme.com",
                carpeta=reunion_limpia, indice=1,
            ),
            "dario": _insertar(
                conn, org_id, user_id, nombre="Darío Vega", correo="dario.vega@acme.com",
                carpeta=reunion_limpia, indice=2,
            ),
            "elena": _insertar(
                conn, org_id, user_id, nombre="Elena Mora", correo="ventas@acme.com",
                carpeta=reunion_unica, indice=1,
            ),
        }
    return pg_vacia, ids


def _foto(engine):
    with engine.connect() as conn:
        filas = conn.execute(text(f"SELECT {COLUMNAS} FROM dossiers ORDER BY id")).mappings().all()
    return {str(f["id"]): dict(f) for f in filas}


def test_simulacion_informa_y_no_cambia_nada(sembrado):
    engine, ids = sembrado
    antes = _foto(engine)

    with Session(engine) as db:
        informe = marcar_dossiers_correo_ajeno(db, aplicar=False)

    assert informe["modo"] == "simulacion"
    assert [a["dossier_id"] for a in informe["afectados"]] == [str(ids["beto"])]
    assert informe["afectados"][0]["correo_anterior"] == "ana.perez@acme.com"
    assert informe["afectados"][0]["presunto_dueno"]["dossier_id"] == str(ids["ana"])
    assert informe["revisados"] == 5
    assert _foto(engine) == antes


def test_cli_por_defecto_y_con_dry_run_es_simulacion(sembrado, capsys):
    engine, ids = sembrado
    antes = _foto(engine)

    assert main([], engine=engine) == 0
    salida_defecto = json.loads(capsys.readouterr().out)
    assert main(["--dry-run"], engine=engine) == 0
    salida_dry_run = json.loads(capsys.readouterr().out)

    assert salida_defecto["modo"] == salida_dry_run["modo"] == "simulacion"
    assert [a["dossier_id"] for a in salida_defecto["afectados"]] == [str(ids["beto"])]
    assert _foto(engine) == antes


def test_aplicar_marca_solo_los_afectados(sembrado, capsys):
    engine, ids = sembrado
    antes = _foto(engine)

    assert main(["--aplicar"], engine=engine) == 0
    informe = json.loads(capsys.readouterr().out)
    despues = _foto(engine)

    assert informe["modo"] == "aplicado"
    beto = despues[str(ids["beto"])]
    assert beto["subject_email"] is None
    assert beto["dossier_data"]["person_filters"]["email"] is None
    marca = beto["dossier_data"]["correo_sospechoso"]
    assert marca["tarea"] == "BUG-2026-10-19-07"
    assert marca["motivo"] == "correo_de_otro_asistente"
    assert marca["correo_anterior"] == "ana.perez@acme.com"
    assert marca["presunto_dueno"] == {"dossier_id": str(ids["ana"]), "subject_name": "Ana Pérez"}
    assert beto["dossier_data"]["body"] == "# Informe de Beto Soto"
    assert beto["dossier_data"]["billing"] == "none"
    assert beto["credits_consumed"] == antes[str(ids["beto"])]["credits_consumed"]
    assert beto["status"] == "complete"

    for clave in ("corporativo", "ana", "carla", "dario", "elena"):
        assert despues[str(ids[clave])] == antes[str(ids[clave])], clave


def test_segunda_ejecucion_no_cambia_nada(sembrado):
    engine, _ids = sembrado
    with Session(engine) as db:
        primera = marcar_dossiers_correo_ajeno(db, aplicar=True)
    tras_primera = _foto(engine)

    with Session(engine) as db:
        segunda = marcar_dossiers_correo_ajeno(db, aplicar=True)

    assert len(primera["afectados"]) == 1
    assert segunda["afectados"] == []
    assert segunda["ya_marcados"] == 1
    assert _foto(engine) == tras_primera
