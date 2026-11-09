"""Cambiar de organización no debe romper la regla de una sola organización principal.

Defecto encontrado el 2026-11-02 al probar S3.9: ``_clear_and_set_primary_org`` marcaba la
nueva principal y desmarcaba la anterior en el mismo flush. SQLAlchemy ordena esos UPDATE
por id (UUID aleatorio): si la nueva iba primero, el índice único parcial
``idx_memberships_primary_org`` lo rechazaba y ``POST /auth/session/switch`` respondía 500
de forma intermitente.

Requiere ``TEST_DATABASE_URL`` (fixture ``pg_vacia``).
"""
from __future__ import annotations

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from alembic import command
from dossier.api.auth_routes import _clear_and_set_primary_org
from dossier.db.models import OrgMembership


def test_cambiar_la_principal_nunca_viola_el_indice_unico(pg_vacia, alembic_cfg):
    """Con 12 usuarios, el orden de los UPDATE cae al menos una vez en el caso malo
    (probabilidad de no verlo con el defecto: 1/4096)."""
    command.upgrade(alembic_cfg, "head")
    cambios: list[tuple] = []
    with pg_vacia.begin() as c:
        for i in range(12):
            a = c.execute(text("INSERT INTO organizations (name, slug) VALUES ('A', :s) RETURNING id"), {"s": f"a{i}"}).scalar_one()
            b = c.execute(text("INSERT INTO organizations (name, slug) VALUES ('B', :s) RETURNING id"), {"s": f"b{i}"}).scalar_one()
            u = c.execute(text("INSERT INTO users (email) VALUES (:e) RETURNING id"), {"e": f"u{i}@example.com"}).scalar_one()
            c.execute(
                text(
                    "INSERT INTO org_memberships (organization_id, user_id, role, is_primary_org) "
                    "VALUES (:a, :u, 'admin', TRUE), (:b, :u, 'user', FALSE)"
                ),
                {"a": a, "b": b, "u": u},
            )
            cambios.append((u, b))

    with Session(pg_vacia) as s:
        for usuario, nueva in cambios:
            _clear_and_set_primary_org(s, usuario, nueva)
            s.commit()

        for usuario, nueva in cambios:
            principales = s.scalars(
                select(OrgMembership.organization_id).where(
                    OrgMembership.user_id == usuario, OrgMembership.is_primary_org.is_(True)
                )
            ).all()
            assert principales == [nueva]


def test_volver_a_la_misma_principal_no_cambia_nada(pg_vacia, alembic_cfg):
    command.upgrade(alembic_cfg, "head")
    with pg_vacia.begin() as c:
        a = c.execute(text("INSERT INTO organizations (name, slug) VALUES ('A', 'a') RETURNING id")).scalar_one()
        u = c.execute(text("INSERT INTO users (email) VALUES ('u@example.com') RETURNING id")).scalar_one()
        c.execute(
            text("INSERT INTO org_memberships (organization_id, user_id, role, is_primary_org) VALUES (:a, :u, 'admin', TRUE)"),
            {"a": a, "u": u},
        )

    with Session(pg_vacia) as s:
        _clear_and_set_primary_org(s, u, a)
        s.commit()
        assert s.scalars(select(OrgMembership.is_primary_org)).all() == [True]
