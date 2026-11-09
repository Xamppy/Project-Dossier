"""S4.10 · `audit_logs`: la tabla de la línea base, el ORM, la regla de solo inserción y el arranque.

La tabla ya existe desde la línea base (Migracion.md, sección 13): esta tarea no la
recrea. Requiere ``TEST_DATABASE_URL`` (fixture ``pg_vacia``).
"""
from __future__ import annotations

from sqlalchemy import inspect, text

from alembic import command
from dossier.db.models import AuditLog
from dossier.db.schema_patches import apply_schema_patches

TABLA = "audit_logs"
REVISION_ANTERIOR = "d5a9e3c7f2b8"


def _triggers(engine) -> set[str]:
    with engine.connect() as c:
        return set(
            c.execute(
                text("SELECT tgname FROM pg_trigger WHERE tgrelid = 'audit_logs'::regclass AND NOT tgisinternal")
            ).scalars()
        )


def test_la_tabla_de_la_linea_base_coincide_con_el_orm(pg_vacia, alembic_cfg):
    command.upgrade(alembic_cfg, "head")

    columnas = {c["name"] for c in inspect(pg_vacia).get_columns(TABLA)}
    assert columnas == set(AuditLog.__table__.columns.keys())


def test_upgrade_agrega_la_regla_de_solo_insercion_sin_recrear_la_tabla(pg_vacia, alembic_cfg):
    command.upgrade(alembic_cfg, REVISION_ANTERIOR)
    with pg_vacia.begin() as c:
        c.execute(text("INSERT INTO audit_logs (action) VALUES ('registro previo')"))

    command.upgrade(alembic_cfg, "head")

    assert "trg_audit_logs_inmutable" in _triggers(pg_vacia)
    with pg_vacia.connect() as c:  # los registros que ya había siguen ahí
        assert c.execute(text("SELECT COUNT(*) FROM audit_logs")).scalar_one() == 1


def test_downgrade_quita_solo_la_regla(pg_vacia, alembic_cfg):
    command.upgrade(alembic_cfg, "head")
    command.downgrade(alembic_cfg, REVISION_ANTERIOR)

    assert TABLA in inspect(pg_vacia).get_table_names()
    assert "trg_audit_logs_inmutable" not in _triggers(pg_vacia)


def test_el_arranque_aplica_la_regla_y_es_idempotente(pg_vacia, alembic_cfg):
    command.upgrade(alembic_cfg, REVISION_ANTERIOR)

    apply_schema_patches(pg_vacia)
    apply_schema_patches(pg_vacia)

    assert "trg_audit_logs_inmutable" in _triggers(pg_vacia)
