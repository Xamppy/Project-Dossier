"""S3.9 · La tabla `refresh_tokens` en Alembic, en el ORM y en los parches de arranque.

Requiere ``TEST_DATABASE_URL`` (fixture ``pg_vacia``).
"""
from __future__ import annotations

from sqlalchemy import inspect, text

from alembic import command
from dossier.db.models import RefreshToken
from dossier.db.schema_patches import apply_schema_patches

TABLA = "refresh_tokens"
REVISION_ANTERIOR = "c4d8a2f6b1e9"


def _columnas(engine) -> set[str]:
    return {c["name"] for c in inspect(engine).get_columns(TABLA)}


def test_upgrade_head_deja_la_tabla_igual_que_el_orm(pg_vacia, alembic_cfg):
    command.upgrade(alembic_cfg, "head")

    assert _columnas(pg_vacia) == set(RefreshToken.__table__.columns.keys())
    assert "revoked_at" in _columnas(pg_vacia)


def test_downgrade_quita_solo_la_columna_nueva(pg_vacia, alembic_cfg):
    command.upgrade(alembic_cfg, "head")
    command.downgrade(alembic_cfg, REVISION_ANTERIOR)

    assert TABLA in inspect(pg_vacia).get_table_names()  # la tabla es de la línea base
    assert "revoked_at" not in _columnas(pg_vacia)


def test_el_arranque_agrega_la_columna_y_es_idempotente(pg_vacia, alembic_cfg):
    """Base creada antes de S3.9 y sin create_all (DATABASE_AUTO_CREATE_TABLES=0)."""
    command.upgrade(alembic_cfg, REVISION_ANTERIOR)
    assert "revoked_at" not in _columnas(pg_vacia)

    apply_schema_patches(pg_vacia)
    apply_schema_patches(pg_vacia)

    assert "revoked_at" in _columnas(pg_vacia)


def test_borrar_el_usuario_borra_sus_tokens(pg_vacia, alembic_cfg):
    command.upgrade(alembic_cfg, "head")
    with pg_vacia.begin() as c:
        org = c.execute(text("INSERT INTO organizations (name, slug) VALUES ('A','a') RETURNING id")).scalar_one()
        user = c.execute(text("INSERT INTO users (email) VALUES ('a@a.cl') RETURNING id")).scalar_one()
        c.execute(
            text(
                "INSERT INTO refresh_tokens (user_id, organization_id, token_hash, expires_at) "
                "VALUES (:u, :o, 'h', NOW() + INTERVAL '1 day')"
            ),
            {"u": user, "o": org},
        )
        c.execute(text("DELETE FROM users WHERE id = :u"), {"u": user})
        assert c.execute(text("SELECT COUNT(*) FROM refresh_tokens")).scalar_one() == 0
