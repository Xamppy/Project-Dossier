"""S5.7 · S6.1 · Estrés del correo del dossier: informe enorme y envíos manuales simultáneos.

La concurrencia (CA16) usa Postgres real (``TEST_DATABASE_URL``) porque lo que se prueba es el
bloqueo de fila; con una sesión falsa no probaría nada.
"""
from __future__ import annotations

import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from alembic import command
from dossier.api.app import app
from dossier.api.auth_routes import get_db_if_configured
from dossier.db.models import Dossier, Organization, OrgMembership, User
from dossier.security.jwt_tokens import create_access_token
from dossier.services.dossier_email import build_dossier_email


def test_informe_de_500_kb_se_arma_rapido_y_completo():
    secciones = "\n\n".join(
        f"## Sección {i}\n\n" + "Hallazgo sobre la trayectoria profesional. " * 25 + f"\n\n| a | b |\n|---|---|\n| {i} | x |"
        for i in range(450)
    )
    assert len(secciones) > 500_000
    d = Dossier(id=uuid.uuid4(), subject_name="Ana", status="complete",
                dossier_data={"body": secciones, "output_language": "es"})

    inicio = time.monotonic()
    correo = build_dossier_email(d, language=None, dossier_url="https://e.com/d")
    assert time.monotonic() - inicio < 3

    assert "<h2>Sección 449</h2>" in correo.html
    assert "## Sección 449" in correo.text


def test_ca16_diez_envios_simultaneos_del_mismo_dossier_mandan_un_solo_correo(
    pg_vacia, alembic_cfg, servidor_smtp
):
    command.upgrade(alembic_cfg, "head")
    with Session(pg_vacia) as s:
        org = Organization(name="Org", slug=f"org-{uuid.uuid4().hex[:6]}", plan="pro")
        user = User(email="yo-estres@example.com")
        s.add_all([org, user])
        s.flush()
        s.add(OrgMembership(organization_id=org.id, user_id=user.id, role="user", is_primary_org=True))
        d = Dossier(organization_id=org.id, requested_by_user_id=user.id, subject_name="Ana",
                    status="complete", dossier_data={"body": "## Informe", "billing": "none"})
        s.add(d)
        s.commit()
        dossier_id, token = d.id, create_access_token(
            user_id=str(user.id), email=user.email, organization_id=str(org.id), role="user"
        )

    def _db():
        with Session(pg_vacia) as sesion:
            yield sesion

    app.dependency_overrides[get_db_if_configured] = _db
    try:
        client = TestClient(app)
        with ThreadPoolExecutor(max_workers=10) as pool:
            codigos = list(pool.map(
                lambda _: client.post(f"/dossiers/{dossier_id}/email",
                                      headers={"Authorization": f"Bearer {token}"}).status_code,
                range(10),
            ))
    finally:
        app.dependency_overrides.pop(get_db_if_configured, None)

    assert sorted(codigos) == [200] + [429] * 9
    assert len(servidor_smtp.mensajes) == 1
