"""S5.2 · Seguridad de ``GET /dossier-notifications/stream`` (contra Postgres).

- Sin token o con un token inválido: 401.
- Nada de otra organización aparece en el canal, ni para su admin.
- Un viewer solo ve lo compartido con él; un user, lo propio y lo compartido.
- Si el usuario deja de ser miembro o se desactiva, el stream abierto termina.

Requiere ``TEST_DATABASE_URL`` (fixture ``pg_vacia``).
"""
from __future__ import annotations

import time
from collections.abc import Iterator
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from alembic import command
from dossier.api.app import app
from dossier.api.auth_routes import get_db_if_configured
from tests.integration.test_dossier_notifications_route import (
    RUTA,
    _miembro,
    _org,
    _usuario,
    cliente,
    despues,
    eventos,
    insertar_dossier,
    token,
)

SECRETO_B = "Sujeto-Secreto-B"


def _sujetos(datos: dict) -> set[str]:
    return {i.get("subject_name") or "" for i in datos["items"]}


@pytest.fixture
def mundo(pg_vacia, alembic_cfg, monkeypatch) -> Iterator[SimpleNamespace]:
    monkeypatch.setenv("DOSSIER_NOTIFICATIONS_MAX_SECONDS", "0")
    command.upgrade(alembic_cfg, "head")
    m = SimpleNamespace(engine=pg_vacia)
    with pg_vacia.begin() as c:
        m.org_a, m.org_b = _org(c, "A"), _org(c, "B")
        m.a_admin = _usuario(c, "admin@a.com")
        m.a_user = _usuario(c, "user@a.com")
        m.a_viewer = _usuario(c, "viewer@a.com")
        m.b_admin = _usuario(c, "admin@b.com")
        _miembro(c, m.org_a, m.a_admin, "admin")
        _miembro(c, m.org_a, m.a_user, "user")
        _miembro(c, m.org_a, m.a_viewer, "viewer")
        _miembro(c, m.org_b, m.b_admin, "admin")
    m.del_admin = insertar_dossier(pg_vacia, m.org_a, m.a_admin, "Del admin")
    m.del_user = insertar_dossier(pg_vacia, m.org_a, m.a_user, "Del user")
    m.compartido = insertar_dossier(pg_vacia, m.org_a, m.a_admin, "Compartido")
    insertar_dossier(pg_vacia, m.org_b, m.b_admin, SECRETO_B)
    with pg_vacia.begin() as c:
        for destino in (m.a_user, m.a_viewer):
            c.execute(
                text(
                    "INSERT INTO dossier_shares (dossier_id, shared_with_user_id, shared_by_user_id) "
                    "VALUES (:d, :u, :p)"
                ),
                {"d": m.compartido, "u": destino, "p": m.a_admin},
            )

    def _db():
        with Session(pg_vacia) as s:
            yield s

    app.dependency_overrides[get_db_if_configured] = _db
    yield m
    app.dependency_overrides.clear()


def _primer_evento(tok: str) -> dict:
    with cliente(tok).stream("GET", RUTA) as resp:
        assert resp.status_code == 200
        return next(eventos(resp))


def test_sin_token_401(mundo):
    resp = cliente().get(RUTA)
    assert resp.status_code == 401
    assert "text/event-stream" not in resp.headers.get("content-type", "")


def test_token_invalido_401(mundo):
    assert cliente("no-es-un-jwt").get(RUTA).status_code == 401


def test_token_de_org_ajena_sin_membresia_403(mundo):
    assert cliente(token(mundo.a_admin, mundo.org_b, "admin")).get(RUTA).status_code == 403


def test_admin_de_a_no_ve_nada_de_b(mundo):
    datos = _primer_evento(token(mundo.a_admin, mundo.org_a, "admin"))
    assert _sujetos(datos) == {"Del admin", "Del user", "Compartido"}
    assert datos["organization_id"] == str(mundo.org_a)


def test_user_ve_lo_propio_y_lo_compartido(mundo):
    datos = _primer_evento(token(mundo.a_user, mundo.org_a, "user"))
    assert _sujetos(datos) == {"Del user", "Compartido"}


def test_viewer_solo_ve_lo_compartido(mundo):
    datos = _primer_evento(token(mundo.a_viewer, mundo.org_a, "viewer"))
    assert _sujetos(datos) == {"Compartido"}


def test_un_dossier_nuevo_de_b_no_llega_al_stream_de_a(mundo, monkeypatch):
    monkeypatch.setenv("DOSSIER_NOTIFICATIONS_CHECK_SECONDS", "1")
    monkeypatch.setenv("DOSSIER_NOTIFICATIONS_MAX_SECONDS", "3")
    hilo = despues(1.5, lambda: insertar_dossier(mundo.engine, mundo.org_b, mundo.b_admin, SECRETO_B + "-2"))
    with cliente(token(mundo.a_admin, mundo.org_a, "admin")).stream("GET", RUTA) as resp:
        recibidos = list(eventos(resp))
    hilo.join()
    assert len(recibidos) == 1


@pytest.mark.parametrize(
    "retirar",
    [
        "DELETE FROM org_memberships WHERE user_id = :u",
        "UPDATE users SET is_active = false WHERE id = :u",
    ],
    ids=["miembro-retirado", "usuario-desactivado"],
)
def test_el_stream_termina_si_pierde_el_acceso(mundo, monkeypatch, retirar):
    monkeypatch.setenv("DOSSIER_NOTIFICATIONS_CHECK_SECONDS", "1")
    monkeypatch.setenv("DOSSIER_NOTIFICATIONS_MAX_SECONDS", "60")
    def quitar_acceso() -> None:
        with mundo.engine.begin() as c:
            c.execute(text(retirar), {"u": mundo.a_user})

    inicio = time.monotonic()
    hilo = despues(1.5, quitar_acceso)
    with cliente(token(mundo.a_user, mundo.org_a, "user")).stream("GET", RUTA) as resp:
        recibidos = list(eventos(resp))
    hilo.join()
    assert len(recibidos) == 1
    # Terminó en la siguiente comprobación, no a los 60 s.
    assert time.monotonic() - inicio < 10
