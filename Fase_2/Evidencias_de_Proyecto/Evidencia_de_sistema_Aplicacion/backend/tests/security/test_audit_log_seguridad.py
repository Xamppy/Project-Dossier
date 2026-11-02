"""S4.10 · Lo que el registro de auditoría NO debe permitir (pruebas de seguridad).

Hallazgo de origen: docs/security/README.md, "Sin rastro de acceso a datos personales".
Requiere ``TEST_DATABASE_URL`` (fixture ``pg_vacia``).
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from alembic import command
from dossier.api.app import app
from dossier.api.auth_routes import get_db_if_configured
from dossier.db.models import AuditLog
from dossier.security.jwt_tokens import create_access_token
from dossier.services import audit_log as al


@pytest.fixture
def base(pg_vacia, alembic_cfg):
    command.upgrade(alembic_cfg, "head")
    with pg_vacia.begin() as c:
        org = c.execute(text("INSERT INTO organizations (name, slug) VALUES ('A', 'a') RETURNING id")).scalar_one()
        user = c.execute(text("INSERT INTO users (email) VALUES ('ana@example.com') RETURNING id")).scalar_one()
        c.execute(
            text("INSERT INTO org_memberships (organization_id, user_id, role, is_primary_org) VALUES (:o, :u, 'admin', TRUE)"),
            {"o": org, "u": user},
        )
    with Session(pg_vacia) as s:
        al.record(s, al.AuditEvent(action="GET /dossiers", resource_type="dossier", user_id=user, organization_id=org))
        s.commit()
    return pg_vacia, org, user


# --------------------------------------------------------------------------
# Solo inserción
# --------------------------------------------------------------------------


def test_no_se_puede_modificar_un_registro(base):
    engine, _, _ = base
    with pytest.raises(DBAPIError, match="solo inserción"), engine.begin() as c:
        c.execute(text("UPDATE audit_logs SET http_status = 200"))


def test_no_se_puede_borrar_un_registro(base):
    engine, _, _ = base
    with pytest.raises(DBAPIError, match="solo inserción"), engine.begin() as c:
        c.execute(text("DELETE FROM audit_logs"))


def test_no_se_puede_cambiar_el_actor_por_otro(base):
    """Solo se permite que el usuario pase a NULL (lo hace la base al borrarlo), no reemplazarlo."""
    engine, _, _ = base
    with engine.begin() as c:
        otro =c.execute(text("INSERT INTO users (email) VALUES ('otro@example.com') RETURNING id")).scalar_one()
    with pytest.raises(DBAPIError, match="solo inserción"), engine.begin() as c:
        c.execute(text("UPDATE audit_logs SET user_id = :o"), {"o": otro})


def test_borrar_el_usuario_sigue_siendo_posible_y_conserva_el_registro(base):
    """Derecho al olvido: se borra la cuenta; el registro queda, anónimo y con su firma válida."""
    engine, _, user = base
    with engine.begin() as c:
        c.execute(text("DELETE FROM users WHERE id = :u"), {"u": user})

    with Session(engine) as s:
        fila = s.scalars(select(AuditLog)).one()
    assert fila.user_id is None
    assert al.verify_log_hash(fila) is True


# --------------------------------------------------------------------------
# Sin datos personales
# --------------------------------------------------------------------------


def test_el_registro_no_guarda_datos_personales_de_la_consulta(pg_vacia, alembic_cfg):
    command.upgrade(alembic_cfg, "head")
    with pg_vacia.begin() as c:
        org = c.execute(text("INSERT INTO organizations (name, slug) VALUES ('A', 'a') RETURNING id")).scalar_one()
        user = c.execute(text("INSERT INTO users (email) VALUES ('ana@example.com') RETURNING id")).scalar_one()
        c.execute(
            text("INSERT INTO org_memberships (organization_id, user_id, role, is_primary_org) VALUES (:o, :u, 'admin', TRUE)"),
            {"o": org, "u": user},
        )

    def _db():
        with Session(pg_vacia) as s:
            yield s

    token = create_access_token(user_id=str(user), email="ana@example.com", organization_id=str(org), role="admin")
    app.dependency_overrides[get_db_if_configured] = _db
    try:
        TestClient(app).get(
            "/dossiers",
            params={"limit": 5, "email": "victima@empresa.cl", "full_name": "Ana Prueba"},
            headers={"Authorization": f"Bearer {token}"},
        )
    finally:
        app.dependency_overrides.pop(get_db_if_configured, None)

    with pg_vacia.connect() as c:
        volcado = json.dumps([dict(r._mapping) for r in c.execute(text("SELECT * FROM audit_logs"))], default=str)
    assert "victima@empresa.cl" not in volcado
    assert "Ana Prueba" not in volcado
    assert token not in volcado


def test_un_registro_alterado_a_mano_se_detecta(base):
    """Aun desactivando la regla (p. ej. un administrador de la base), la firma delata el cambio."""
    engine, _, _ = base
    with engine.begin() as c:
        c.execute(text("ALTER TABLE audit_logs DISABLE TRIGGER trg_audit_logs_inmutable"))
        c.execute(text("UPDATE audit_logs SET http_status = 200, success = TRUE"))
        c.execute(text("ALTER TABLE audit_logs ENABLE TRIGGER trg_audit_logs_inmutable"))

    with Session(engine) as s:
        fila = s.scalars(select(AuditLog)).one()
    assert al.verify_log_hash(fila) is False
