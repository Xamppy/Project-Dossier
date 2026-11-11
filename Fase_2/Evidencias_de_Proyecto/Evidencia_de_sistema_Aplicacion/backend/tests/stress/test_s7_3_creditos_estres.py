"""S7.3 · Estrés: varios workers a la vez no cobran dos veces ni procesan dos veces un trabajo.

Doce trabajos de Personas en cola y cuatro workers que toman de la cola en paralelo
(``claim_next_queued_job`` con ``SKIP LOCKED``). Al final: doce dossiers, doce movimientos de
crédito y el saldo baja exactamente doce. Requiere ``TEST_DATABASE_URL``.
"""
from __future__ import annotations

import threading
from collections import Counter

from sqlalchemy import text
from sqlalchemy.orm import Session

from dossier.db.models import DossierGenerationJob
from dossier.services import dossier_generation_job_service as servicio
from tests.integration.test_s7_3_creditos_aislamiento import (  # noqa: F401
    SALDO_INICIAL,
    dossiers,
    movimientos,
    mundo,
    saldo,
)

TRABAJOS = 12
WORKERS = 4


def test_cuatro_workers_doce_trabajos_un_cobro_por_dossier(mundo):  # noqa: F811
    with Session(mundo.engine) as db:
        for i in range(TRABAJOS):
            job = DossierGenerationJob(
                organization_id=mundo.org_a,
                requested_by_user_id=mundo.a_admin,
                status="queued",
                job_type="person_manual",
                external_event_id=f"person:carga-{i}",
                reunion_snapshot={
                    "person_request": {
                        "full_name": f"Ana Prueba {i}",
                        "email": "ana@empresa.example",
                        "research_source": "pdl",
                        "max_profiles": 1,
                    }
                },
                depth_level="basic",
                credits_estimated=1,
            )
            db.add(job)
            mundo.jobs.append(job.id)
        db.commit()

    procesados: Counter[str] = Counter()
    candado = threading.Lock()
    barrera = threading.Barrier(WORKERS)

    def worker() -> None:
        barrera.wait()
        db = Session(mundo.engine)
        try:
            while True:
                job = servicio.claim_next_queued_job(db)
                if job is None:
                    return
                with candado:
                    procesados[str(job.id)] += 1
                servicio.process_dossier_generation_job(db, job.id)
        finally:
            db.close()

    hilos = [threading.Thread(target=worker) for _ in range(WORKERS)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    assert len(procesados) == TRABAJOS
    assert set(procesados.values()) == {1}  # ningún trabajo lo tomaron dos workers
    with mundo.engine.connect() as c:
        estados = dict(
            c.execute(
                text("SELECT status, count(*) FROM dossier_generation_jobs WHERE organization_id = :o GROUP BY 1"),
                {"o": mundo.org_a},
            ).all()
        )
    assert estados == {"completed": TRABAJOS}
    assert len(dossiers(mundo, mundo.org_a)) == TRABAJOS
    movs = movimientos(mundo, mundo.org_a)
    assert len(movs) == TRABAJOS
    assert len({d for d, _, _ in movs}) == TRABAJOS
    assert saldo(mundo, mundo.org_a) == SALDO_INICIAL - TRABAJOS
    # Cada movimiento anota su propio saldo: de 99 a 88 sin repetir.
    assert sorted(s for _, _, s in movs) == list(range(SALDO_INICIAL - TRABAJOS, SALDO_INICIAL))
