"""S6.3, seguridad (CA8): los dossiers de una reunión solo van al dueño del calendario.

Los asistentes aparecen en la reunión y en sus dossiers, pero nunca reciben el correo.
Requiere ``TEST_DATABASE_URL`` y el SMTP de loopback.
"""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from alembic import command
from dossier.db.models import Dossier, Organization, User
from dossier.services.dossier_email import deliver_meeting_dossiers

ASISTENTES = ("ana@cliente.example", "luis@cliente.example")


def test_el_correo_va_solo_al_dueno_del_calendario(pg_vacia, alembic_cfg, servidor_smtp):
    command.upgrade(alembic_cfg, "head")
    with Session(pg_vacia) as s:
        sufijo = uuid.uuid4().hex[:8]
        org = Organization(name=f"Org {sufijo}", slug=f"org-{sufijo}", plan="pro")
        yo = User(email=f"yo-{sufijo}@mi-empresa.example")
        s.add_all([org, yo])
        s.flush()
        dossiers = [
            Dossier(
                organization_id=org.id, requested_by_user_id=yo.id, subject_name=nombre, status="complete",
                dossier_data={"format": "markdown", "body": f"Contacto: {correo}", "billing": "none"},
            )
            for nombre, correo in zip(("Ana Prueba", "Luis Prueba"), ASISTENTES, strict=True)
        ]
        s.add_all(dossiers)
        s.commit()
        ids, dueno = [d.id for d in dossiers], yo.email

    with Session(pg_vacia) as db:
        assert deliver_meeting_dossiers(db, dossier_ids=ids, recipient=dueno, meeting_title="Demo",
                                        language="es", calendar_event_id=None)

    destinatarios = [d for sobre in servidor_smtp.sobres for d in sobre["to"]]
    assert destinatarios == [dueno]
    (mensaje,) = servidor_smtp.mensajes
    for cabecera in ("To", "Cc", "Bcc"):
        valor = mensaje.get(cabecera) or ""
        assert not any(a in valor for a in ASISTENTES), f"un asistente aparece en {cabecera}"
