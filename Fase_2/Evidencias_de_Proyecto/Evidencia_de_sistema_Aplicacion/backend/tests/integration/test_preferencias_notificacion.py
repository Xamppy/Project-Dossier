"""Informe beta · preferencias de notificación persistentes y respetadas (Postgres).

Defecto del informe del 2026-10-06: «el estado de cada tipo de notificación no se guarda de
forma persistente». Ahora ``notify_email`` y ``notify_browser`` viven en ``users``, se cambian con
``PATCH /auth/me/preferences`` y el correo automático respeta ``notify_email``. Requiere
``TEST_DATABASE_URL``.
"""
from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from alembic import command
from dossier.api.app import app
from dossier.api.auth_routes import get_db_if_configured
from dossier.db.models import User
from tests.integration.test_limite_dossiers_simultaneos import cliente, org, usuario

RUTA = "/auth/me/preferences"


@pytest.fixture
def base(pg_vacia, alembic_cfg) -> Iterator[SimpleNamespace]:
    command.upgrade(alembic_cfg, "head")
    m = SimpleNamespace(engine=pg_vacia)
    with pg_vacia.begin() as c:
        m.org = org(c, "Org", "pro")
        m.ana = usuario(c, "ana@org.com", m.org, "admin")
        m.beto = usuario(c, "beto@org.com", m.org, "user")

    def _db():
        with Session(pg_vacia) as s:
            yield s

    app.dependency_overrides[get_db_if_configured] = _db
    yield m
    app.dependency_overrides.clear()


def _prefs(m, uid) -> tuple[bool, bool]:
    with m.engine.connect() as c:
        return tuple(
            c.execute(text("SELECT notify_email, notify_browser FROM users WHERE id = :u"), {"u": uid}).one()
        )


def test_por_omision_estan_activadas_y_se_ven_en_auth_me(base):
    me = cliente(base.ana, base.org, "admin").get("/auth/me").json()
    assert me["notify_email"] is True
    assert me["notify_browser"] is True


def test_se_guardan_y_persisten(base):
    c = cliente(base.ana, base.org, "admin")
    resp = c.patch(RUTA, json={"notify_email": False})
    assert resp.status_code == 200
    assert resp.json()["notify_email"] is False
    assert resp.json()["notify_browser"] is True
    assert _prefs(base, base.ana) == (False, True)
    # Una recarga (nueva petición) trae lo guardado.
    assert c.get("/auth/me").json()["notify_email"] is False

    assert c.patch(RUTA, json={"notify_browser": False, "notify_email": True}).status_code == 200
    assert _prefs(base, base.ana) == (True, False)


def test_no_toca_las_demas_preferencias(base):
    c = cliente(base.ana, base.org, "admin")
    c.patch(RUTA, json={"locale": "en", "dossier_output_language": "fr"})
    c.patch(RUTA, json={"notify_email": False})
    me = c.get("/auth/me").json()
    assert (me["locale"], me["dossier_output_language"], me["notify_email"]) == ("en", "fr", False)


@pytest.mark.parametrize("valor", ["false", 0, 1, "si", None])
def test_solo_acepta_booleanos(base, valor):
    resp = cliente(base.ana, base.org, "admin").patch(RUTA, json={"notify_email": valor})
    if valor is None:
        assert resp.status_code == 400  # sin campos que actualizar
    else:
        assert resp.status_code == 422
    assert _prefs(base, base.ana) == (True, True)


def test_cada_usuario_cambia_solo_las_suyas(base):
    cliente(base.beto, base.org, "user").patch(RUTA, json={"notify_email": False, "notify_browser": False})
    assert _prefs(base, base.beto) == (False, False)
    assert _prefs(base, base.ana) == (True, True)


def test_sin_sesion_401(base):
    from fastapi.testclient import TestClient

    assert TestClient(app).patch(RUTA, json={"notify_email": False}).status_code == 401


# --- El correo automático respeta la preferencia ----------------------------------------------


@pytest.mark.parametrize(("activado", "envios"), [(True, 1), (False, 0)])
def test_correo_automatico_de_personas(base, monkeypatch, activado, envios):
    from dossier.services import dossier_generation_job_service as servicio

    enviados: list[str] = []
    monkeypatch.setattr(servicio, "email_delivery_available", lambda: True)
    monkeypatch.setattr(
        servicio, "deliver_dossier_after_generation", lambda db, *, dossier_id, recipient: enviados.append(recipient)
    )
    with Session(base.engine) as db:
        user = db.get(User, base.ana)
        user.notify_email = activado
        servicio.enviar_dossier_al_solicitante(
            db, result={"saved_dossier": {"id": "d1", "status": "complete"}}, user=user
        )
    assert len(enviados) == envios


@pytest.mark.parametrize(("activado", "envios"), [(True, 1), (False, 0)])
def test_correo_de_la_automatizacion_del_calendario(base, monkeypatch, activado, envios):
    from dossier.services import calendar_automation as auto

    enviados: list[str] = []
    monkeypatch.setattr(auto, "email_delivery_available", lambda: True)
    monkeypatch.setattr(auto, "saved_dossier_ids", lambda guardados: ["d1"])
    monkeypatch.setattr(auto, "deliver_meeting_dossiers", lambda db, **kw: enviados.append(kw["recipient"]))
    with Session(base.engine) as db:
        user = db.get(User, base.ana)
        user.notify_email = activado
        auto._enviar_dossiers_de_la_reunion(
            db,
            integration=SimpleNamespace(auto_send_email=True),
            user=user,
            event=SimpleNamespace(title="Reunión", id="e1"),
            guardados={},
            idioma="es",
        )
    assert len(enviados) == envios


def test_la_migracion_agrega_y_quita_las_columnas(base, alembic_cfg):
    def columnas() -> set[str]:
        with base.engine.connect() as c:
            return set(
                c.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'users' AND column_name LIKE 'notify_%'"
                    )
                ).scalars()
            )

    assert columnas() == {"notify_email", "notify_browser"}
    command.downgrade(alembic_cfg, "e1b5c9d3a7f2")
    assert columnas() == set()
    command.upgrade(alembic_cfg, "head")
    assert columnas() == {"notify_email", "notify_browser"}
