"""S6.4, estrés: muchos envíos en espera y dos procesos de reintento a la vez (CA12).

Requiere ``TEST_DATABASE_URL`` y el SMTP de loopback.
"""
from __future__ import annotations

import threading
import time
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from alembic import command
from dossier.db.models import Dossier, DossierEmailRetry, Organization, User
from dossier.services.dossier_email_retry import procesar_reintentos

EN_ESPERA = 20


def _sembrar(engine, cantidad: int) -> None:
    with Session(engine) as s:
        sufijo = uuid.uuid4().hex[:8]
        org = Organization(name=f"Org {sufijo}", slug=f"org-{sufijo}", plan="pro")
        user = User(email=f"u-{sufijo}@mi-empresa.example")
        s.add_all([org, user])
        s.flush()
        vencido = datetime.now(UTC) - timedelta(minutes=1)
        for i in range(cantidad):
            d = Dossier(organization_id=org.id, requested_by_user_id=user.id, subject_name=f"Persona {i}",
                        status="complete", dossier_data={"format": "markdown", "body": "## R", "billing": "none"})
            s.add(d)
            s.flush()
            s.add(DossierEmailRetry(organization_id=org.id, user_id=user.id, kind="persona", dossier_ids=[d.id],
                                    language="es", attempts=0, next_attempt_at=vencido))
        s.commit()


def _quedan(engine) -> int:
    with Session(engine) as s:
        return len(s.scalars(select(DossierEmailRetry)).all())


def test_muchos_envios_en_espera_salen_en_una_vuelta(pg_vacia, alembic_cfg, servidor_smtp):
    command.upgrade(alembic_cfg, "head")
    _sembrar(pg_vacia, EN_ESPERA)

    inicio = time.perf_counter()
    with Session(pg_vacia) as db:
        resumen = procesar_reintentos(db, limite=EN_ESPERA)
    duracion = time.perf_counter() - inicio

    assert resumen["enviados"] == EN_ESPERA
    assert len(servidor_smtp.mensajes) == EN_ESPERA
    assert _quedan(pg_vacia) == 0
    assert duracion < 60, f"reintentar {EN_ESPERA} envíos tardó {duracion:.1f} s"


def test_dos_procesos_a_la_vez_no_envian_dos_veces(pg_vacia, alembic_cfg, servidor_smtp):
    command.upgrade(alembic_cfg, "head")
    _sembrar(pg_vacia, EN_ESPERA)
    errores: list[BaseException] = []
    barrera = threading.Barrier(2)

    def correr():
        try:
            with Session(pg_vacia) as db:
                barrera.wait(timeout=10)
                procesar_reintentos(db, limite=EN_ESPERA)
        except BaseException as e:  # la prueba reporta cualquier falla del hilo
            errores.append(e)

    hilos = [threading.Thread(target=correr) for _ in range(2)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=90)

    assert errores == []
    assert len(servidor_smtp.mensajes) == EN_ESPERA
    assert _quedan(pg_vacia) == 0
