"""S6.1 · Seguridad de POST /dossiers/{id}/email (CA14, CA16, CA17).

Sin Postgres: sesión falsa, como tests/security/test_dossier_detail_seguridad.py. El envío
real se sustituye por un registro de llamadas; nada sale a la red.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from dossier.api.app import app
from dossier.api.auth_routes import (
    OrgAuthContext,
    get_db_if_configured,
    get_org_auth_context,
)
from dossier.db.models import Dossier, Organization, OrgMembership, User
from dossier.services import dossier_email
from dossier.services.email_service import EmailDeliveryError


class _FakeResult:
    def all(self):
        return []

    def scalars(self):
        return self

    def first(self):
        return None

    def scalar_one_or_none(self):
        return None


class _FakeSession:
    def __init__(self, dossier: Dossier | None = None):
        self._dossier = dossier
        self.commits = 0

    def get(self, model, pk, **_):
        if model is Dossier and self._dossier is not None and pk == self._dossier.id:
            return self._dossier
        return None

    def execute(self, _stmt):
        return _FakeResult()

    def refresh(self, *_a, **_k):
        pass

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    def expire_all(self):
        pass


ORG = Organization(id=uuid.uuid4(), name="Propia", slug="propia")
YO = User(id=uuid.uuid4(), email="yo@example.com")


def _dossier(org_id=ORG.id, owner=YO.id) -> Dossier:
    return Dossier(
        id=uuid.uuid4(),
        organization_id=org_id,
        requested_by_user_id=owner,
        subject_name="Ana Prueba",
        status="complete",
        dossier_data={"format": "markdown", "body": "## Informe secreto\n\nContenido."},
        email_sent=False,
        email_recipients=[],
    )


@pytest.fixture
def enviados(monkeypatch):
    lista: list[dict] = []
    monkeypatch.setattr(dossier_email, "send_email", lambda **kw: lista.append(kw))
    monkeypatch.setenv("SMTP_USERNAME", "remitente@gmail.com")
    monkeypatch.setenv("SMTP_PASSWORD", "abcd efgh ijkl mnop")
    monkeypatch.delenv("SMTP_SECURITY", raising=False)
    monkeypatch.delenv("SMTP_HOST", raising=False)
    return lista


def _post(dossier, *, role="user", json=None, sesion=None):
    sesion = sesion or _FakeSession(dossier)
    membresia = OrgMembership(id=uuid.uuid4(), organization_id=ORG.id, user_id=YO.id, role=role)
    app.dependency_overrides[get_db_if_configured] = lambda: sesion
    app.dependency_overrides[get_org_auth_context] = lambda: OrgAuthContext(user=YO, org=ORG, membership=membresia)
    try:
        return TestClient(app).post(f"/dossiers/{dossier.id}/email", json=json)
    finally:
        app.dependency_overrides.clear()


def test_ca14_dossier_de_otra_organizacion_da_404_y_no_envia(enviados):
    ajeno = _dossier(org_id=uuid.uuid4(), owner=uuid.uuid4())

    resp = _post(ajeno)

    assert resp.status_code == 404
    assert enviados == []
    assert "Informe secreto" not in resp.text


def test_ca14_dossier_de_otro_usuario_no_compartido_da_404_a_un_user(enviados):
    de_otro = _dossier(owner=uuid.uuid4())

    resp = _post(de_otro, role="user")

    assert resp.status_code == 404
    assert enviados == []


def test_ca14_sin_sesion_da_401(enviados):
    app.dependency_overrides[get_db_if_configured] = lambda: _FakeSession()
    try:
        resp = TestClient(app).post(f"/dossiers/{uuid.uuid4()}/email")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 401
    assert enviados == []


def test_el_destinatario_no_se_puede_elegir(enviados):
    resp = _post(
        _dossier(),
        json={"to": ["atacante@example.com"], "recipient": "atacante@example.com", "email": "x@example.com"},
    )

    assert resp.status_code == 200
    assert [e["to"] for e in enviados] == [["yo@example.com"]]
    assert "atacante" not in resp.text


def test_ca16_enfriamiento_rige_aunque_otro_usuario_haya_enviado(enviados):
    d = _dossier()
    assert _post(d).status_code == 200

    resp = _post(d)

    assert resp.status_code == 429
    assert len(enviados) == 1


def test_ca17_error_smtp_no_expone_configuracion(monkeypatch):
    monkeypatch.setenv("SMTP_USERNAME", "remitente@gmail.com")
    monkeypatch.setenv("SMTP_PASSWORD", "abcd efgh ijkl mnop")
    monkeypatch.setenv("SMTP_HOST", "smtp.interno.example.com")
    monkeypatch.delenv("SMTP_SECURITY", raising=False)

    def falla(**_):
        raise EmailDeliveryError("El servidor SMTP rechazó el usuario o la contraseña de aplicación (535).")

    monkeypatch.setattr(dossier_email, "send_email", falla)
    sesion = _FakeSession()
    d = _dossier()
    sesion._dossier = d

    resp = _post(d, sesion=sesion)

    assert resp.status_code == 502
    for secreto in ("remitente@gmail.com", "abcd", "smtp.interno", "535"):
        assert secreto not in resp.text
    assert sesion.commits == 0
    assert d.email_sent is False


def test_ca17_sin_configuracion_no_revela_que_falta(monkeypatch):
    monkeypatch.delenv("SMTP_USERNAME", raising=False)
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    monkeypatch.delenv("SMTP_SECURITY", raising=False)

    resp = _post(_dossier())

    assert resp.status_code == 503
    assert "SMTP_" not in resp.text
