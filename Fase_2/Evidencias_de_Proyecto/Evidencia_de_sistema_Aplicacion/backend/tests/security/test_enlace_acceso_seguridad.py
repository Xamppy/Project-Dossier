"""S6.2, seguridad: solo el hash en la base (CA5), límite por IP (CA10) y una respuesta que no
trae nada más que ese dossier (CA12). Requiere ``TEST_DATABASE_URL``.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from alembic import command
from dossier.api.app import app
from dossier.api.auth_routes import get_db_if_configured
from dossier.db.models import Dossier, Organization, User
from dossier.services.dossier_access_links import crear_enlace


@pytest.fixture
def base(pg_vacia, alembic_cfg):
    command.upgrade(alembic_cfg, "head")

    def _db():
        with Session(pg_vacia) as sesion:
            yield sesion

    app.dependency_overrides[get_db_if_configured] = _db
    yield pg_vacia
    app.dependency_overrides.pop(get_db_if_configured, None)


def _enlace(engine) -> tuple[str, uuid.UUID]:
    with Session(engine) as s:
        sufijo = uuid.uuid4().hex[:8]
        org = Organization(name=f"Org secreta {sufijo}", slug=f"org-{sufijo}", plan="pro")
        user = User(email=f"u-{sufijo}@mi-empresa.example")
        s.add_all([org, user])
        s.flush()
        d = Dossier(organization_id=org.id, requested_by_user_id=user.id, subject_name="Ana Prueba",
                    status="complete", subject_email="ana@cliente.example",
                    dossier_data={"format": "markdown", "body": "## Informe", "billing": "none"})
        otro = Dossier(organization_id=org.id, requested_by_user_id=user.id, subject_name="Otro Dossier",
                       status="complete", dossier_data={"format": "markdown", "body": "## Otro", "billing": "none"})
        s.add_all([d, otro])
        s.flush()
        token = crear_enlace(s, d, user_id=user.id)
        s.commit()
        return token, d.id


def test_la_base_guarda_solo_el_hash(base):
    token, _ = _enlace(base)
    with base.connect() as conn:
        filas = conn.execute(text("SELECT row_to_json(r)::text FROM dossier_access_links r")).scalars().all()
    assert len(filas) == 1
    assert token not in filas[0]


def test_la_respuesta_solo_trae_ese_dossier(base):
    token, _ = _enlace(base)
    r = TestClient(app).post("/dossier-access", json={"token": token})
    assert r.status_code == 200
    cuerpo = r.json()
    assert set(cuerpo) == {"subject_name", "body", "created_at", "output_language"}
    texto = r.text
    for ajeno in ("Org secreta", "Otro Dossier", "ana@cliente.example", "mi-empresa.example", "organization"):
        assert ajeno not in texto


def test_mas_de_20_canjes_por_minuto_desde_una_ip_dan_429(base, monkeypatch):
    monkeypatch.setenv("ACCESS_LINK_RATE_LIMIT", "20/60")
    client = TestClient(app)
    respuestas = [client.post("/dossier-access", json={"token": f"falso-{i}"}).status_code for i in range(21)]
    assert respuestas[:20] == [410] * 20
    assert respuestas[20] == 429


@pytest.mark.parametrize("cuerpo", [{}, {"token": ""}, {"token": "x" * 5000}, {"token": 123}])
def test_un_token_malformado_no_rompe_nada(base, cuerpo):
    r = TestClient(app).post("/dossier-access", json=cuerpo)
    assert r.status_code in (410, 422)
