"""Plantilla viva de pruebas de seguridad.

Cubren los cuatro controles del objetivo específico 8: control de acceso,
limitación de tasa, registro de auditoría y retención de 24 horas.

Hoy solo existe el primero. Las pruebas de los otros tres están escritas como
esqueleto con `skip` y su tarea asociada: cuando la tarea se implemente, se quita
el `skip` y la prueba ya dice qué debe cumplir. Eso es TDD a escala de sprint.

Ver docs/dev/testing-policy.md §1 y docs/security/README.md.
"""
from __future__ import annotations

import os

import pytest

from dossier.security.jwt_tokens import (
    create_access_token,
    decode_access_token,
)

# --------------------------------------------------------------------------
# Control de acceso — implementado
# --------------------------------------------------------------------------

def test_token_valido_se_decodifica_con_sus_datos():
    """Caso normal: lo que se firma es lo que se lee."""
    token = create_access_token(
        user_id="u-1",
        email="persona@ejemplo.cl",
        organization_id="org-1",
        role="user",
    )
    datos = decode_access_token(token)

    assert datos["sub"] == "u-1"
    assert datos["email"] == "persona@ejemplo.cl"
    # La clave del payload es `org_id`, no `organization_id`: el parámetro y el
    # campo firmado tienen nombres distintos (jwt_tokens.py:48).
    assert datos["org_id"] == "org-1"
    assert datos["role"] == "user"


def test_token_manipulado_es_rechazado():
    """Caso de error: alterar el token invalida la firma."""
    token = create_access_token(user_id="u-1", email="persona@ejemplo.cl")
    manipulado = token[:-6] + "AAAAAA"

    with pytest.raises(Exception):
        decode_access_token(manipulado)


def test_token_con_otra_clave_es_rechazado():
    """Caso de error: un token firmado con otra clave no vale.

    Es la prueba que demuestra que `JWT_SECRET` cumple su función.
    """
    token = create_access_token(user_id="u-1", email="persona@ejemplo.cl")

    previo = os.environ["JWT_SECRET"]
    os.environ["JWT_SECRET"] = "una-clave-distinta-de-la-original-xyz"
    try:
        with pytest.raises(Exception):
            decode_access_token(token)
    finally:
        os.environ["JWT_SECRET"] = previo


def test_vigencia_del_token_de_acceso_es_corta(monkeypatch):
    """La vigencia por omisión era de 7 días (10080 minutos); S3.9 la bajó a 15.

    Habilitada con S3.9. Queda como red de seguridad: si alguien vuelve a subir
    el valor por omisión por encima de 15 minutos, falla.

    Ver docs/security/README.md, "Token de acceso de 7 días en localStorage".
    """
    import jwt

    monkeypatch.delenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", raising=False)
    token = create_access_token(user_id="u-1", email="persona@ejemplo.cl")
    claims = jwt.decode(token, options={"verify_signature": False})

    assert claims["exp"] - claims["iat"] <= 15 * 60


# --------------------------------------------------------------------------
# Aislamiento entre organizaciones — S6.7
# --------------------------------------------------------------------------
#
# Prueba NEGATIVA: no verifica que algo funcione, sino que algo NO sea posible.
# Es la más valiosa de este proyecto, porque una fuga entre organizaciones es el
# fallo más caro que puede tener un sistema multiempresa.
#
# Patrón:
#   1. Crea dos organizaciones con un recurso cada una
#   2. Autentica como la organización A
#   3. Pide el recurso de la organización B
#   4. Verifica que la respuesta es 404 o 403, NUNCA el recurso
#
# Implementado en S6.7: tests/security/test_aislamiento_organizaciones.py (contra Postgres)
# y tests/stress/test_aislamiento_organizaciones_estres.py (bajo carga). Las tres pruebas
# que esperaban aquí viven allá con el mismo nombre.


# --------------------------------------------------------------------------
# Limitación de tasa — S5.8
# --------------------------------------------------------------------------

def _post_refresh_sin_db(veces: int) -> list[int]:
    from fastapi.testclient import TestClient

    from dossier.api.app import app
    from dossier.api.auth_routes import get_db_if_configured

    def _sin_db():
        yield None

    app.dependency_overrides[get_db_if_configured] = _sin_db
    try:
        cliente = TestClient(app, raise_server_exceptions=False)
        return [cliente.post("/auth/refresh").status_code for _ in range(veces)]
    finally:
        app.dependency_overrides.pop(get_db_if_configured, None)


def test_superado_el_umbral_la_api_responde_429(monkeypatch):
    """Habilitada con S5.8."""
    monkeypatch.setenv("AUTH_RATE_LIMIT", "2/60")
    assert _post_refresh_sin_db(3) == [401, 401, 429]


def test_pasada_la_ventana_la_api_vuelve_a_aceptar(monkeypatch):
    """Habilitada con S5.8. El reloj del limitador se adelanta en vez de esperar un minuto."""
    from dossier.security import rate_limit as rl

    ahora = [1000.0]
    monkeypatch.setattr(rl, "_reloj", lambda: ahora[0])
    monkeypatch.setenv("AUTH_RATE_LIMIT", "1/60")
    assert _post_refresh_sin_db(2) == [401, 429]

    ahora[0] += 61

    assert _post_refresh_sin_db(1) == [401]


# --------------------------------------------------------------------------
# Auditoría — S4.10 y S6.6
# --------------------------------------------------------------------------

def test_leer_un_dossier_deja_registro_de_auditoria():
    """Con actor, organización, recurso e instante. Habilitada con S4.10.

    Sin Postgres: una sesión falsa recoge lo que el middleware registra. El flujo
    completo contra la base está en tests/integration/test_audit_log_flujo.py.
    """
    import uuid

    from fastapi.testclient import TestClient

    from dossier.api.app import app
    from dossier.api.auth_routes import get_db_if_configured
    from dossier.db.models import AuditLog

    registrados: list = []

    class SesionQueRecoge:
        def add(self, obj):
            registrados.append(obj)

        def flush(self):
            pass

        def commit(self):
            pass

        def rollback(self):
            pass

        def close(self):
            pass

        def get(self, *_args, **_kwargs):
            return None

    def _db():
        yield SesionQueRecoge()

    usuario, organizacion, dossier = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    token = create_access_token(
        user_id=str(usuario), email="persona@ejemplo.cl", organization_id=str(organizacion), role="user"
    )
    app.dependency_overrides[get_db_if_configured] = _db
    try:
        TestClient(app, raise_server_exceptions=False).get(
            f"/dossiers/{dossier}", headers={"Authorization": f"Bearer {token}"}
        )
    finally:
        app.dependency_overrides.pop(get_db_if_configured, None)

    auditoria = [r for r in registrados if isinstance(r, AuditLog)]
    assert len(auditoria) == 1
    fila = auditoria[0]
    assert (fila.user_id, fila.organization_id) == (usuario, organizacion)
    assert (fila.resource_type, fila.resource_id) == ("dossier", dossier)
    assert fila.created_at is not None


@pytest.mark.skip(reason="Se habilita con S6.6")
def test_enviar_y_borrar_dejan_registro_de_auditoria():
    raise NotImplementedError


# --------------------------------------------------------------------------
# Retención de 24 horas — S6.5
# --------------------------------------------------------------------------

_TABLAS_HIJAS = (
    "dossier_alerts",
    "dossier_media_mentions",
    "dossier_corporate_records",
    "dossier_career_entries",
    "dossier_ice_breakers",
    "dossier_shares",
)


def _org_y_usuario_s65(conn, retencion):
    import uuid

    from sqlalchemy import text

    sufijo = uuid.uuid4().hex[:8]
    org = conn.execute(
        text("INSERT INTO organizations (name, slug) VALUES (:n, :s) RETURNING id"),
        {"n": f"Org {sufijo}", "s": f"org-{sufijo}"},
    ).scalar_one()
    user = conn.execute(
        text("INSERT INTO users (email, dossier_retention_days) VALUES (:e, :r) RETURNING id"),
        {"e": f"s65-{sufijo}@example.test", "r": retencion},
    ).scalar_one()
    return org, user


def _dossier_s65(conn, org, user, horas):
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import text

    return conn.execute(
        text(
            "INSERT INTO dossiers (organization_id, requested_by_user_id, dossier_data, created_at) "
            "VALUES (:o, :u, CAST('{\"body\": \"Ana Pérez\"}' AS JSONB), :c) RETURNING id"
        ),
        {"o": org, "u": user, "c": datetime.now(UTC) - timedelta(hours=horas)},
    ).scalar_one()


@pytest.mark.parametrize("retencion_elegida", [None, 90])
def test_pasadas_24_horas_el_dossier_no_es_recuperable(pg_vacia, alembic_cfg, retencion_elegida):
    """Borrado EFECTIVO, no solo marca de borrado (S6.5, CA2).

    Vale aunque el usuario hubiera elegido conservar indefinidamente (``None``) o 90 días:
    la retención de 24 h ya no depende de esa preferencia.
    """
    from sqlalchemy import text
    from sqlalchemy.orm import Session

    from alembic import command
    from dossier.services.dossier_retention_worker import purge_expired_dossiers

    command.upgrade(alembic_cfg, "head")
    with pg_vacia.begin() as conn:
        org, user = _org_y_usuario_s65(conn, retencion_elegida)
        vencido = _dossier_s65(conn, org, user, horas=25)

    with Session(pg_vacia) as db:
        resultado = purge_expired_dossiers(db)

    assert resultado.dossiers_borrados == 1
    assert resultado.verificado is True
    with pg_vacia.connect() as conn:
        quedan = conn.execute(
            text("SELECT count(*) FROM dossiers WHERE id = :d"), {"d": vencido}
        ).scalar_one()
        # Tampoco queda el contenido en ninguna parte de la tabla: no es un borrado lógico.
        con_nombre = conn.execute(
            text("SELECT count(*) FROM dossiers WHERE dossier_data::text LIKE '%Ana Pérez%'")
        ).scalar_one()
    assert quedan == 0
    assert con_nombre == 0


def test_el_borrado_arrastra_alertas_trayectoria_y_prensa(pg_vacia, alembic_cfg):
    """Sin entidades huérfanas: el borrado debe ser completo (S6.5, CA4)."""
    from sqlalchemy import text
    from sqlalchemy.orm import Session

    from alembic import command
    from dossier.services.dossier_retention_worker import purge_expired_dossiers

    command.upgrade(alembic_cfg, "head")
    with pg_vacia.begin() as conn:
        org, user = _org_y_usuario_s65(conn, None)
        _, colega = _org_y_usuario_s65(conn, None)
        d = _dossier_s65(conn, org, user, horas=30)
        conn.execute(
            text("INSERT INTO dossier_alerts (dossier_id, level, message) VALUES (:d, 'warning', 'x')"),
            {"d": d},
        )
        conn.execute(
            text("INSERT INTO dossier_media_mentions (dossier_id, title, url) VALUES (:d, 't', 'https://n.test')"),
            {"d": d},
        )
        conn.execute(
            text(
                "INSERT INTO dossier_corporate_records (dossier_id, company_name, country) "
                "VALUES (:d, 'Acme Ltd', 'GB')"
            ),
            {"d": d},
        )
        conn.execute(
            text("INSERT INTO dossier_career_entries (dossier_id, company_name) VALUES (:d, 'Acme')"),
            {"d": d},
        )
        conn.execute(
            text("INSERT INTO dossier_ice_breakers (dossier_id, content) VALUES (:d, 'Hola')"),
            {"d": d},
        )
        conn.execute(
            text(
                "INSERT INTO dossier_shares (dossier_id, shared_with_user_id, shared_by_user_id) "
                "VALUES (:d, :c, :u)"
            ),
            {"d": d, "c": colega, "u": user},
        )

    with Session(pg_vacia) as db:
        resultado = purge_expired_dossiers(db)

    assert resultado.verificado is True
    with pg_vacia.connect() as conn:
        for tabla in _TABLAS_HIJAS:
            quedan = conn.execute(
                text(f"SELECT count(*) FROM {tabla} WHERE dossier_id = :d"), {"d": d}
            ).scalar_one()
            assert quedan == 0, f"quedaron filas huérfanas en {tabla}"
