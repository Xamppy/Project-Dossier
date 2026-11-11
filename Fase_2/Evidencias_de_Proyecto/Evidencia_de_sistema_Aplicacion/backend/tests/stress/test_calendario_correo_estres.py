"""S6.3, estrés: una reunión grande y un servidor SMTP que no responde.

Requiere ``TEST_DATABASE_URL`` y el SMTP de loopback.
"""
from __future__ import annotations

import time
import uuid

from sqlalchemy.orm import Session

from alembic import command
from dossier.db.models import Dossier, Organization, User
from dossier.services.dossier_email import deliver_meeting_dossiers

DOSSIERS = 10


def _sembrar(engine) -> tuple[list[uuid.UUID], str]:
    with Session(engine) as s:
        sufijo = uuid.uuid4().hex[:8]
        org = Organization(name=f"Org {sufijo}", slug=f"org-{sufijo}", plan="pro")
        yo = User(email=f"yo-{sufijo}@mi-empresa.example")
        s.add_all([org, yo])
        s.flush()
        dossiers = [
            Dossier(
                organization_id=org.id, requested_by_user_id=yo.id, subject_name=f"Persona {i}",
                status="complete",
                dossier_data={"format": "markdown", "body": "## Resumen\n\n" + "Dato. " * 400,
                              "billing": "none"},
            )
            for i in range(DOSSIERS)
        ]
        s.add_all(dossiers)
        s.commit()
        return [d.id for d in dossiers], yo.email


def test_una_reunion_con_diez_dossiers_es_un_solo_correo(pg_vacia, alembic_cfg, servidor_smtp):
    command.upgrade(alembic_cfg, "head")
    ids, dueno = _sembrar(pg_vacia)

    inicio = time.perf_counter()
    with Session(pg_vacia) as db:
        assert deliver_meeting_dossiers(db, dossier_ids=ids, recipient=dueno, meeting_title="Directorio",
                                        language="es", calendar_event_id=None)
    duracion = time.perf_counter() - inicio

    (mensaje,) = servidor_smtp.mensajes
    pdfs = [a for a in mensaje.iter_attachments() if a.get_content_type() == "application/pdf"]
    assert len(pdfs) == DOSSIERS
    assert duracion < 60, f"armar y enviar {DOSSIERS} PDFs tardó {duracion:.1f} s"


def test_un_smtp_mudo_corta_por_tiempo_y_no_lanza(pg_vacia, alembic_cfg, servidor_smtp, monkeypatch):
    command.upgrade(alembic_cfg, "head")
    monkeypatch.setenv("SMTP_TIMEOUT_SECONDS", "1")
    servidor_smtp.mudo = True
    ids, dueno = _sembrar(pg_vacia)

    inicio = time.perf_counter()
    with Session(pg_vacia) as db:
        enviado = deliver_meeting_dossiers(db, dossier_ids=ids[:2], recipient=dueno, meeting_title="Demo",
                                           language="es", calendar_event_id=None)
    assert enviado is False
    assert time.perf_counter() - inicio < 20
