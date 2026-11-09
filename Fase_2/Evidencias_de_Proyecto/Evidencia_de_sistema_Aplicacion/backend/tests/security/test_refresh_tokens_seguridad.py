"""S3.9 · Lo que la sesión NO debe permitir (pruebas de seguridad).

Hallazgo de origen: docs/security/README.md, "Token de acceso de 7 días en localStorage".
Las pruebas marcadas con ``pg_vacia`` requieren ``TEST_DATABASE_URL``.
"""
from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from alembic import command
from dossier.api.app import app
from dossier.api.auth_routes import get_db_if_configured
from dossier.db.models import Organization, OrgMembership, RefreshToken, User
from dossier.security import hash_password
from dossier.security.jwt_tokens import create_access_token
from dossier.security.refresh_tokens import REFRESH_COOKIE_NAME, hash_refresh_token

CLAVE = "secreta-123"


# --------------------------------------------------------------------------
# Token de acceso
# --------------------------------------------------------------------------


def _sin_db():
    yield None


def test_token_de_acceso_vencido_es_rechazado(monkeypatch):
    monkeypatch.setenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "-1")
    vencido = create_access_token(user_id="u-1", email="a@b.cl")
    app.dependency_overrides[get_db_if_configured] = _sin_db
    try:
        r = TestClient(app).get("/auth/me", headers={"Authorization": f"Bearer {vencido}"})
    finally:
        app.dependency_overrides.pop(get_db_if_configured, None)

    assert r.status_code == 401


def test_renovar_no_acepta_el_token_de_acceso_como_credencial(monkeypatch):
    """La renovación solo se obtiene con la cookie, no con un Bearer (que podría estar robado)."""
    acceso = create_access_token(user_id="u-1", email="a@b.cl")
    app.dependency_overrides[get_db_if_configured] = _sin_db
    try:
        r = TestClient(app).post("/auth/refresh", headers={"Authorization": f"Bearer {acceso}"})
    finally:
        app.dependency_overrides.pop(get_db_if_configured, None)

    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "refresh_missing"


# --------------------------------------------------------------------------
# Token de renovación contra Postgres
# --------------------------------------------------------------------------


@pytest.fixture
def cliente(pg_vacia, alembic_cfg) -> Iterator[tuple[TestClient, Session]]:
    command.upgrade(alembic_cfg, "head")

    def _db():
        with Session(pg_vacia) as s:
            yield s

    app.dependency_overrides[get_db_if_configured] = _db
    with Session(pg_vacia) as s:
        org = Organization(name="Acme", slug="acme", settings={"workspace_kind": "work"})
        user = User(email="ana@example.com", password_hash=hash_password(CLAVE), email_verified=True)
        s.add_all([org, user])
        s.flush()
        s.add(OrgMembership(organization_id=org.id, user_id=user.id, role="admin", is_primary_org=True))
        s.commit()
        try:
            yield TestClient(app, base_url="https://testserver"), s
        finally:
            app.dependency_overrides.pop(get_db_if_configured, None)


def _login(c: TestClient):
    return c.post("/auth/login", json={"email": "ana@example.com", "password": CLAVE})


def test_la_base_guarda_solo_el_hash(cliente):
    c, s = cliente
    _login(c)
    crudo = c.cookies.get(REFRESH_COOKIE_NAME)

    guardado = s.scalar(select(RefreshToken.token_hash))
    volcado = " ".join(str(v) for v in s.execute(text("SELECT * FROM refresh_tokens")).one())

    assert guardado == hash_refresh_token(crudo)
    assert crudo not in volcado


def test_la_cookie_no_es_legible_por_javascript(cliente):
    c, _ = cliente
    r = _login(c)

    cabecera = next(v for k, v in r.headers.multi_items() if k.lower() == "set-cookie" and REFRESH_COOKIE_NAME in v)
    assert "httponly" in cabecera.lower()


def test_un_token_revocado_por_logout_no_resucita(cliente):
    c, _ = cliente
    _login(c)
    crudo = c.cookies.get(REFRESH_COOKIE_NAME)
    c.post("/auth/logout")

    otro = TestClient(app, base_url="https://testserver")
    otro.cookies.set(REFRESH_COOKIE_NAME, crudo, domain="testserver.local", path="/auth")

    assert otro.post("/auth/refresh").status_code == 401


def test_quitar_la_membresia_impide_renovar_en_esa_organizacion(cliente):
    c, s = cliente
    _login(c)
    s.execute(text("DELETE FROM org_memberships"))
    s.commit()

    r = c.post("/auth/refresh")

    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "refresh_inactive"


def test_cookie_de_otra_ruta_no_se_envia_al_resto_de_la_api(cliente):
    """La cookie tiene Path=/auth: no viaja a /dossiers ni a otras rutas."""
    c, _ = cliente
    _login(c)

    galleta = next(ck for ck in c.cookies.jar if ck.name == REFRESH_COOKIE_NAME)

    assert galleta.path == "/auth"
    assert galleta.secure is True
