"""S3.9 · Flujo de sesión contra Postgres: inicio, renovación, rotación y cierre.

Requiere ``TEST_DATABASE_URL`` (fixture ``pg_vacia``). El cliente usa HTTPS porque la
cookie de renovación es ``Secure``: por HTTP el cliente no la devolvería.
"""
from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from alembic import command
from dossier.api.app import app
from dossier.api.auth_routes import get_db_if_configured
from dossier.db.models import Organization, OrgMembership, RefreshToken, User
from dossier.security import hash_password
from dossier.security.jwt_tokens import decode_access_token
from dossier.security.refresh_tokens import REFRESH_COOKIE_NAME

CLAVE = "secreta-123"


@pytest.fixture
def sesion(pg_vacia, alembic_cfg) -> Iterator[Session]:
    command.upgrade(alembic_cfg, "head")
    with Session(pg_vacia) as s:
        yield s


@pytest.fixture
def cliente(pg_vacia, sesion) -> Iterator[TestClient]:
    def _db():
        with Session(pg_vacia) as s:
            yield s

    app.dependency_overrides[get_db_if_configured] = _db
    try:
        yield TestClient(app, base_url="https://testserver")
    finally:
        app.dependency_overrides.pop(get_db_if_configured, None)


def _usuario(sesion: Session, correo: str = "ana@example.com", slug: str = "acme") -> tuple[User, Organization]:
    org = Organization(name="Acme", slug=slug, settings={"workspace_kind": "work"})
    user = User(email=correo, password_hash=hash_password(CLAVE), email_verified=True)
    sesion.add_all([org, user])
    sesion.flush()
    sesion.add(OrgMembership(organization_id=org.id, user_id=user.id, role="admin", is_primary_org=True))
    sesion.commit()
    return user, org


def _login(cliente: TestClient, correo: str = "ana@example.com", **extra):
    return cliente.post("/auth/login", json={"email": correo, "password": CLAVE, **extra})


def _set_cookie(resp) -> str:
    return "; ".join(v for k, v in resp.headers.multi_items() if k.lower() == "set-cookie")


def _tokens_activos(sesion: Session) -> int:
    sesion.expire_all()
    return sesion.scalar(select(func.count()).select_from(RefreshToken).where(RefreshToken.is_revoked.is_(False)))


# --------------------------------------------------------------------------
# Inicio de sesión
# --------------------------------------------------------------------------


def test_login_entrega_token_de_acceso_y_cookie_de_renovacion(sesion, cliente):
    _usuario(sesion)

    r = _login(cliente)

    assert r.status_code == 200
    assert decode_access_token(r.json()["access_token"])["email"] == "ana@example.com"
    cabecera = _set_cookie(r).lower()
    assert f"{REFRESH_COOKIE_NAME}=" in cabecera
    assert "httponly" in cabecera and "secure" in cabecera and "samesite=strict" in cabecera
    assert "path=/auth" in cabecera
    assert "max-age=" in cabecera  # recordada por omisión
    assert _tokens_activos(sesion) == 1


def test_login_sin_recordar_deja_cookie_de_sesion(sesion, cliente):
    _usuario(sesion)

    r = _login(cliente, remember=False)

    assert r.status_code == 200
    cabecera = _set_cookie(r).lower()
    assert f"{REFRESH_COOKIE_NAME}=" in cabecera
    assert "max-age=" not in cabecera and "expires=" not in cabecera


def test_login_fallido_no_crea_token(sesion, cliente):
    _usuario(sesion)

    r = cliente.post("/auth/login", json={"email": "ana@example.com", "password": "otra"})

    assert r.status_code == 401
    assert REFRESH_COOKIE_NAME not in _set_cookie(r)
    assert _tokens_activos(sesion) == 0


def test_registro_entrega_cookie_de_renovacion(sesion, cliente):
    r = cliente.post(
        "/auth/register",
        json={"email": "nuevo@example.com", "password": CLAVE, "full_name": "Nuevo", "workspace_kind": "personal"},
    )

    assert r.status_code == 200, r.text
    assert f"{REFRESH_COOKIE_NAME}=" in _set_cookie(r)
    assert _tokens_activos(sesion) == 1


# --------------------------------------------------------------------------
# Renovación y rotación
# --------------------------------------------------------------------------


def test_renovar_entrega_token_nuevo_y_rota_la_cookie(sesion, cliente):
    user, org = _usuario(sesion)
    _login(cliente)
    anterior = cliente.cookies.get(REFRESH_COOKIE_NAME)

    r = cliente.post("/auth/refresh")

    assert r.status_code == 200, r.text
    claims = decode_access_token(r.json()["access_token"])
    assert (claims["sub"], claims["org_id"], claims["role"]) == (str(user.id), str(org.id), "admin")
    nueva = cliente.cookies.get(REFRESH_COOKIE_NAME)
    assert nueva and nueva != anterior
    assert _tokens_activos(sesion) == 1  # el anterior quedó revocado


def test_renovar_sin_cookie_responde_401(sesion, cliente):
    r = cliente.post("/auth/refresh")

    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "refresh_missing"


def test_renovar_con_cookie_inventada_responde_401(sesion, cliente):
    cliente.cookies.set(REFRESH_COOKIE_NAME, "p." + "a" * 64, domain="testserver.local", path="/auth")

    r = cliente.post("/auth/refresh")

    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "refresh_invalid"


def test_renovacion_recordada_conserva_el_vencimiento_original(sesion, cliente):
    """La rotación no alarga la sesión: vence 30 días después del inicio, no de la última renovación."""
    _usuario(sesion)
    _login(cliente)
    sesion.expire_all()
    vence = sesion.scalar(select(RefreshToken.expires_at))

    cliente.post("/auth/refresh")

    sesion.expire_all()
    activo = sesion.execute(select(RefreshToken).where(RefreshToken.is_revoked.is_(False))).scalar_one()
    assert activo.expires_at == vence


def test_renovacion_sin_recordar_mantiene_cookie_de_sesion(sesion, cliente):
    _usuario(sesion)
    _login(cliente, remember=False)

    r = cliente.post("/auth/refresh")

    assert r.status_code == 200
    assert "max-age=" not in _set_cookie(r).lower()


def test_token_vencido_responde_401_y_borra_la_cookie(sesion, cliente):
    _usuario(sesion)
    _login(cliente)
    sesion.execute(text("UPDATE refresh_tokens SET expires_at = NOW() - INTERVAL '1 minute'"))
    sesion.commit()

    r = cliente.post("/auth/refresh")

    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "refresh_expired"
    assert f'{REFRESH_COOKIE_NAME}=""' in _set_cookie(r) or "max-age=0" in _set_cookie(r).lower()


def test_usar_un_token_recien_rotado_no_cierra_las_demas_sesiones(sesion, cliente):
    """Dos pestañas que renuevan a la vez: la segunda recibe `refresh_rotated` y reintenta."""
    _usuario(sesion)
    _login(cliente)
    anterior = cliente.cookies.get(REFRESH_COOKIE_NAME)
    cliente.post("/auth/refresh")
    otra = TestClient(app, base_url="https://testserver")
    otra.cookies.set(REFRESH_COOKIE_NAME, anterior, domain="testserver.local", path="/auth")

    r = otra.post("/auth/refresh")

    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "refresh_rotated"
    assert _tokens_activos(sesion) == 1


def test_reutilizar_un_token_rotado_hace_tiempo_cierra_todas_las_sesiones(sesion, cliente):
    """Un token rotado que vuelve a aparecer fuera de la ventana de gracia indica robo."""
    _usuario(sesion)
    _login(cliente)
    robado = cliente.cookies.get(REFRESH_COOKIE_NAME)
    cliente.post("/auth/refresh")
    sesion.execute(text("UPDATE refresh_tokens SET revoked_at = NOW() - INTERVAL '1 hour' WHERE is_revoked"))
    sesion.commit()
    atacante = TestClient(app, base_url="https://testserver")
    atacante.cookies.set(REFRESH_COOKIE_NAME, robado, domain="testserver.local", path="/auth")

    r = atacante.post("/auth/refresh")

    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "refresh_reused"
    assert _tokens_activos(sesion) == 0
    assert cliente.post("/auth/refresh").status_code == 401  # la sesión legítima también cae


def test_usuario_desactivado_no_puede_renovar(sesion, cliente):
    user, _ = _usuario(sesion)
    _login(cliente)
    sesion.execute(text("UPDATE users SET is_active = FALSE WHERE id = :id"), {"id": user.id})
    sesion.commit()

    r = cliente.post("/auth/refresh")

    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "refresh_inactive"


# --------------------------------------------------------------------------
# Cierre de sesión y cambio de organización
# --------------------------------------------------------------------------


def test_logout_revoca_el_token_y_borra_la_cookie(sesion, cliente):
    _usuario(sesion)
    _login(cliente)

    r = cliente.post("/auth/logout")

    assert r.status_code == 204
    assert _tokens_activos(sesion) == 0
    assert cliente.post("/auth/refresh").status_code == 401


def test_logout_sin_sesion_es_inofensivo(sesion, cliente):
    assert cliente.post("/auth/logout").status_code == 204


def test_cambiar_de_organizacion_mueve_la_renovacion_a_la_nueva(sesion, cliente):
    """Si no, al vencer el token de acceso la sesión volvería en silencio a la organización anterior."""
    user, _ = _usuario(sesion)
    otra = Organization(name="Beta", slug="beta", settings={"workspace_kind": "work"})
    sesion.add(otra)
    sesion.flush()
    sesion.add(OrgMembership(organization_id=otra.id, user_id=user.id, role="viewer", is_primary_org=False))
    sesion.commit()
    acceso = _login(cliente).json()["access_token"]

    cambio = cliente.post(
        "/auth/session/switch",
        json={"organization_id": str(otra.id)},
        headers={"Authorization": f"Bearer {acceso}"},
    )
    assert cambio.status_code == 200, cambio.text

    claims = decode_access_token(cliente.post("/auth/refresh").json()["access_token"])
    assert (claims["org_id"], claims["role"]) == (str(otra.id), "viewer")


def test_la_respuesta_nunca_incluye_el_token_de_renovacion(sesion, cliente):
    _usuario(sesion)
    r = _login(cliente)
    crudo = cliente.cookies.get(REFRESH_COOKIE_NAME)

    assert crudo not in r.text
    assert crudo not in cliente.post("/auth/refresh").text
