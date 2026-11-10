"""S6.2, estrés (CA11): diez canjes simultáneos del mismo enlace, exactamente uno gana.

Requiere ``TEST_DATABASE_URL``.
"""
from __future__ import annotations

import threading
import uuid

from sqlalchemy.orm import Session

from alembic import command
from dossier.db.models import Dossier, Organization, User
from dossier.services.dossier_access_links import canjear_enlace, crear_enlace

CANJES = 10


def test_diez_canjes_simultaneos_solo_uno_gana(pg_vacia, alembic_cfg):
    command.upgrade(alembic_cfg, "head")
    with Session(pg_vacia) as s:
        sufijo = uuid.uuid4().hex[:8]
        org = Organization(name=f"Org {sufijo}", slug=f"org-{sufijo}", plan="pro")
        user = User(email=f"u-{sufijo}@mi-empresa.example")
        s.add_all([org, user])
        s.flush()
        d = Dossier(organization_id=org.id, requested_by_user_id=user.id, subject_name="Ana", status="complete",
                    dossier_data={"format": "markdown", "body": "## R", "billing": "none"})
        s.add(d)
        s.flush()
        token = crear_enlace(s, d, user_id=user.id)
        s.commit()

    ganadores: list[object] = []
    errores: list[BaseException] = []
    barrera = threading.Barrier(CANJES)

    def canjear():
        try:
            with Session(pg_vacia) as db:
                barrera.wait(timeout=10)
                resultado = canjear_enlace(db, token)
                if resultado is not None:
                    ganadores.append(resultado)
        except BaseException as e:  # la prueba reporta cualquier falla del hilo
            errores.append(e)

    hilos = [threading.Thread(target=canjear) for _ in range(CANJES)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=60)

    assert errores == []
    assert len(ganadores) == 1
