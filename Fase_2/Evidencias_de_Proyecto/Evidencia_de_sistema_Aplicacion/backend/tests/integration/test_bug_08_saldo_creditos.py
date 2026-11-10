"""BUG-2026-10-19-08: `credit_ledger.balance_after` repetía el saldo con dos dossiers en una
misma sentencia.

Causa: el descuento iba en un trigger BEFORE y la anotación en uno AFTER. Postgres corre los
AFTER al final de la sentencia, así que todas las filas leían el saldo final. Requiere
``TEST_DATABASE_URL``.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from alembic import command

REVISION_ANTERIOR = "f3a7c1e9b5d2"


def _org_usuario(conn, saldo: int):
    sufijo = uuid.uuid4().hex[:8]
    org = conn.execute(
        text("INSERT INTO organizations (name, slug, credits_balance) VALUES (:n, :s, :c) RETURNING id"),
        {"n": f"Org {sufijo}", "s": f"org-{sufijo}", "c": saldo},
    ).scalar_one()
    user = conn.execute(
        text("INSERT INTO users (email) VALUES (:e) RETURNING id"), {"e": f"u-{sufijo}@example.test"}
    ).scalar_one()
    return org, user


def _insertar(conn, org, user, cantidad: int, billing: str | None = None) -> None:
    datos = '{"billing": "none"}' if billing == "none" else "{}"
    conn.execute(
        text(
            "INSERT INTO dossiers (organization_id, requested_by_user_id, depth_level, dossier_data) "
            "SELECT :o, :u, 'standard', CAST(:d AS JSONB) FROM generate_series(1, :n)"
        ),
        {"o": org, "u": user, "d": datos, "n": cantidad},
    )


def _saldos(conn, org) -> list[int]:
    return list(
        conn.execute(
            text("SELECT balance_after FROM credit_ledger WHERE organization_id = :o ORDER BY balance_after DESC"),
            {"o": org},
        ).scalars()
    )


def _saldo_org(conn, org) -> int:
    return conn.execute(text("SELECT credits_balance FROM organizations WHERE id = :o"), {"o": org}).scalar_one()


@pytest.fixture
def base(pg_vacia, alembic_cfg):
    command.upgrade(alembic_cfg, "head")
    return pg_vacia


def test_dos_dossiers_en_una_sentencia_anotan_cada_uno_su_saldo(base):
    with base.begin() as conn:
        org, user = _org_usuario(conn, 10)
        _insertar(conn, org, user, 2)

    with base.connect() as conn:
        assert _saldos(conn, org) == [7, 4]
        assert _saldo_org(conn, org) == 4


def test_tres_dossiers_en_una_sentencia(base):
    with base.begin() as conn:
        org, user = _org_usuario(conn, 20)
        _insertar(conn, org, user, 3)

    with base.connect() as conn:
        assert _saldos(conn, org) == [17, 14, 11]
        assert _saldo_org(conn, org) == 11


def test_un_dossier_solo_sigue_igual(base):
    with base.begin() as conn:
        org, user = _org_usuario(conn, 10)
        _insertar(conn, org, user, 1)

    with base.connect() as conn:
        assert _saldos(conn, org) == [7]
        assert _saldo_org(conn, org) == 7


def test_sin_saldo_para_todos_no_se_cobra_nada(base):
    with base.begin() as conn:
        org, user = _org_usuario(conn, 5)

    with pytest.raises(DBAPIError, match="Insufficient credits"), base.begin() as conn:
        _insertar(conn, org, user, 2)  # 3 + 3 > 5

    with base.connect() as conn:
        assert _saldo_org(conn, org) == 5
        assert _saldos(conn, org) == []
        assert conn.execute(text("SELECT count(*) FROM dossiers WHERE organization_id = :o"), {"o": org}).scalar_one() == 0


def test_sin_cobro_no_descuenta_ni_anota(base):
    with base.begin() as conn:
        org, user = _org_usuario(conn, 10)
        _insertar(conn, org, user, 2, billing="none")

    with base.connect() as conn:
        assert _saldos(conn, org) == []
        assert _saldo_org(conn, org) == 10


def test_el_downgrade_deja_los_triggers_como_estaban(base, alembic_cfg):
    command.downgrade(alembic_cfg, REVISION_ANTERIOR)
    with base.begin() as conn:
        org, user = _org_usuario(conn, 10)
        _insertar(conn, org, user, 1)
    with base.connect() as conn:
        assert _saldos(conn, org) == [7]
