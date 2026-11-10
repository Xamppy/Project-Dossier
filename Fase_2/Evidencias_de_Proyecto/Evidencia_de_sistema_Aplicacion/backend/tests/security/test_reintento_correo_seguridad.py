"""S6.4, seguridad: la cola de reintentos no guarda el destinatario (CA10) y un reintento solo
envía dossiers completos de esa organización y de ese usuario (CA11).

Requiere ``TEST_DATABASE_URL`` y el SMTP de loopback.
"""
from __future__ import annotations

import socket
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from alembic import command
from dossier.db.models import Dossier, DossierEmailRetry, Organization, User
from dossier.services import dossier_email_retry
from dossier.services.dossier_email import deliver_dossier_after_generation
from dossier.services.dossier_email_retry import procesar_reintentos


def _puerto_cerrado() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _org_usuario(s: Session) -> tuple[Organization, User]:
    sufijo = uuid.uuid4().hex[:8]
    org = Organization(name=f"Org {sufijo}", slug=f"org-{sufijo}", plan="pro")
    user = User(email=f"u-{sufijo}@mi-empresa.example")
    s.add_all([org, user])
    s.flush()
    return org, user


def _dossier(s: Session, org, user, *, status="complete", nombre="Ana Prueba") -> Dossier:
    d = Dossier(organization_id=org.id, requested_by_user_id=user.id, subject_name=nombre, status=status,
                dossier_data={"format": "markdown", "body": f"## {nombre}", "billing": "none"})
    s.add(d)
    s.flush()
    return d


def test_la_fila_en_espera_no_guarda_el_destinatario(pg_vacia, alembic_cfg, servidor_smtp, monkeypatch):
    command.upgrade(alembic_cfg, "head")
    monkeypatch.setattr(dossier_email_retry, "_dormir", lambda _s: None)
    monkeypatch.setenv("SMTP_PORT", str(_puerto_cerrado()))
    with Session(pg_vacia) as s:
        org, user = _org_usuario(s)
        d = _dossier(s, org, user)
        s.commit()
        dossier_id, correo = d.id, user.email

    with Session(pg_vacia) as db:
        assert deliver_dossier_after_generation(db, dossier_id=dossier_id, recipient=correo) is False

    with pg_vacia.connect() as conn:
        filas = conn.execute(text("SELECT row_to_json(r)::text FROM dossier_email_retries r")).scalars().all()
    assert len(filas) == 1
    assert correo not in filas[0]


def test_un_reintento_solo_envia_lo_propio_y_completo(pg_vacia, alembic_cfg, servidor_smtp):
    """Una fila alterada que apunta a dossiers ajenos o incompletos no los envía."""
    command.upgrade(alembic_cfg, "head")
    with Session(pg_vacia) as s:
        org, user = _org_usuario(s)
        otra_org, otro = _org_usuario(s)
        propio = _dossier(s, org, user, nombre="Propio SA")
        incompleto = _dossier(s, org, user, status="failed", nombre="Incompleto SA")
        de_otro_usuario = _dossier(s, org, otro, nombre="Colega SA")
        de_otra_org = _dossier(s, otra_org, otro, nombre="Ajena SA")
        s.add(DossierEmailRetry(
            organization_id=org.id, user_id=user.id, kind="reunion",
            dossier_ids=[propio.id, incompleto.id, de_otro_usuario.id, de_otra_org.id],
            meeting_title="Demo", language="es", attempts=0,
            next_attempt_at=datetime.now(UTC) - timedelta(minutes=1),
        ))
        s.commit()
        destino = user.email

    with Session(pg_vacia) as db:
        assert procesar_reintentos(db)["enviados"] == 1

    (mensaje,) = servidor_smtp.mensajes
    assert [d for sobre in servidor_smtp.sobres for d in sobre["to"]] == [destino]
    adjuntos = [a.get_filename() for a in mensaje.iter_attachments()]
    assert adjuntos == ["dossier-propio-sa.pdf"]
    with Session(pg_vacia) as s:
        assert s.scalars(select(DossierEmailRetry)).all() == []
