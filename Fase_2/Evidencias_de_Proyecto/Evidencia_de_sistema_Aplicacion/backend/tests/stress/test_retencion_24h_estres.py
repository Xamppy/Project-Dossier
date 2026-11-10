"""S6.5, estrés: volumen alto, workers simultáneos y Redis caído.

Especificación: ``specs/proposals/S6.5-retencion-24h.md``. Requiere ``TEST_DATABASE_URL``.
"""
from __future__ import annotations

import threading
import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from alembic import command
from dossier.cache import corporate_dossier_redis as cache
from dossier.db.models import DossierGenerationJob
from dossier.services.dossier_retention_worker import purge_expired_dossiers

VENCIDOS = 300


@pytest.fixture
def base(pg_vacia, alembic_cfg, monkeypatch):
    command.upgrade(alembic_cfg, "head")
    DossierGenerationJob.__table__.create(bind=pg_vacia, checkfirst=True)
    monkeypatch.delenv("DOSSIER_RETENTION_HOURS", raising=False)
    return pg_vacia


def _sembrar_vencidos(engine, cantidad: int) -> None:
    """``cantidad`` dossiers de 30 h, cada uno con una alerta y una mención de prensa."""
    sufijo = uuid.uuid4().hex[:8]
    with engine.begin() as conn:
        org = conn.execute(
            text("INSERT INTO organizations (name, slug) VALUES (:n, :s) RETURNING id"),
            {"n": f"Org {sufijo}", "s": f"org-{sufijo}"},
        ).scalar_one()
        user = conn.execute(
            text("INSERT INTO users (email) VALUES (:e) RETURNING id"),
            {"e": f"estres-{sufijo}@example.test"},
        ).scalar_one()
        creado = datetime.now(UTC) - timedelta(hours=30)
        ids = conn.execute(
            text(
                "INSERT INTO dossiers (organization_id, requested_by_user_id, dossier_data, created_at) "
                "SELECT :o, :u, CAST('{\"billing\": \"none\"}' AS JSONB), :c "
                "FROM generate_series(1, :n) RETURNING id"
            ),
            {"o": org, "u": user, "c": creado, "n": cantidad},
        ).scalars().all()
        conn.execute(
            text(
                "INSERT INTO dossier_alerts (dossier_id, level, message) "
                "SELECT id, 'warning', 'x' FROM dossiers WHERE id = ANY(:ids)"
            ),
            {"ids": ids},
        )
        conn.execute(
            text(
                "INSERT INTO dossier_media_mentions (dossier_id, title, url) "
                "SELECT id, 't', 'https://n.test' FROM dossiers WHERE id = ANY(:ids)"
            ),
            {"ids": ids},
        )


def _contar(engine, tabla: str) -> int:
    with engine.connect() as conn:
        return int(conn.execute(text(f"SELECT count(*) FROM {tabla}")).scalar_one())


def test_volumen_alto_se_borra_completo_y_verificado(base):
    _sembrar_vencidos(base, VENCIDOS)

    inicio = time.perf_counter()
    with Session(base) as db:
        resultado = purge_expired_dossiers(db)
    duracion = time.perf_counter() - inicio

    assert resultado.dossiers_borrados == VENCIDOS
    assert resultado.verificado is True
    assert _contar(base, "dossiers") == 0
    assert _contar(base, "dossier_alerts") == 0
    assert _contar(base, "dossier_media_mentions") == 0
    assert duracion < 30, f"borrar {VENCIDOS} dossiers tardó {duracion:.1f} s"


def test_volumen_alto_deja_un_registro_de_auditoria_por_dossier(base):
    """S6.6: cada borrado queda en ``audit_logs``, más una fila de verificación por vuelta."""
    _sembrar_vencidos(base, VENCIDOS)

    with Session(base) as db:
        purge_expired_dossiers(db)

    with base.connect() as conn:
        por_accion = dict(
            conn.execute(
                text("SELECT action, count(*) FROM audit_logs WHERE action LIKE 'RETENTION%' GROUP BY action")
            ).all()
        )
    assert por_accion == {"RETENTION dossier_deleted": VENCIDOS, "RETENTION verification": 1}


def test_dos_workers_a_la_vez_no_fallan_ni_dejan_restos(base):
    """Con varios procesos, cada uno corre su worker: no deben pisarse."""
    _sembrar_vencidos(base, VENCIDOS)
    resultados = []
    errores: list[BaseException] = []
    barrera = threading.Barrier(2)

    def correr():
        try:
            with Session(base) as db:
                barrera.wait(timeout=10)
                resultados.append(purge_expired_dossiers(db))
        except BaseException as e:  # la prueba reporta cualquier falla del hilo
            errores.append(e)

    hilos = [threading.Thread(target=correr) for _ in range(2)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=60)

    assert errores == []
    assert sum(r.dossiers_borrados for r in resultados) == VENCIDOS
    assert all(r.verificado for r in resultados)
    assert _contar(base, "dossiers") == 0


def test_redis_caido_no_rompe_la_verificacion(monkeypatch):
    """Si Redis falla al consultar, la verificación no se cae: registra y sigue."""

    class _RedisRoto:
        def exists(self, *_):
            raise ConnectionError("Redis no responde")

    monkeypatch.setattr(cache, "_client", lambda: _RedisRoto())
    assert cache.dossier_redis_key_exists("dossier:corp:abc") is False
