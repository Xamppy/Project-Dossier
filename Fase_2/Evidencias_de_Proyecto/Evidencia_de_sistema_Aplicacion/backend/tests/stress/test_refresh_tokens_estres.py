"""S3.9 · Renovación bajo concurrencia y volumen (pruebas de estrés).

Requieren ``TEST_DATABASE_URL`` (fixture ``pg_vacia``).
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from alembic import command
from dossier.db.models import Organization, OrgMembership, RefreshToken, User
from dossier.security import refresh_tokens as rt


def _usuario(s: Session) -> tuple[User, Organization]:
    org = Organization(name="Acme", slug="acme", settings={"workspace_kind": "work"})
    user = User(email="ana@example.com")
    s.add_all([org, user])
    s.flush()
    s.add(OrgMembership(organization_id=org.id, user_id=user.id, role="admin", is_primary_org=True))
    s.commit()
    return user, org


def test_concurrencia_veinte_renovaciones_del_mismo_token_rotan_una_sola_vez(pg_vacia, alembic_cfg):
    """Sin bloqueo de fila, dos renovaciones simultáneas podrían emitir dos tokens válidos."""
    command.upgrade(alembic_cfg, "head")
    with Session(pg_vacia) as s:
        user, org = _usuario(s)
        crudo = rt.issue(s, user_id=user.id, organization_id=org.id, persistent=True)
        s.commit()

    def renovar(_: int) -> str:
        with Session(pg_vacia) as s:
            try:
                rt.rotate(s, crudo)
                return "ok"
            except rt.RefreshTokenError as e:
                return e.code

    with ThreadPoolExecutor(max_workers=20) as pool:
        resultados = list(pool.map(renovar, range(20)))

    assert resultados.count("ok") == 1
    assert set(resultados) <= {"ok", "refresh_rotated"}
    with Session(pg_vacia) as s:
        activos = s.scalar(select(func.count()).select_from(RefreshToken).where(RefreshToken.is_revoked.is_(False)))
    assert activos == 1


def test_volumen_revocar_quinientas_sesiones_es_rapido(pg_vacia, alembic_cfg):
    command.upgrade(alembic_cfg, "head")
    with Session(pg_vacia) as s:
        user, org = _usuario(s)
        for _ in range(500):
            rt.issue(s, user_id=user.id, organization_id=org.id, persistent=True)
        s.commit()

        inicio = time.perf_counter()
        revocadas = rt.revoke_all_for_user(s, user.id, now=datetime.now(UTC))
        s.commit()

        assert revocadas == 500
        assert time.perf_counter() - inicio < 2.0


def test_degradacion_token_desconocido_no_toca_la_base(pg_vacia, alembic_cfg):
    """Un token con formato inválido se rechaza sin consultar (no sirve para sondear la tabla)."""
    command.upgrade(alembic_cfg, "head")
    with Session(pg_vacia) as s:
        consultas: list[str] = []

        from sqlalchemy import event

        @event.listens_for(pg_vacia, "before_cursor_execute")
        def _contar(conn, cursor, statement, *args):
            consultas.append(statement)

        try:
            rt.rotate(s, "basura")
        except rt.RefreshTokenError as e:
            assert e.code == "refresh_invalid"
        finally:
            event.remove(pg_vacia, "before_cursor_execute", _contar)

    assert consultas == []
