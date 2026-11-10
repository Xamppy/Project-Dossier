"""S6.5, integración: retención de 24 h contra Postgres real.

Especificación: ``specs/proposals/S6.5-retencion-24h.md`` (CA3, CA5, CA6, CA7, CA11).
Requiere ``TEST_DATABASE_URL`` (fixture ``pg_vacia``). Los casos CA2 y CA4 están en
``tests/security/test_ejemplo_seguridad.py``.
"""
from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from alembic import command
from dossier.api.app import app
from dossier.api.auth_routes import get_db_if_configured
from dossier.db.models import DossierGenerationJob
from dossier.security.jwt_tokens import create_access_token
from dossier.services.dossier_retention_worker import purge_expired_dossiers, verificar_borrado

AHORA = datetime.now(UTC)


@pytest.fixture
def base(pg_vacia, alembic_cfg, monkeypatch):
    command.upgrade(alembic_cfg, "head")
    DossierGenerationJob.__table__.create(bind=pg_vacia, checkfirst=True)
    monkeypatch.delenv("DOSSIER_RETENTION_HOURS", raising=False)
    return pg_vacia


def _org_y_usuario(conn, retencion=None) -> tuple[uuid.UUID, uuid.UUID]:
    sufijo = uuid.uuid4().hex[:8]
    org = conn.execute(
        text("INSERT INTO organizations (name, slug) VALUES (:n, :s) RETURNING id"),
        {"n": f"Org {sufijo}", "s": f"org-{sufijo}"},
    ).scalar_one()
    user = conn.execute(
        text("INSERT INTO users (email, dossier_retention_days) VALUES (:e, :r) RETURNING id"),
        {"e": f"retencion-{sufijo}@example.test", "r": retencion},
    ).scalar_one()
    return org, user


def _dossier(conn, org, user, *, horas: float) -> uuid.UUID:
    return conn.execute(
        text(
            "INSERT INTO dossiers (organization_id, requested_by_user_id, dossier_data, created_at) "
            "VALUES (:o, :u, CAST('{}' AS JSONB), :c) RETURNING id"
        ),
        {"o": org, "u": user, "c": AHORA - timedelta(hours=horas)},
    ).scalar_one()


def _job(conn, org, user, *, estado: str, horas: float, terminado: bool = True) -> uuid.UUID:
    job_id = uuid.uuid4()
    momento = AHORA - timedelta(hours=horas)
    conn.execute(
        text(
            "INSERT INTO dossier_generation_jobs (id, organization_id, requested_by_user_id, status, "
            "job_type, depth_level, credits_estimated, credits_consumed, meeting_label, created_at, "
            "completed_at) VALUES (:i, :o, :u, :s, 'person', 'standard', 1, 1, 'Reunión con Ana', "
            ":c, :t)"
        ),
        {"i": job_id, "o": org, "u": user, "s": estado, "c": momento, "t": momento if terminado else None},
    )
    return job_id


def _existe(conn, tabla: str, id_) -> bool:
    return conn.execute(text(f"SELECT count(*) FROM {tabla} WHERE id = :i"), {"i": id_}).scalar_one() > 0


# --------------------------------------------------------------------------
# CA3 · lo reciente no se toca
# --------------------------------------------------------------------------


def test_un_dossier_de_menos_de_24_horas_no_se_borra(base):
    with base.begin() as conn:
        org, user = _org_y_usuario(conn)
        reciente = _dossier(conn, org, user, horas=23)

    with Session(base) as db:
        resultado = purge_expired_dossiers(db)

    assert resultado.dossiers_borrados == 0
    with base.connect() as conn:
        assert _existe(conn, "dossiers", reciente)


# --------------------------------------------------------------------------
# CA5 · el movimiento de créditos se conserva sin el dossier
# --------------------------------------------------------------------------


def test_el_movimiento_de_creditos_queda_sin_dossier(base):
    with base.begin() as conn:
        org, user = _org_y_usuario(conn)
        viejo = _dossier(conn, org, user, horas=30)
        movimiento = conn.execute(
            text(
                "INSERT INTO credit_ledger (organization_id, user_id, dossier_id, change_amount, "
                "balance_after, reason) VALUES (:o, :u, :d, -1, 9, 'dossier_generation') RETURNING id"
            ),
            {"o": org, "u": user, "d": viejo},
        ).scalar_one()

    with Session(base) as db:
        purge_expired_dossiers(db)

    with base.connect() as conn:
        fila = conn.execute(
            text("SELECT dossier_id, change_amount FROM credit_ledger WHERE id = :i"), {"i": movimiento}
        ).one()
    assert fila.dossier_id is None
    assert fila.change_amount == -1


# --------------------------------------------------------------------------
# CA6 · los jobs terminados y vencidos se borran; los activos o recientes, no
# --------------------------------------------------------------------------


def test_los_jobs_terminados_y_vencidos_se_borran(base):
    with base.begin() as conn:
        org, user = _org_y_usuario(conn)
        viejo_ok = _job(conn, org, user, estado="completed", horas=30)
        viejo_fallido = _job(conn, org, user, estado="failed", horas=26)
        reciente = _job(conn, org, user, estado="completed", horas=2)
        activo_viejo = _job(conn, org, user, estado="running", horas=30, terminado=False)

    with Session(base) as db:
        resultado = purge_expired_dossiers(db)

    assert resultado.jobs_borrados == 2
    with base.connect() as conn:
        assert not _existe(conn, "dossier_generation_jobs", viejo_ok)
        assert not _existe(conn, "dossier_generation_jobs", viejo_fallido)
        assert _existe(conn, "dossier_generation_jobs", reciente)
        assert _existe(conn, "dossier_generation_jobs", activo_viejo)


# --------------------------------------------------------------------------
# CA7 · el borrado se verifica y el resultado lo informa
# --------------------------------------------------------------------------


def test_el_resultado_informa_borrado_verificado(base, caplog):
    with base.begin() as conn:
        org, user = _org_y_usuario(conn)
        for horas in (25, 40, 72):
            _dossier(conn, org, user, horas=horas)
        _job(conn, org, user, estado="completed", horas=30)

    with (
        caplog.at_level(logging.INFO, logger="dossier.services.dossier_retention_worker"),
        Session(base) as db,
    ):
        resultado = purge_expired_dossiers(db)

    assert resultado.dossiers_borrados == 3
    assert resultado.jobs_borrados == 1
    assert resultado.verificado is True
    assert resultado.restos == {}
    assert any("verificado" in r.getMessage() for r in caplog.records if r.levelno == logging.INFO)


def test_la_verificacion_detecta_un_resto(base, caplog):
    with base.begin() as conn:
        org, user = _org_y_usuario(conn)
        sigue_ahi = _dossier(conn, org, user, horas=30)
        conn.execute(
            text("INSERT INTO dossier_alerts (dossier_id, level, message) VALUES (:d, 'warning', 'x')"),
            {"d": sigue_ahi},
        )

    with (
        caplog.at_level(logging.ERROR, logger="dossier.services.dossier_retention_worker"),
        Session(base) as db,
    ):
        restos = verificar_borrado(
            db, dossier_ids=[sigue_ahi], cache_keys=[], corte=AHORA - timedelta(hours=24)
        )

    assert restos == {"dossiers": 1, "dossier_alerts": 1}
    assert any(r.levelno == logging.ERROR for r in caplog.records)


def test_la_verificacion_detecta_un_job_vencido(base):
    with base.begin() as conn:
        org, user = _org_y_usuario(conn)
        _job(conn, org, user, estado="completed", horas=30)

    with Session(base) as db:
        restos = verificar_borrado(db, dossier_ids=[], cache_keys=[], corte=AHORA - timedelta(hours=24))

    assert restos == {"dossier_generation_jobs": 1}


# --------------------------------------------------------------------------
# CA11 · la API informa el plazo y ya no deja elegirlo
# --------------------------------------------------------------------------


@pytest.fixture
def api(base):
    with base.begin() as conn:
        org, user = _org_y_usuario(conn, retencion=90)
        conn.execute(
            text(
                "INSERT INTO org_memberships (organization_id, user_id, role, is_primary_org) "
                "VALUES (:o, :u, 'user', true)"
            ),
            {"o": org, "u": user},
        )
        email = conn.execute(text("SELECT email FROM users WHERE id = :u"), {"u": user}).scalar_one()

    def _db():
        s = Session(base)
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db_if_configured] = _db
    token = create_access_token(user_id=str(user), email=email, organization_id=str(org), role="user")
    yield TestClient(app), {"Authorization": f"Bearer {token}"}, user
    app.dependency_overrides.pop(get_db_if_configured, None)


def test_auth_me_informa_el_plazo_en_horas(api):
    client, headers, _ = api
    r = client.get("/auth/me", headers=headers)
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["dossier_retention_hours"] == 24
    assert "dossier_retention_days" not in cuerpo


def test_las_preferencias_ignoran_dossier_retention_days(api, base):
    client, headers, user = api
    r = client.patch(
        "/auth/me/preferences", headers=headers, json={"locale": "es", "dossier_retention_days": 7}
    )
    assert r.status_code == 200, r.text
    assert "dossier_retention_days" not in r.json()
    with base.connect() as conn:
        dias = conn.execute(
            text("SELECT dossier_retention_days FROM users WHERE id = :u"), {"u": user}
        ).scalar_one()
    assert dias == 90  # el valor antiguo no cambia: el campo ya no se usa
