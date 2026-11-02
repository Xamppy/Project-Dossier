"""S6.1 · POST /dossiers/{id}/email, GET /dossiers/{id} y GET /auth/me contra Postgres real,
autenticación real y el servidor SMTP de loopback (CA13, CA15–CA18).

Requiere ``TEST_DATABASE_URL`` (fixture ``pg_vacia``).
"""
from __future__ import annotations

import io
import uuid

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader
from sqlalchemy.orm import Session

from alembic import command
from dossier.api import dossier_routes
from dossier.api.app import app
from dossier.api.auth_routes import get_db_if_configured
from dossier.db.models import Dossier, DossierShare, Organization, OrgMembership, User
from dossier.security.jwt_tokens import create_access_token

INFORME = "## Resumen ejecutivo\n\nAna Prueba dirige Empresa de Prueba SA."


class Mundo:
    def __init__(self, engine):
        self.engine = engine
        self.s = Session(engine)
        sufijo = uuid.uuid4().hex[:8]
        self.org = Organization(name=f"Org {sufijo}", slug=f"org-{sufijo}", plan="pro")
        self.s.add(self.org)
        self.s.commit()
        self.yo = self.usuario("yo")

    def usuario(self, nombre, role="user") -> User:
        u = User(email=f"{nombre}-{uuid.uuid4().hex[:6]}@example.com")
        self.s.add(u)
        self.s.flush()
        self.s.add(OrgMembership(organization_id=self.org.id, user_id=u.id, role=role, is_primary_org=True))
        self.s.commit()
        return u

    def token(self, user=None, role="user") -> dict:
        user = user or self.yo
        t = create_access_token(user_id=str(user.id), email=user.email,
                                organization_id=str(self.org.id), role=role)
        return {"Authorization": f"Bearer {t}"}

    def dossier(self, status="complete", body=INFORME, owner=None) -> Dossier:
        d = Dossier(
            organization_id=self.org.id,
            requested_by_user_id=(owner or self.yo).id,
            subject_name="Ana Prueba",
            status=status,
            dossier_data={"format": "markdown", "body": body, "billing": "none", "output_language": "es"},
        )
        self.s.add(d)
        self.s.commit()
        return d

    def leer(self, dossier_id) -> Dossier:
        self.s.expire_all()
        return self.s.get(Dossier, dossier_id)


@pytest.fixture
def mundo(pg_vacia, alembic_cfg):
    command.upgrade(alembic_cfg, "head")
    m = Mundo(pg_vacia)

    def _db():
        with Session(pg_vacia) as sesion:
            yield sesion

    app.dependency_overrides[get_db_if_configured] = _db
    yield m
    app.dependency_overrides.pop(get_db_if_configured, None)
    m.s.close()


@pytest.fixture
def client():
    return TestClient(app)


def _enviar(client, mundo, dossier, **kw):
    return client.post(f"/dossiers/{dossier.id}/email", headers=mundo.token(**kw))


# --- CA13 ---


def test_ca13_envia_al_correo_del_usuario_y_lo_registra(mundo, client, servidor_smtp):
    d = mundo.dossier()

    resp = _enviar(client, mundo, d)

    assert resp.status_code == 200, resp.text
    cuerpo = resp.json()
    assert cuerpo["dossier_id"] == str(d.id)
    assert cuerpo["email_sent"] is True
    assert cuerpo["email_sent_at"]
    assert cuerpo["email_recipients"] == [mundo.yo.email]
    (msg,) = servidor_smtp.mensajes
    assert servidor_smtp.sobres[0]["to"] == [mundo.yo.email]
    assert "Ana Prueba dirige Empresa de Prueba SA." in msg.get_body(("html",)).get_content()
    (adjunto,) = list(msg.iter_attachments())
    assert adjunto.get_content_type() == "application/pdf"
    assert "Ana Prueba" in PdfReader(io.BytesIO(adjunto.get_content())).pages[0].extract_text()
    guardado = mundo.leer(d.id)
    assert guardado.email_sent is True
    assert guardado.email_recipients == [mundo.yo.email]


def test_ca13_un_miembro_con_el_dossier_compartido_lo_recibe_en_su_correo(mundo, client, servidor_smtp):
    d = mundo.dossier()
    colega = mundo.usuario("colega")
    mundo.s.add(DossierShare(dossier_id=d.id, shared_with_user_id=colega.id, shared_by_user_id=mundo.yo.id))
    mundo.s.commit()

    resp = _enviar(client, mundo, d, user=colega)

    assert resp.status_code == 200, resp.text
    assert servidor_smtp.sobres[0]["to"] == [colega.email]
    assert resp.json()["email_recipients"] == [colega.email]


# --- CA15 ---


@pytest.mark.parametrize(("status", "body"), [("failed", INFORME), ("pending", INFORME), ("complete", "")])
def test_ca15_dossier_no_completo_o_vacio_da_409(mundo, client, servidor_smtp, status, body):
    d = mundo.dossier(status=status, body=body)

    resp = _enviar(client, mundo, d)

    assert resp.status_code == 409
    assert servidor_smtp.conexiones == 0
    assert mundo.leer(d.id).email_sent is False


# --- CA16 (secuencial; la concurrencia está en tests/stress) ---


def test_ca16_segundo_envio_dentro_del_minuto_da_429_con_retry_after(mundo, client, servidor_smtp):
    d = mundo.dossier()
    assert _enviar(client, mundo, d).status_code == 200

    resp = _enviar(client, mundo, d)

    assert resp.status_code == 429
    assert 1 <= int(resp.headers["Retry-After"]) <= 60
    assert len(servidor_smtp.mensajes) == 1


# --- CA17 ---


def test_ca17_sin_configuracion_da_503(mundo, client, servidor_smtp, monkeypatch):
    monkeypatch.setenv("SMTP_SECURITY", "starttls")  # exige usuario y contraseña, que no hay
    d = mundo.dossier()

    resp = _enviar(client, mundo, d)

    assert resp.status_code == 503
    assert servidor_smtp.conexiones == 0


def test_ca17_fallo_smtp_da_502_sin_marcar_el_dossier(mundo, client, servidor_smtp):
    servidor_smtp.rechazar = True
    d = mundo.dossier()

    resp = _enviar(client, mundo, d)

    assert resp.status_code == 502
    guardado = mundo.leer(d.id)
    assert (guardado.email_sent, guardado.email_sent_at, guardado.email_recipients) == (False, None, [])


# --- CA18 ---


def test_ca18_detalle_del_dossier_expone_el_estado_del_envio(mundo, client, servidor_smtp):
    d = mundo.dossier()
    antes = client.get(f"/dossiers/{d.id}", headers=mundo.token()).json()["email_delivery"]
    _enviar(client, mundo, d)

    despues = client.get(f"/dossiers/{d.id}", headers=mundo.token()).json()["email_delivery"]

    assert antes == {"sent": False, "sent_at": None, "recipients": []}
    assert despues["sent"] is True
    assert despues["sent_at"]
    assert despues["recipients"] == [mundo.yo.email]


def test_ca18_auth_me_indica_si_el_envio_esta_disponible(mundo, client, servidor_smtp, monkeypatch):
    disponible = client.get("/auth/me", headers=mundo.token()).json()
    monkeypatch.setenv("SMTP_SECURITY", "starttls")
    no_disponible = client.get("/auth/me", headers=mundo.token()).json()

    assert disponible["email_delivery_available"] is True
    assert no_disponible["email_delivery_available"] is False
    assert not [k for k in disponible if "smtp" in k.lower()]


# --- Ruta síncrona de Personas ---


def test_ruta_sincrona_de_personas_tambien_envia_el_dossier(mundo, client, monkeypatch):
    llamadas: list[dict] = []
    resultado = {"saved_dossier": {"id": str(uuid.uuid4()), "status": "complete"}}
    monkeypatch.setattr(dossier_routes, "run_person_research_and_persist", lambda *a, **k: resultado)
    monkeypatch.setattr(
        dossier_routes,
        "enviar_dossier_al_solicitante",
        lambda db, *, result, user: llamadas.append({"result": result, "email": user.email}),
    )

    resp = client.post(
        "/dossiers/person/research",
        headers=mundo.token(),
        json={"full_name": "Ana Prueba", "replace_dossier_id": str(uuid.uuid4())},
    )

    assert resp.status_code == 200, resp.text
    assert llamadas == [{"result": resultado, "email": mundo.yo.email}]
